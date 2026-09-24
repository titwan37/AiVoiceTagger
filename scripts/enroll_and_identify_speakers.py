#!/usr/bin/env python3
"""
AiVoiceTagger — Voice Biometric Speaker Enrollment & Matching Pipeline
======================================================================
Identifies known actors across all transcribed speeches in aivoicetagger_state.db
using ECAPA-TDNN / D-Vector acoustic embeddings and cosine similarity matching.
Extracts acoustic stress biomarkers (Pitch F0, Jitter, Vocal Strain, Speech Rate).
"""

import argparse
import json
import logging
import os
import re
import sqlite3
import subprocess
import shutil
import sys
import tempfile
import warnings
warnings.filterwarnings("ignore", category=FutureWarning)

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import polars as pl  # python -m pip install polars
import soundfile as sf  # pip install soundfile

# python -m pip install --upgrade torch torchaudio --index-url https://download.pytorch.org/whl/cu121 --force-reinstall
# python -m pip install --upgrade torch torchaudio --index-url https://download.pytorch.org/whl/cu121 --force-reinstall
# python -m pip install onnxruntime-gpu

# python -m pip install speechbrain


# Optional heavy ML frameworks with graceful fallback
try:
    import torch  # type: ignore
    import torchaudio  # type: ignore
    HAS_TORCH = True
except ImportError:
    HAS_TORCH = False

try:
    from speechbrain.inference.speaker import EncoderClassifier  # type: ignore
    HAS_SPEECHBRAIN = True
except ImportError:
    HAS_SPEECHBRAIN = False

from tqdm import tqdm

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("VoiceBiometricEngine")


# ---------------------------------------------------------------------------
# Data Models
# ---------------------------------------------------------------------------
@dataclass
class MatchResult:
    actor_tag: str
    confidence: float
    is_ambiguous: bool
    second_best_actor: Optional[str] = None
    second_best_score: Optional[float] = None


@dataclass
class AcousticBiomarkers:
    rms_energy: float
    pitch_f0_hz: float
    pitch_variance: float
    vocal_strain_index: float
    speech_rate_wpm: float


# ---------------------------------------------------------------------------
# Biometric & Biomarker Processing Engine
# ---------------------------------------------------------------------------
class VoiceBiometricEngine:
    def __init__(
        self,
        profiles_dir: str = "profiles",
        db_path: str = "aivoicetagger_state.db",
        match_threshold: float = 0.66,
        ambiguity_margin: float = 0.09,
        device: Optional[str] = None,
        verbose: bool = True,
        actor_thresholds: Optional[Dict[str, float]] = None,
    ):
        self.profiles_dir = Path(profiles_dir)
        self.db_path = Path(db_path)
        self.match_threshold = match_threshold
        self.ambiguity_margin = ambiguity_margin
        self.verbose = verbose
        self.actor_thresholds = actor_thresholds or {}
        self.actor_start_years = {
            "Dinda": 2020,
        }
        
        if not self.db_path.exists():
            raise FileNotFoundError(f"Database not found at {self.db_path}")

        # Hardware acceleration
        if device:
            self.device = device
        elif HAS_TORCH and torch.cuda.is_available():
            self.device = "cuda:0"
        else:
            self.device = "cpu"

        logger.info(f"Initialized VoiceBiometricEngine on device: {self.device}")
        
        # Load embedding model
        self.classifier = None
        if HAS_SPEECHBRAIN and HAS_TORCH:
            try:
                logger.info("Loading SpeechBrain ECAPA-TDNN model (spkrec-ecapa-voxceleb)...")
                self.classifier = EncoderClassifier.from_hparams(
                    source="speechbrain/spkrec-ecapa-voxceleb",
                    run_opts={"device": self.device},
                )
                logger.info("✅ ECAPA-TDNN 192-dim acoustic model loaded successfully.")
            except Exception as e:
                logger.warning(f"SpeechBrain model download/load failed: {e}. Falling back to acoustic spectral vectors.")
        else:
            logger.info("SpeechBrain / PyTorch not installed. Using spectral MFCC centroid fallback.")

        self.enrolled_vault: Dict[str, np.ndarray] = {}

    def _get_connection(self) -> sqlite3.Connection:
        """Establish resilient SQLite connection with WAL mode."""
        conn = sqlite3.connect(str(self.db_path), timeout=15.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode = WAL;")
        conn.execute("PRAGMA busy_timeout = 10000;")
        return conn

    def apply_schema_migrations(self):
        """Ensure speaker_profiles and biometric columns exist in SQLite database."""
        conn = self._get_connection()
        cursor = conn.cursor()

        # 1. Create speaker_profiles table
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS speaker_profiles (
                actor_id TEXT PRIMARY KEY,
                display_name TEXT NOT NULL,
                sample_count INTEGER NOT NULL,
                embedding_blob BLOB NOT NULL,
                created_at TEXT NOT NULL
            );
            """
        )

        # 2. Check and alter speeches table
        cursor.execute("PRAGMA table_info(speeches);")
        speech_cols = [row["name"] for row in cursor.fetchall()]
        if "speaker_anonymized" not in speech_cols:
            cursor.execute("ALTER TABLE speeches ADD COLUMN speaker_anonymized TEXT;")
            logger.info("Added column 'speaker_anonymized' to speeches table (GDPR compliant).")
        if "speaker_disclosed" not in speech_cols:
            cursor.execute("ALTER TABLE speeches ADD COLUMN speaker_disclosed TEXT;")
            logger.info("Added column 'speaker_disclosed' to speeches table (Certified Forensic ID).")
        if "speaker_tag" not in speech_cols:
            cursor.execute("ALTER TABLE speeches ADD COLUMN speaker_tag TEXT;")
            logger.info("Added column 'speaker_tag' to speeches table.")
        if "speaker_confidence" not in speech_cols:
            cursor.execute("ALTER TABLE speeches ADD COLUMN speaker_confidence REAL DEFAULT 0.0;")
            logger.info("Added column 'speaker_confidence' to speeches table.")
        if "biomarkers_json" not in speech_cols:
            cursor.execute("ALTER TABLE speeches ADD COLUMN biomarkers_json TEXT;")
            logger.info("Added column 'biomarkers_json' to speeches table.")

        # 3. Check and alter records table
        cursor.execute("PRAGMA table_info(records);")
        rec_cols = [row["name"] for row in cursor.fetchall()]
        if "participants_anonymized_json" not in rec_cols:
            cursor.execute("ALTER TABLE records ADD COLUMN participants_anonymized_json TEXT;")
            logger.info("Added column 'participants_anonymized_json' to records table (GDPR compliant).")
        if "participants_disclosed_json" not in rec_cols:
            cursor.execute("ALTER TABLE records ADD COLUMN participants_disclosed_json TEXT;")
            logger.info("Added column 'participants_disclosed_json' to records table (Certified Forensic ID).")
        if "participants_json" not in rec_cols:
            cursor.execute("ALTER TABLE records ADD COLUMN participants_json TEXT;")
            logger.info("Added column 'participants_json' to records table.")
        if "stress_index" not in rec_cols:
            cursor.execute("ALTER TABLE records ADD COLUMN stress_index REAL DEFAULT 0.0;")
            logger.info("Added column 'stress_index' to records table.")

        conn.commit()
        conn.close()
        logger.info("✅ Database schema migrations (GDPR Anonymized & Certified Disclosed) applied successfully.")

    def load_audio_pcm(self, audio_path: Path, target_sr: int = 16000) -> Tuple[np.ndarray, int]:
        """Loads audio file into float32 mono PCM array using soundfile, local cache, or fast multi-threaded ffmpeg."""
        try:
            data, sr = sf.read(str(audio_path), dtype="float32")
            if data.ndim > 1:
                data = np.mean(data, axis=1)
            if sr != target_sr:
                indices = np.round(np.arange(0, len(data), sr / target_sr)).astype(int)
                data = data[indices[indices < len(data)]]
            return data, target_sr
        except Exception:
            # Check local PCM cache folder to eliminate network SMB re-decoding lag
            cache_dir = Path(".pcm_cache")
            cache_dir.mkdir(exist_ok=True)
            stat = audio_path.stat() if audio_path.exists() else None
            cache_key = f"{audio_path.stem[:25]}_{stat.st_size if stat else 0}.wav"
            cache_path = cache_dir / cache_key

            if cache_path.exists():
                try:
                    data, sr = sf.read(str(cache_path), dtype="float32")
                    return data, sr
                except Exception:
                    pass

            # If input file is on network SMB share, copy locally first to prevent SMB seeking lag
            local_src = str(audio_path)
            temp_copy = None
            if str(audio_path).startswith("\\\\") or not audio_path.is_absolute():
                try:
                    with tempfile.NamedTemporaryFile(suffix=audio_path.suffix, delete=False) as tmp_file:
                        temp_copy = tmp_file.name
                    shutil.copyfile(str(audio_path), temp_copy)
                    local_src = temp_copy
                except Exception:
                    local_src = str(audio_path)

            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
                tmp_wav = tmp.name
            try:
                cmd = ["ffmpeg", "-y", "-threads", "4", "-i", local_src, "-vn", "-sn", "-ar", str(target_sr), "-ac", "1", tmp_wav]
                res = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
                if res.returncode == 0:
                    data, sr = sf.read(tmp_wav, dtype="float32")
                    try:
                        sf.write(str(cache_path), data, sr)
                    except Exception:
                        pass
                    return data, sr
            finally:
                if temp_copy and os.path.exists(temp_copy):
                    try:
                        os.remove(temp_copy)
                    except Exception:
                        pass
                if os.path.exists(tmp_wav):
                    try:
                        os.remove(tmp_wav)
                    except Exception:
                        pass
            raise RuntimeError(f"Failed to decode audio file {audio_path.name}")

    def extract_embedding_from_pcm(self, pcm_samples: np.ndarray, samplerate: int = 16000) -> np.ndarray:
        """Compute normalized 192-dim D-Vector embedding from float32 audio samples."""
        if len(pcm_samples) < 3200:  # < 200ms
            # Pad short audio
            pad_len = 3200 - len(pcm_samples)
            pcm_samples = np.pad(pcm_samples, (0, pad_len), mode="constant")

        if self.classifier is not None and HAS_TORCH:
            signal = torch.from_numpy(pcm_samples).unsqueeze(0).float()
            with torch.no_grad():
                emb = self.classifier.encode_batch(signal.to(self.device))
                emb_np = emb.squeeze().cpu().numpy()
                norm = np.linalg.norm(emb_np)
                return emb_np / norm if norm > 0 else emb_np
        else:
            # Deterministic spectral acoustic vector fallback (128-dim)
            fft_vals = np.abs(np.fft.rfft(pcm_samples, n=256))
            norm = np.linalg.norm(fft_vals)
            return (fft_vals / norm) if norm > 0 else fft_vals

    def extract_embeddings_batch(
        self, pcm_slices: List[np.ndarray], samplerate: int = 16000, batch_size: int = 32
    ) -> List[np.ndarray]:
        """Compute normalized D-Vector embeddings using safe CUDA micro-batching (batch_size=32)."""
        if not pcm_slices:
            return []

        if self.classifier is not None and HAS_TORCH:
            all_embeddings = []
            target_max = int(4.0 * samplerate)  # Cap speech slices to 4.0s max for ECAPA-TDNN optimal CUDA speed

            for i in range(0, len(pcm_slices), batch_size):
                chunk = pcm_slices[i : i + batch_size]
                processed_chunk = []
                for pcm in chunk:
                    if len(pcm) > target_max:
                        mid = len(pcm) // 2
                        pcm = pcm[mid - target_max // 2 : mid + target_max // 2]
                    processed_chunk.append(pcm)

                max_len = max(max(len(p) for p in processed_chunk), 3200)
                batch_tensors = []
                for pcm in processed_chunk:
                    if len(pcm) < max_len:
                        pcm = np.pad(pcm, (0, max_len - len(pcm)), mode="constant")
                    batch_tensors.append(torch.from_numpy(pcm).float())

                batch_signal = torch.stack(batch_tensors)
                try:
                    inference_ctx = torch.inference_mode if hasattr(torch, "inference_mode") else torch.no_grad
                    with inference_ctx():
                        embs = self.classifier.encode_batch(batch_signal.to(self.device))
                        embs_np = embs.squeeze(1).cpu().numpy()
                        if embs_np.ndim == 1:
                            embs_np = np.expand_dims(embs_np, axis=0)

                        norms = np.linalg.norm(embs_np, axis=1, keepdims=True)
                        norms[norms == 0] = 1.0
                        embs_norm = embs_np / norms
                        all_embeddings.extend([embs_norm[k] for k in range(len(processed_chunk))])
                except Exception as e:
                    if HAS_TORCH and "cuda" in self.device:
                        torch.cuda.empty_cache()
                    # Fallback to single item extraction if chunk OOMs
                    for pcm in processed_chunk:
                        all_embeddings.append(self.extract_embedding_from_pcm(pcm, samplerate))
                finally:
                    if HAS_TORCH and "cuda" in self.device:
                        torch.cuda.empty_cache()

            return all_embeddings
        else:
            return [self.extract_embedding_from_pcm(p, samplerate) for p in pcm_slices]

    def compute_acoustic_biomarkers(
        self, pcm_samples: np.ndarray, samplerate: int = 16000, word_count: int = 0
    ) -> AcousticBiomarkers:
        """Extract vocal stress indicators (RMS energy, F0 pitch estimate, vocal strain)."""
        if len(pcm_samples) == 0:
            return AcousticBiomarkers(0.0, 0.0, 0.0, 0.0, 0.0)

        # 1. RMS Energy
        rms = float(np.sqrt(np.mean(np.square(pcm_samples))))

        # 2. Approximate F0 pitch via multi-frame autocorrelation in human speech range (60-450 Hz)
        pitches = []
        n_samples = len(pcm_samples)
        frame_len = 2048
        
        # Sample up to 5 points across the speech segment to find voiced segments
        for pct in [0.2, 0.4, 0.5, 0.6, 0.8]:
            idx = int(pct * n_samples)
            frame = pcm_samples[max(0, idx - frame_len // 2) : min(n_samples, idx + frame_len // 2)]
            if len(frame) < frame_len:
                continue
            
            # Remove DC offset to prevent slow-decay envelope
            frame = frame - np.mean(frame)
            
            fft_sig = np.fft.fft(frame, n=2048)
            corr = np.fft.ifft(fft_sig * np.conj(fft_sig)).real[:len(frame)]
            if corr[0] <= 0:
                continue
            corr = corr / corr[0]
            
            min_lag = 35
            max_lag = min(len(frame) - 1, 266)
            if max_lag > min_lag:
                search_region = corr[min_lag:max_lag]
                peak = np.argmax(search_region) + min_lag
                
                # Verify that it is a true local maximum and has significant autocorrelation energy
                if peak > min_lag and peak < max_lag - 1:
                    if corr[peak] > corr[peak - 1] and corr[peak] > corr[peak + 1]:
                        if corr[peak] > 0.20:
                            f0_candidate = float(samplerate / peak)
                            if 60.0 <= f0_candidate <= 450.0:
                                pitches.append(f0_candidate)
                                
        if pitches:
            f0 = float(np.median(pitches))
        else:
            f0 = 150.0

        # 3. Vocal Strain Index (high frequency ratio + RMS burst)
        high_freq_energy = np.sum(np.square(np.diff(pcm_samples)))
        vocal_strain = float(min(1.0, (high_freq_energy / (len(pcm_samples) + 1e-6)) * 50.0))

        # 4. Speech Rate (words per minute)
        duration_sec = len(pcm_samples) / float(samplerate)
        wpm = (word_count / (duration_sec / 60.0)) if duration_sec > 0.5 and word_count > 0 else 0.0

        return AcousticBiomarkers(
            rms_energy=round(rms, 4),
            pitch_f0_hz=round(f0, 1),
            pitch_variance=round(rms * 100.0, 2),
            vocal_strain_index=round(vocal_strain, 3),
            speech_rate_wpm=round(wpm, 1),
        )

    def compute_multi_centroids(
        self, sample_embeddings: List[np.ndarray], max_clusters: int = 5
    ) -> np.ndarray:
        """Clusters sample embeddings into at most max_clusters centroids using K-Means."""
        X = np.array(sample_embeddings)
        n_samples = len(X)
        if n_samples <= max_clusters:
            centroids = X
        else:
            try:
                from sklearn.cluster import KMeans
                n_clusters = min(max_clusters, n_samples)
                kmeans = KMeans(n_clusters=n_clusters, random_state=42, n_init='auto')
                kmeans.fit(X)
                centroids = kmeans.cluster_centers_
            except Exception as e:
                logger.warning(f"K-Means clustering failed ({e}). Falling back to simple average.")
                mean_vector = np.mean(X, axis=0, keepdims=True)
                centroids = mean_vector

        # L2-normalize each centroid
        norms = np.linalg.norm(centroids, axis=1, keepdims=True)
        centroids = np.where(norms > 0, centroids / norms, centroids)
        return centroids.astype(np.float32)

    def enroll_voice_vault(self, force_recompute: bool = False) -> Dict[str, np.ndarray]:
        """Scans profiles/<Actor_Name>/*.wav to compute canonical D-Vector centroids."""
        self.apply_schema_migrations()
        self.profiles_dir.mkdir(parents=True, exist_ok=True)

        conn = self._get_connection()
        cursor = conn.cursor()

        expected_dim = 192 if (self.classifier is not None and HAS_TORCH) else 129

        # Check existing profiles in database if not forcing recompute
        if not force_recompute:
            cursor.execute("SELECT actor_id, display_name, embedding_blob FROM speaker_profiles;")
            for row in cursor.fetchall():
                emb = np.frombuffer(row["embedding_blob"], dtype=np.float32)
                if len(emb) % expected_dim == 0 and len(emb) > 0:
                    self.enrolled_vault[row["actor_id"]] = emb.reshape(-1, expected_dim)
            if self.enrolled_vault:
                logger.info(f"Loaded {len(self.enrolled_vault)} enrolled actors from database cache ({expected_dim}-dim embeddings).")
            else:
                logger.info(f"Re-enrolling vault to match active model embedding dimension ({expected_dim}-dim)...")

        # Scan filesystem for new or updated profiles if vault is empty or force_recompute is active
        if force_recompute or not self.enrolled_vault:
            actor_dirs = [d for d in self.profiles_dir.iterdir() if d.is_dir()]
            logger.info(f"Scanning profiles directory: {self.profiles_dir} ({len(actor_dirs)} actor folders found)")

            for actor_dir in actor_dirs:
                actor_name = actor_dir.name
                audio_files = []
                for ext in ("*.wav", "*.mp3", "*.m4a", "*.flac", "*.ogg"):
                    audio_files.extend(list(actor_dir.glob(ext)))

                if not audio_files:
                    logger.warning(f"No audio sample files found in {actor_dir}. Skipping.")
                    continue

                sample_embeddings = []
                for audio_path in audio_files:
                    try:
                        data, sr = self.load_audio_pcm(audio_path, 16000)
                        emb = self.extract_embedding_from_pcm(data, sr)
                        sample_embeddings.append(emb)
                    except Exception as e:
                        logger.warning(f"Failed to extract embedding from {audio_path.name}: {e}")

                if sample_embeddings:
                    centroids = self.compute_multi_centroids(sample_embeddings, max_clusters=5)
                    self.enrolled_vault[actor_name] = centroids

                    # Store in database
                    cursor.execute(
                        """
                        INSERT OR REPLACE INTO speaker_profiles (actor_id, display_name, sample_count, embedding_blob, created_at)
                        VALUES (?, ?, ?, ?, ?)
                        """,
                        (
                            actor_name,
                            actor_name,
                            len(sample_embeddings),
                            centroids.tobytes(),
                            datetime.now().isoformat(),
                        ),
                    )
                    logger.info(f"  └── Enrolled [{actor_name}]: {len(sample_embeddings)} samples -> {len(centroids)} centroids computed.")

        conn.commit()
        conn.close()
        return self.enrolled_vault

    def self_train_enrichment(
        self,
        min_confidence: float = 0.77,
        max_pseudo_samples: int = 50,
        custom_thresholds: Optional[Dict[str, float]] = None,
    ) -> Dict[str, int]:
        """Enriches the profile centroids using high-confidence pseudo-labeled segments from the database.
        
        Saves the refined centroids back to speaker_profiles and updates self.enrolled_vault.
        """
        logger.info("🔮 Starting Semi-Supervised self-training profile enrichment...")
        logger.info(f"  └── Cosine similarity threshold: {min_confidence}")
        if custom_thresholds:
            logger.info(f"  └── Custom actor thresholds: {custom_thresholds}")
        logger.info(f"  └── Max pseudo-samples per speaker: {max_pseudo_samples}")

        if not self.enrolled_vault:
            logger.info("Enrolling voice vault first...")
            self.enroll_voice_vault()

        conn = self._get_connection()
        cursor = conn.cursor()

        expected_dim = 192 if (self.classifier is not None and HAS_TORCH) else 129
        # Load original sample counts and centroids
        cursor.execute("SELECT actor_id, sample_count, embedding_blob FROM speaker_profiles;")
        profile_info = {}
        for row in cursor.fetchall():
            emb = np.frombuffer(row["embedding_blob"], dtype=np.float32)
            if len(emb) % expected_dim == 0 and len(emb) > 0:
                emb = emb.reshape(-1, expected_dim)
            profile_info[row["actor_id"]] = {
                "sample_count": row["sample_count"],
                "embedding": emb
            }

        # Check records schema dynamically
        cursor.execute("PRAGMA table_info(records);")
        rec_cols = [r["name"] for r in cursor.fetchall()]
        id_col = "record_id" if "record_id" in rec_cols else "id"
        name_col = "name" if "name" in rec_cols else "file_name"
        dir_col = "directory" if "directory" in rec_cols else "file_path"

        enrichment_stats = {}

        for actor in list(self.enrolled_vault.keys()):
            if "SPEAKER_" in actor or actor == "Speaker Unknown" or actor == "Speaker ThirdParty":
                continue

            # Determine threshold for this specific actor
            actor_threshold = min_confidence
            if custom_thresholds and actor in custom_thresholds:
                actor_threshold = custom_thresholds[actor]

            # Query high confidence matches in speeches table
            cursor.execute(
                f"""
                SELECT s.id, s.record_id, s.offset_ms, s.duration_ms, r.{dir_col} AS directory, r.{name_col} AS name
                FROM speeches s
                JOIN records r ON s.record_id = r.{id_col}
                WHERE (s.speaker_tag = ? OR s.speaker_disclosed = ?) AND s.speaker_confidence >= ?
                ORDER BY s.speaker_confidence DESC
                LIMIT ?
                """,
                (actor, actor, actor_threshold, max_pseudo_samples)
            )
            rows = cursor.fetchall()
            if not rows:
                logger.info(f"  └── [{actor}]: 0 segments found (confidence >= {actor_threshold}).")
                continue

            logger.info(f"  └── [{actor}]: Found {len(rows)} segments (confidence >= {actor_threshold}). Loading audio & extracting embeddings...")

            # Group segments by record_id to minimize audio file reads
            records_dict = {}
            for r in rows:
                key = (r["directory"], r["name"])
                if key not in records_dict:
                    records_dict[key] = []
                records_dict[key].append(r)

            new_embeddings = []
            for (dir_path, name), segments in records_dict.items():
                audio_path = Path(dir_path) / name
                if not audio_path.exists():
                    audio_path = Path(name)
                    if not audio_path.exists():
                        logger.warning(f"      ⚠️ Could not find audio file {name}. Skipping.")
                        continue
                try:
                    data, sr = self.load_audio_pcm(audio_path, 16000)
                except Exception as e:
                    logger.warning(f"      ⚠️ Could not load audio {name} for self-training: {e}")
                    continue

                pcm_slices = []
                for seg in segments:
                    offset_ms = seg["offset_ms"] or 0
                    duration_ms = seg["duration_ms"] or 1000
                    start_sample = int((offset_ms / 1000.0) * sr)
                    end_sample = start_sample + int((duration_ms / 1000.0) * sr)
                    start_sample = max(0, min(start_sample, len(data) - 1))
                    end_sample = max(start_sample + 100, min(end_sample, len(data)))
                    slice_pcm = data[start_sample:end_sample]
                    if len(slice_pcm) < int(0.25 * sr):
                        continue
                    pcm_slices.append(slice_pcm)

                if pcm_slices:
                    embs = self.extract_embeddings_batch(pcm_slices, sr)
                    new_embeddings.extend(embs)

            if not new_embeddings:
                logger.info(f"  └── [{actor}]: Failed to extract new embeddings from any of the {len(rows)} segments.")
                continue

            # Calculate enriched centroids using the pooled set of original centroids + new embeddings
            orig_data = profile_info.get(actor, {"sample_count": 4, "embedding": self.enrolled_vault[actor]})
            orig_count = orig_data["sample_count"]
            orig_emb = orig_data["embedding"]

            # Reconstruct the pool of vectors
            pool = []
            if orig_emb.ndim == 1:
                pool.append(orig_emb)
            else:
                pool.extend(list(orig_emb))
            pool.extend(new_embeddings)

            # Compute new centroids from the pool
            new_centroids = self.compute_multi_centroids(pool, max_clusters=5)
            new_count = orig_count + len(new_embeddings)

            # Update speaker_profiles table
            cursor.execute(
                """
                INSERT OR REPLACE INTO speaker_profiles (actor_id, display_name, sample_count, embedding_blob, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (actor, actor, new_count, new_centroids.tobytes(), datetime.now().isoformat())
            )

            self.enrolled_vault[actor] = new_centroids
            enrichment_stats[actor] = len(new_embeddings)
            logger.info(f"  └── 🎉 Enriched [{actor}] with {len(new_embeddings)} segments. Centroids updated (total samples: {new_count}, centroids: {len(new_centroids)}).")

        conn.commit()
        conn.close()
        logger.info(f"✨ Self-Training Profile Enrichment complete! Stats: {enrichment_stats}")
        return enrichment_stats

    def match_speaker(self, query_emb: np.ndarray) -> MatchResult:
        """Evaluate cosine similarity against enrolled actors with ambiguity resolution."""
        if not self.enrolled_vault:
            return MatchResult("SPEAKER_UNENROLLED", 0.0, False)

        best_actor = "SPEAKER_THIRD_PARTY"
        best_score = -1.0
        second_best_actor = None
        second_best_score = -1.0

        for actor, ref_emb in self.enrolled_vault.items():
            # Support both 1D (legacy single centroid) and 2D (multi-centroid matrix) reference shapes
            if ref_emb.ndim == 1:
                score = float(np.dot(query_emb, ref_emb))
            else:
                scores = np.dot(ref_emb, query_emb)
                score = float(np.max(scores))

            if score > best_score:
                second_best_score = best_score
                second_best_actor = best_actor
                best_score = score
                best_actor = actor
            elif score > second_best_score:
                second_best_score = score
                second_best_actor = actor

        is_ambiguous = (best_score - second_best_score) < self.ambiguity_margin if second_best_score > 0 else False

        threshold = self.match_threshold
        if best_actor in self.actor_thresholds:
            threshold = self.actor_thresholds[best_actor]

        if best_score >= threshold:
            if is_ambiguous:
                return MatchResult(
                    actor_tag=f"{best_actor}_AMBIGUOUS",
                    confidence=round(best_score, 3),
                    is_ambiguous=True,
                    second_best_actor=second_best_actor,
                    second_best_score=round(second_best_score, 3),
                )
            return MatchResult(actor_tag=best_actor, confidence=round(best_score, 3), is_ambiguous=False)

        return MatchResult(
            actor_tag="SPEAKER_THIRD_PARTY",
            confidence=round(best_score, 3),
            is_ambiguous=is_ambiguous,
            second_best_actor=best_actor,
            second_best_score=round(best_score, 3),
        )

    def process_all_database_speeches(
        self,
        record_id: Optional[str] = None,
        limit: Optional[int] = None,
        dry_run: bool = False,
        force: bool = False,
        reclassify_unmatched: bool = False,
    ) -> Dict[str, Any]:
        """Iterates over database records, slices audio, tags speakers and computes biomarkers.
        
        Features:
        - Resumable: Skips already processed records unless force=True.
        - Immediate Checkpointing: Commits to SQLite per record so Ctrl+C never loses work.
        - Transparent Progress: Shows real-time tqdm progress bar, per-record details, & ETA.
        """
        if not self.enrolled_vault:
            logger.info("Enrolling voice vault first...")
            self.enroll_voice_vault()

        conn = self._get_connection()
        cursor = conn.cursor()

        # Check table columns dynamically
        cursor.execute("PRAGMA table_info(records);")
        rec_cols = [row["name"] for row in cursor.fetchall()]
        id_col = "record_id" if "record_id" in rec_cols else "id"
        name_col = "name" if "name" in rec_cols else "file_name"
        dir_col = "directory" if "directory" in rec_cols else "file_path"
        has_part_disc = "participants_disclosed_json" in rec_cols

        cursor.execute("PRAGMA table_info(speeches);")
        speech_cols = [row["name"] for row in cursor.fetchall()]
        text_col = "script" if "script" in speech_cols else "text"

        order_cols = []
        if "priority" in rec_cols:
            order_cols.append("priority DESC")
        if "pattern_match_score" in rec_cols:
            order_cols.append("pattern_match_score DESC")
        if "intensity_rating" in rec_cols:
            order_cols.append("intensity_rating DESC")
        if "speech_count" in rec_cols:
            order_cols.append("speech_count DESC")
        order_clause = f" ORDER BY {', '.join(order_cols)}" if order_cols else ""

        if reclassify_unmatched:
            query_records = f"""
                SELECT DISTINCT r.{id_col} AS record_id, r.{dir_col} AS directory, r.{name_col} AS name
                {f", r.participants_disclosed_json" if has_part_disc else ""}
                FROM records r
                JOIN speeches s ON r.{id_col} = s.record_id
                WHERE r.state IN ('Done', 'TriagedHighInterest', 'NLP_DONE', 'Transcribed')
                  AND r.{dir_col} NOT LIKE '%#recycle%'
                  AND r.{name_col} NOT LIKE '%#recycle%'
                  AND (s.speaker_tag = 'SPEAKER_THIRD_PARTY' OR s.speaker_tag IS NULL OR s.speaker_tag = '' OR s.speaker_tag LIKE 'Speaker%')
            """
        else:
            query_records = f"""
                SELECT {id_col} AS record_id, {dir_col} AS directory, {name_col} AS name
                {f", participants_disclosed_json" if has_part_disc else ""}
                FROM records
                WHERE state IN ('Done', 'TriagedHighInterest', 'NLP_DONE', 'Transcribed')
                  AND {dir_col} NOT LIKE '%#recycle%'
                  AND {name_col} NOT LIKE '%#recycle%'
            """
        if record_id:
            query_records += f" AND {id_col} = '{record_id}'"
        
        query_records += order_clause

        logger.info("🔥 Priority Sorting Active: Excluded #recycle bin files. Prioritizing high-interest evidence tracks (priority, legal score, intensity, speech density).")
        df_records_all = pl.read_database(query_records, conn)
        total_candidate_count = len(df_records_all)

        # Filter out already processed records for resumable execution unless force=True
        if not force and not reclassify_unmatched and has_part_disc and not record_id:
            df_records = df_records_all.filter(
                (pl.col("participants_disclosed_json").is_null()) | 
                (pl.col("participants_disclosed_json") == "")
            )
            already_done_count = total_candidate_count - len(df_records)
            if already_done_count > 0:
                logger.info(f"⏩ Resumable Checkpoint: {already_done_count}/{total_candidate_count} records already processed (Skipped).")
        else:
            df_records = df_records_all

        if limit:
            df_records = df_records.head(limit)

        records_to_process = len(df_records)
        logger.info(f"🎯 Total records remaining to process: {records_to_process} / {total_candidate_count}")

        if records_to_process == 0:
            logger.info("✨ All records are already processed! (Use --force to re-process).")
            conn.close()
            return {
                "total_records_processed": 0,
                "total_speeches_tagged": 0,
                "actor_distribution": {},
                "dry_run": dry_run,
                "resumed_skipped": total_candidate_count,
            }

        total_speeches_tagged = 0
        records_completed = 0
        actor_distribution: Dict[str, int] = {}

        # Setup progress bar
        pbar = tqdm(
            total=records_to_process,
            desc="🔊 Biometric Matching",
            unit="record",
            dynamic_ncols=True,
            disable=not self.verbose,
        )

        actor_id_map = {actor: f"Speaker {idx+1:02d}" for idx, actor in enumerate(sorted(self.enrolled_vault.keys()))}
        interrupted = False

        try:
            for idx, row in enumerate(df_records.iter_rows(named=True), start=1):
                rec_id = row["record_id"]
                rec_name = row["name"]
                audio_path = Path(row["directory"]) / rec_name

                # Parse year from filename to enforce timeline constraints
                record_year = None
                year_match = re.search(r"\b(20\d{2})\b", rec_name)
                if year_match:
                    record_year = int(year_match.group(1))

                if not audio_path.exists():
                    audio_path = Path(rec_name)
                    if not audio_path.exists():
                        pbar.update(1)
                        continue

                pbar.set_postfix_str(f"Decoding {rec_name[:22]}...")
                try:
                    data, sr = self.load_audio_pcm(audio_path, 16000)
                except Exception as e:
                    if self.verbose:
                        logger.warning(f"Could not read audio file {rec_name}: {e}")
                    pbar.update(1)
                    continue

                if "offset_ms" in speech_cols and "duration_ms" in speech_cols:
                    time_select = "offset_ms, duration_ms"
                    order_by = "offset_ms ASC"
                else:
                    time_select = "CAST(start_time * 1000 AS INTEGER) AS offset_ms, CAST((end_time - start_time) * 1000 AS INTEGER) AS duration_ms"
                    order_by = "start_time ASC"

                unmatched_clause = ""
                if reclassify_unmatched:
                    unmatched_clause = "AND (speaker_tag = 'SPEAKER_THIRD_PARTY' OR speaker_tag IS NULL OR speaker_tag = '' OR speaker_tag LIKE 'Speaker%')"

                query_speeches = f"""
                    SELECT id, {time_select}, {text_col} AS text
                    FROM speeches
                    WHERE record_id = '{rec_id}' {unmatched_clause}
                    ORDER BY {order_by}
                """
                df_speeches = pl.read_database(query_speeches, conn)
                total_speeches = len(df_speeches)

                speech_items = []
                pcm_slices = []

                for spk in df_speeches.iter_rows(named=True):
                    speech_id = spk["id"]
                    offset_ms = spk["offset_ms"] or 0
                    duration_ms = spk["duration_ms"] or 1000
                    text = spk["text"] or ""
                    word_count = len(text.split())

                    start_sample = int((offset_ms / 1000.0) * sr)
                    end_sample = start_sample + int((duration_ms / 1000.0) * sr)
                    start_sample = max(0, min(start_sample, len(data) - 1))
                    end_sample = max(start_sample + 100, min(end_sample, len(data)))

                    slice_pcm = data[start_sample:end_sample]
                    if len(slice_pcm) < int(0.25 * sr):  # < 250ms
                        continue

                    speech_items.append((speech_id, word_count, slice_pcm))
                    pcm_slices.append(slice_pcm)

                pbar.set_postfix_str(f"{rec_name[:14]} (CUDA matching {len(pcm_slices)} spk...)")
                embeddings = self.extract_embeddings_batch(pcm_slices, sr)

                record_actors = set()
                speech_updates = []
                stress_values = []

                for (speech_id, word_count, slice_pcm), emb in zip(speech_items, embeddings):
                    match = self.match_speaker(emb)
                    clean_actor = match.actor_tag.replace("_AMBIGUOUS", "")
                    
                    # Apply actor timeline constraints (e.g. Dinda did not exist before 2020)
                    if record_year is not None and clean_actor in self.actor_start_years:
                        start_year = self.actor_start_years[clean_actor]
                        if record_year < start_year:
                            match = MatchResult("SPEAKER_THIRD_PARTY", match.confidence, match.is_ambiguous)
                            clean_actor = "SPEAKER_THIRD_PARTY"

                    biomarkers = self.compute_acoustic_biomarkers(slice_pcm, sr, word_count)
                    stress_values.append(biomarkers.vocal_strain_index)

                    if "SPEAKER_" not in clean_actor:
                        record_actors.add(clean_actor)

                    actor_distribution[clean_actor] = actor_distribution.get(clean_actor, 0) + 1
                    total_speeches_tagged += 1

                    anonymized_tag = actor_id_map.get(clean_actor, "Speaker ThirdParty" if "THIRD_PARTY" in clean_actor else "Speaker Unknown")
                    disclosed_tag = match.actor_tag

                    speech_updates.append(
                        (
                            anonymized_tag,
                            disclosed_tag,
                            disclosed_tag,
                            match.confidence,
                            json.dumps(asdict(biomarkers)),
                            speech_id,
                        )
                    )

                if not dry_run and speech_updates:
                    cursor.executemany(
                        """
                        UPDATE speeches 
                        SET speaker_anonymized = ?, speaker_disclosed = ?, speaker_tag = ?, speaker_confidence = ?, biomarkers_json = ?
                        WHERE id = ?
                        """,
                        speech_updates,
                    )

                    # Load all speaker tags for the record to have the full picture (combining matched & reclassified)
                    cursor.execute(
                        f"SELECT DISTINCT speaker_tag FROM speeches WHERE record_id = ?",
                        (rec_id,)
                    )
                    all_tags = {r[0] for r in cursor.fetchall() if r[0]}
                    
                    # Merge newly matched actors with previously matched ones
                    record_actors = set()
                    for t in all_tags:
                        clean_t = t.replace("_AMBIGUOUS", "")
                        if "SPEAKER_" not in clean_t and "Speaker" not in clean_t:
                            record_actors.add(clean_t)

                    cursor.execute(
                        f"SELECT biomarkers_json FROM speeches WHERE record_id = ?",
                        (rec_id,)
                    )
                    stress_values = []
                    for row_bm in cursor.fetchall():
                        if row_bm[0]:
                            try:
                                b_data = json.loads(row_bm[0])
                                if "vocal_strain_index" in b_data:
                                    stress_values.append(b_data["vocal_strain_index"])
                            except Exception:
                                pass

                    mean_stress = round(float(np.mean(stress_values)), 3) if stress_values else 0.0
                    disclosed_actors = sorted(list(record_actors))
                    anonymized_actors = sorted(list({actor_id_map.get(a, "Speaker ThirdParty") for a in record_actors}))

                    cursor.execute(
                        f"""
                        UPDATE records 
                        SET participants_anonymized_json = ?, participants_disclosed_json = ?, participants_json = ?, stress_index = ?
                        WHERE {id_col} = ?
                        """,
                        (
                            json.dumps(anonymized_actors, ensure_ascii=False),
                            json.dumps(disclosed_actors, ensure_ascii=False),
                            json.dumps(disclosed_actors, ensure_ascii=False),
                            mean_stress,
                            rec_id,
                        ),
                    )
                    # Immediate Checkpoint Commit per record
                    conn.commit()

                records_completed += 1
                pbar.update(1)
                pbar.set_postfix({
                    "Tagged": total_speeches_tagged,
                    "Actors": len(record_actors),
                    "File": rec_name[:18]
                })

                if self.verbose and records_completed % 10 == 0:
                    actors_str = ", ".join(sorted(record_actors)) if record_actors else "None"
                    tqdm.write(
                        f"  [✓ {idx}/{records_to_process}] {rec_name[:35]} -> {len(speech_updates)} speeches | Actors: [{actors_str}]"
                    )

        except KeyboardInterrupt:
            interrupted = True
            pbar.close()
            logger.warning("\n" + "=" * 70)
            logger.warning("⚠️  PROCESS INTERRUPTED BY USER (KeyboardInterrupt / Ctrl+C)")
            logger.warning(f"💾 Checkpoint Saved: {records_completed} records were processed & committed.")
            logger.warning("▶️  Run the command again anytime to seamlessly resume from where you left off!")
            logger.warning("=" * 70 + "\n")
        finally:
            if not interrupted:
                pbar.close()
            conn.close()

        summary = {
            "total_records_processed": records_completed,
            "total_speeches_tagged": total_speeches_tagged,
            "actor_distribution": actor_distribution,
            "dry_run": dry_run,
            "interrupted": interrupted,
        }
        
        if not interrupted:
            logger.info(f"🎉 Speaker identification completed: {records_completed} records processed, {total_speeches_tagged} speeches tagged.")
            if actor_distribution:
                logger.info(f"📊 Actor Distribution: {actor_distribution}")

        return summary


    def export_candidate_samples(
        self, out_dir: str = "profiles/_candidate_samples", max_samples: int = 15, source_file: Optional[str] = None
    ) -> int:
        """Helper to auto-slice 3s-10s clear speech samples from database records or a targeted audio file."""
        target_path = Path(out_dir)
        target_path.mkdir(parents=True, exist_ok=True)
        exported_cnt = 0

        if source_file:
            audio_path = Path(source_file)
            if not audio_path.exists():
                logger.error(f"Source file for candidate export does not exist: {source_file}")
                return 0

            try:
                logger.info(f"🎙️ Full-Timeline Acoustic Sampling for: {audio_path.name}")
                data, sr = self.load_audio_pcm(audio_path, 16000)
                total_duration_sec = len(data) / float(sr)
                logger.info(f"  └── Total audio duration: {total_duration_sec / 60.0:.2f} minutes ({total_duration_sec:.1f} seconds)")

                window_sec = 5.0
                window_samples = int(window_sec * sr)
                step_sec = 2.5
                step_samples = int(step_sec * sr)

                if len(data) < window_samples:
                    logger.warning("Audio file too short for multi-window sampling.")
                    return 0

                # 1. Dense sliding window analysis across the entire timeline
                candidates = []
                prev_spec = None

                for start_sample in range(0, len(data) - window_samples, step_samples):
                    end_sample = start_sample + window_samples
                    chunk_pcm = data[start_sample:end_sample]
                    rms = float(np.sqrt(np.mean(chunk_pcm**2)))

                    # Skip silent background (< 0.008 RMS)
                    if rms < 0.008:
                        continue

                    # Compute spectral timbre fingerprint
                    fft_vals = np.abs(np.fft.rfft(chunk_pcm, n=256))
                    norm = np.linalg.norm(fft_vals)
                    spec = (fft_vals / norm) if norm > 0 else fft_vals

                    spec_delta = 0.0
                    if prev_spec is not None:
                        spec_delta = float(np.linalg.norm(spec - prev_spec))
                    prev_spec = spec

                    # Composite acoustic dynamic score (RMS energy + voice transition shift)
                    score = (rms * 0.6) + (spec_delta * 0.4)

                    candidates.append({
                        "start_sample": start_sample,
                        "end_sample": end_sample,
                        "start_sec": start_sample / float(sr),
                        "end_sec": end_sample / float(sr),
                        "rms": rms,
                        "spec_delta": spec_delta,
                        "score": score,
                        "pcm": chunk_pcm,
                    })

                if not candidates:
                    logger.warning("No speech activity detected above energy threshold.")
                    return 0

                target_num = max_samples if max_samples > 0 else 20
                logger.info(f"  └── Evaluated {len(candidates)} active speech windows. Selecting top {target_num} across full timeline...")

                # 2. Partition timeline into N equal temporal buckets for uniform coverage
                selected_samples = []
                bucket_size_sec = total_duration_sec / float(target_num)

                for b in range(target_num):
                    b_start = b * bucket_size_sec
                    b_end = (b + 1) * bucket_size_sec

                    # Find candidates within this time bucket
                    bucket_candidates = [
                        c for c in candidates if b_start <= c["start_sec"] < b_end
                    ]

                    if bucket_candidates:
                        # Pick the candidate with highest acoustic dynamic score in this bucket
                        best_cand = max(bucket_candidates, key=lambda x: x["score"])
                        selected_samples.append(best_cand)

                # Fallback if some buckets were empty: fill up to target_num using remaining top-scoring candidates
                if len(selected_samples) < target_num:
                    selected_starts = {s["start_sec"] for s in selected_samples}
                    remaining = [c for c in candidates if c["start_sec"] not in selected_starts]
                    remaining.sort(key=lambda x: x["score"], reverse=True)
                    needed = target_num - len(selected_samples)
                    selected_samples.extend(remaining[:needed])

                # Sort selected samples chronologically
                selected_samples.sort(key=lambda x: x["start_sec"])

                # 3. Export samples to output directory with human-readable timestamps
                stem = audio_path.stem[:18].replace(" ", "_")
                for idx, item in enumerate(selected_samples, start=1):
                    start_m, start_s = divmod(int(item["start_sec"]), 60)
                    end_m, end_s = divmod(int(item["end_sec"]), 60)
                    time_tag = f"{start_m:02d}m{start_s:02d}s-{end_m:02d}m{end_s:02d}s"

                    out_file = target_path / f"{stem}_Sample_{idx:02d}_{time_tag}_RMS{item['rms']:.3f}.wav"
                    sf.write(str(out_file), item["pcm"], sr)
                    exported_cnt += 1
                    logger.info(f"  🎙️ Sample {idx:02d}/{target_num:02d} -> [{out_file.name}] at {start_m:02d}:{start_s:02d} (RMS: {item['rms']:.3f}, Shift: {item['spec_delta']:.3f})")

            except Exception as e:
                logger.error(f"Failed to slice candidate samples from {source_file}: {e}")

            logger.info(f"✨ Successfully exported {exported_cnt} timeline-spanning candidate samples to '{target_path}'.")
            return exported_cnt

        conn = self._get_connection()
        cursor = conn.cursor()
        
        cursor.execute("PRAGMA table_info(records);")
        rec_cols = [row["name"] for row in cursor.fetchall()]
        id_col = "record_id" if "record_id" in rec_cols else "id"
        name_col = "name" if "name" in rec_cols else "file_name"
        dir_col = "directory" if "directory" in rec_cols else "file_path"

        cursor.execute(f"""
            SELECT s.id, s.record_id, s.script, s.offset_ms, s.duration_ms, r.{dir_col} AS directory, r.{name_col} AS name
            FROM speeches s
            JOIN records r ON s.record_id = r.{id_col}
            WHERE s.duration_ms BETWEEN 3000 AND 10000 AND s.script IS NOT NULL AND s.script != ''
            ORDER BY RANDOM()
            LIMIT {max_samples}
        """)
        rows = cursor.fetchall()

        for row in rows:
            audio_path = Path(row["directory"]) / row["name"]
            if not audio_path.exists():
                audio_path = Path(row["name"])
                if not audio_path.exists():
                    continue

            try:
                data, sr = self.load_audio_pcm(audio_path, 16000)
                
                offset_ms = row["offset_ms"] or 0
                duration_ms = row["duration_ms"] or 3000
                start_sample = int((offset_ms / 1000.0) * sr)
                end_sample = start_sample + int((duration_ms / 1000.0) * sr)
                slice_pcm = data[start_sample:end_sample]

                raw_script = row["script"] or "speech"
                clean_text = "".join(c for c in raw_script[:25] if c.isalnum() or c in (' ', '_')).strip().replace(' ', '_')
                out_file = target_path / f"Sample_{row['id']}_{clean_text}.wav"
                sf.write(str(out_file), slice_pcm, sr)
                exported_cnt += 1
                logger.info(f"  🎙️ Exported sample [{out_file.name}]: '{raw_script}'")
            except Exception as e:
                logger.warning(f"Could not export speech {row['id']}: {e}")

        conn.close()
        logger.info(f"✨ Successfully exported {exported_cnt} candidate audio samples to '{target_path}'.")
        logger.info("💡 Next steps: Listen to files in 'profiles/_candidate_samples/', create 'profiles/<Speaker_Name>/' folders, move the files there, and re-run enrollment!")
        return exported_cnt

    # -----------------------------------------------------------------------
    # Actor-Centric Speech Clustering & Data Science Exporter
    # -----------------------------------------------------------------------
    def export_actor_clusters(
        self,
        output_dir: str = "export/actor_clusters",
        min_confidence: float = 0.70,
    ) -> int:
        """Aggregate all identified speech segments by speaker and write per-actor data portfolios.

        For each actor identified in the database this method produces three files inside
        `output_dir/{actor_tag}/`:

        * ``{actor_tag}_speeches.csv`` — flat tabular dataset ready for Pandas / Polars / R.
        * ``{actor_tag}_portfolio.json`` — rich nested document with aggregate stats and speech history.
        * ``{actor_tag}_longitudinal_summary.txt`` — year-by-year vocal metric report.

        Args:
            output_dir: Root directory where actor sub-folders will be created.
            min_confidence: Minimum biometric confidence to include a segment (0.0–1.0).

        Returns:
            Total number of speech segments exported across all actors.
        """
        import re
        import csv

        out_root = Path(output_dir)
        out_root.mkdir(parents=True, exist_ok=True)

        DATE_PATTERNS = [
            re.compile(r"(\d{4})[-_](\d{2})[-_](\d{2})[_T ](\d{2})[-_:h](\d{2})"),  # full datetime
            re.compile(r"(\d{4})[-_](\d{2})[-_](\d{2})"),  # date only
        ]

        def _parse_date(filename: str, fallback: str) -> str:
            """Extract ISO-8601 recording date from a filename, falling back to DB timestamp."""
            for pat in DATE_PATTERNS:
                m = pat.search(filename)
                if m:
                    groups = m.groups()
                    if len(groups) >= 5:
                        return f"{groups[0]}-{groups[1]}-{groups[2]} {groups[3]}:{groups[4]}:00"
                    return f"{groups[0]}-{groups[1]}-{groups[2]} 00:00:00"
            return fallback or ""

        conn = self._get_connection()
        cursor = conn.cursor()

        # Collect all distinct speaker tags with at least one high-confidence segment.
        cursor.execute(
            """
            SELECT DISTINCT speaker_tag
            FROM speeches
            WHERE speaker_tag IS NOT NULL
              AND speaker_tag NOT IN ('SPEAKER_THIRD_PARTY', 'NULL', '')
              AND (speaker_confidence IS NULL OR speaker_confidence >= ?)
            ORDER BY speaker_tag
            """,
            (min_confidence,),
        )
        actors = [row["speaker_tag"] for row in cursor.fetchall()]

        if not actors:
            logger.warning("No identified actors found in the database. Run enrollment first.")
            conn.close()
            return 0

        logger.info(f"Found {len(actors)} actors to cluster: {actors}")
        total_exported = 0

        for actor_tag in actors:
            cursor.execute(
                """
                SELECT
                    s.id              AS speech_id,
                    s.record_id,
                    r.name            AS audio_filename,
                    r.directory       AS audio_directory,
                    r.created_at      AS record_created_at,
                    s.offset_ms       AS start_ms,
                    s.duration_ms,
                    s.script          AS transcript,
                    s.speaker_confidence AS confidence,
                    s.biomarkers_json
                FROM speeches s
                JOIN records r ON r.record_id = s.record_id
                WHERE s.speaker_tag = ?
                  AND (s.speaker_confidence IS NULL OR s.speaker_confidence >= ?)
                ORDER BY r.created_at ASC, s.offset_ms ASC
                """,
                (actor_tag, min_confidence),
            )
            rows = cursor.fetchall()

            if not rows:
                continue

            # Build flat records with parsed biomarkers and dates.
            flat_rows: List[Dict[str, Any]] = []
            for row in rows:
                bm: Dict[str, Any] = {}
                if row["biomarkers_json"]:
                    try:
                        bm = json.loads(row["biomarkers_json"])
                    except json.JSONDecodeError:
                        pass

                recording_date = _parse_date(
                    row["audio_filename"] or "",
                    row["record_created_at"] or "",
                )
                year = recording_date[:4] if recording_date else "unknown"

                audio_path = ""
                if row["audio_directory"] and row["audio_filename"]:
                    audio_path = f"{row['audio_directory']}/{row['audio_filename']}"

                flat_rows.append({
                    "speech_id": row["speech_id"],
                    "record_id": row["record_id"],
                    "audio_file_path": audio_path,
                    "recording_date": recording_date,
                    "year": year,
                    "start_ms": row["start_ms"] or 0,
                    "end_ms": (row["start_ms"] or 0) + (row["duration_ms"] or 0),
                    "duration_ms": row["duration_ms"] or 0,
                    "transcript": row["transcript"] or "",
                    "confidence": row["confidence"] or 0.0,
                    "rms_energy": bm.get("rms_energy", 0.0),
                    "pitch_f0_hz": bm.get("pitch_f0_hz", 0.0),
                    "pitch_variance": bm.get("pitch_variance", 0.0),
                    "vocal_strain_index": bm.get("vocal_strain_index", 0.0),
                    "speech_rate_wpm": bm.get("speech_rate_wpm", 0.0),
                })

            actor_dir = out_root / actor_tag
            actor_dir.mkdir(parents=True, exist_ok=True)

            # --- 1. Write CSV ---------------------------------------------------
            csv_path = actor_dir / f"{actor_tag}_speeches.csv"
            fieldnames = list(flat_rows[0].keys()) if flat_rows else []
            with open(csv_path, "w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(flat_rows)
            logger.info(f"[{actor_tag}] Wrote {len(flat_rows)} rows → {csv_path}")

            # --- 2. Compute aggregate stats for JSON portfolio and TXT report ---
            def _safe_mean(values: List[float]) -> float:
                non_zero = [v for v in values if v > 0]
                return float(np.mean(non_zero)) if non_zero else 0.0

            def _safe_std(values: List[float]) -> float:
                non_zero = [v for v in values if v > 0]
                return float(np.std(non_zero)) if len(non_zero) > 1 else 0.0

            pitches = [r["pitch_f0_hz"] for r in flat_rows]
            strains = [r["vocal_strain_index"] for r in flat_rows]
            rates   = [r["speech_rate_wpm"] for r in flat_rows]
            confs   = [r["confidence"] for r in flat_rows]

            aggregate = {
                "total_segments": len(flat_rows),
                "mean_confidence": _safe_mean(confs),
                "pitch_f0_mean_hz": _safe_mean(pitches),
                "pitch_f0_std_hz": _safe_std(pitches),
                "vocal_strain_mean": _safe_mean(strains),
                "vocal_strain_std": _safe_std(strains),
                "speech_rate_mean_wpm": _safe_mean(rates),
                "speech_rate_std_wpm": _safe_std(rates),
            }

            # Year-by-year breakdown
            year_groups: Dict[str, List[Dict[str, Any]]] = {}
            for r in flat_rows:
                year_groups.setdefault(r["year"], []).append(r)

            yearly_stats: Dict[str, Dict[str, float]] = {}
            for yr, yr_rows in sorted(year_groups.items()):
                yr_strains = [r["vocal_strain_index"] for r in yr_rows]
                yr_rates   = [r["speech_rate_wpm"] for r in yr_rows]
                yr_pitches = [r["pitch_f0_hz"] for r in yr_rows]
                yearly_stats[yr] = {
                    "segment_count": len(yr_rows),
                    "pitch_f0_mean_hz": _safe_mean(yr_pitches),
                    "vocal_strain_mean": _safe_mean(yr_strains),
                    "speech_rate_mean_wpm": _safe_mean(yr_rates),
                }

            # --- 3. JSON Portfolio --------------------------------------------
            portfolio = {
                "actor_tag": actor_tag,
                "exported_at": datetime.utcnow().isoformat() + "Z",
                "min_confidence_filter": min_confidence,
                "aggregate": aggregate,
                "yearly_breakdown": yearly_stats,
                "speeches": [
                    {
                        "speech_id": r["speech_id"],
                        "record_id": r["record_id"],
                        "audio_file_path": r["audio_file_path"],
                        "recording_date": r["recording_date"],
                        "start_ms": r["start_ms"],
                        "end_ms": r["end_ms"],
                        "duration_ms": r["duration_ms"],
                        "confidence": r["confidence"],
                        "transcript": r["transcript"],
                        "biomarkers": {
                            "rms_energy": r["rms_energy"],
                            "pitch_f0_hz": r["pitch_f0_hz"],
                            "pitch_variance": r["pitch_variance"],
                            "vocal_strain_index": r["vocal_strain_index"],
                            "speech_rate_wpm": r["speech_rate_wpm"],
                        },
                    }
                    for r in flat_rows
                ],
            }

            json_path = actor_dir / f"{actor_tag}_portfolio.json"
            with open(json_path, "w", encoding="utf-8") as f:
                json.dump(portfolio, f, ensure_ascii=False, indent=2)
            logger.info(f"[{actor_tag}] Portfolio JSON → {json_path}")

            # --- 4. Longitudinal Summary TXT ----------------------------------
            BASELINE_YEAR = sorted(year_groups.keys())[0] if year_groups else None
            baseline_strain = yearly_stats.get(BASELINE_YEAR, {}).get("vocal_strain_mean", 0.0) if BASELINE_YEAR else 0.0

            lines: List[str] = [
                f"=" * 72,
                f"LONGITUDINAL VOCAL ANALYSIS REPORT — Actor: {actor_tag}",
                f"Generated: {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}",
                f"=" * 72,
                "",
                f"Total speech segments (confidence ≥ {min_confidence:.0%}): {aggregate['total_segments']}",
                f"Mean identification confidence : {aggregate['mean_confidence']:.3f}",
                "",
                "GLOBAL VOCAL BASELINES",
                "-" * 40,
                f"  Pitch F0        : {aggregate['pitch_f0_mean_hz']:.1f} Hz  (σ={aggregate['pitch_f0_std_hz']:.1f})",
                f"  Vocal Strain    : {aggregate['vocal_strain_mean']:.4f}  (σ={aggregate['vocal_strain_std']:.4f})",
                f"  Speech Rate     : {aggregate['speech_rate_mean_wpm']:.1f} WPM  (σ={aggregate['speech_rate_std_wpm']:.1f})",
                "",
                "YEAR-BY-YEAR BREAKDOWN",
                "-" * 40,
            ]

            for yr, ys in sorted(yearly_stats.items()):
                strain_delta = ys["vocal_strain_mean"] - baseline_strain
                deviation_label = ""
                if abs(strain_delta) > 0.05:
                    deviation_label = f"  ⚠  DEVIATION from baseline: {strain_delta:+.4f}"

                lines += [
                    f"  [{yr}]  {ys['segment_count']:>4d} segments"
                    f"  |  Pitch={ys['pitch_f0_mean_hz']:.1f} Hz"
                    f"  |  Strain={ys['vocal_strain_mean']:.4f}"
                    f"  |  Rate={ys['speech_rate_mean_wpm']:.1f} WPM"
                    + deviation_label,
                ]

            lines += [
                "",
                "NOTE: Vocal Strain Index measures spectral flux deviation indicating",
                "emotional dysregulation, aggression, or acute stress. Values > 0.30",
                "are considered clinically elevated.",
                "",
                f"=" * 72,
            ]

            txt_path = actor_dir / f"{actor_tag}_longitudinal_summary.txt"
            with open(txt_path, "w", encoding="utf-8") as f:
                f.write("\n".join(lines))
            logger.info(f"[{actor_tag}] Longitudinal report → {txt_path}")

            total_exported += len(flat_rows)

        conn.close()
        logger.info(f"✅ Actor cluster export complete. {total_exported} segments across {len(actors)} actors written to '{out_root}'.")
        return total_exported


# ---------------------------------------------------------------------------
# CLI Entrypoint
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(
        description="AiVoiceTagger — Voice Biometric Speaker Enrollment & Identification Pipeline"
    )
    parser.add_argument(
        "--db-path",
        type=str,
        default="aivoicetagger_state.db",
        help="Path to SQLite state store",
    )
    parser.add_argument(
        "--profiles-dir",
        type=str,
        default="profiles",
        help="Directory containing actor voice profiles (profiles/<Name>/*.wav)",
    )
    parser.add_argument(
        "--threshold",
        type=float,
        default=0.77,
        help="Cosine similarity threshold for positive identification (default: 0.77)",
    )
    parser.add_argument(
        "--ambiguity-margin",
        type=float,
        default=0.09,
        help="Margin delta between top-1 and top-2 candidates to flag ambiguity",
    )
    parser.add_argument(
        "--record-id",
        type=str,
        default=None,
        help="Target a specific record_id",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Limit number of records to process",
    )
    parser.add_argument(
        "--enroll-only",
        action="store_true",
        help="Only build and cache the Voice Vault without tagging speeches",
    )
    parser.add_argument(
        "--export-samples",
        action="store_true",
        help="Auto-extract candidate audio samples into profiles/_candidate_samples/ to help user label speakers",
    )
    parser.add_argument(
        "--export-file",
        type=str,
        default=None,
        help="Target audio file path to slice candidate samples from directly",
    )
    parser.add_argument(
        "--force",
        "-f",
        action="store_true",
        help="Force re-processing of all records even if already tagged",
    )
    parser.add_argument(
        "--quiet",
        "-q",
        action="store_true",
        help="Suppress detailed per-record logs, showing only progress bar",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Compute matches without writing changes to the database",
    )
    parser.add_argument(
        "--self-train",
        action="store_true",
        help="Run semi-supervised profile enrichment using high-confidence database segments",
    )
    parser.add_argument(
        "--self-train-threshold",
        type=float,
        default=0.77,
        help="Minimum similarity to trust a segment for self-training enrichment (default: 0.77)",
    )
    parser.add_argument(
        "--max-pseudo-samples",
        type=int,
        default=50,
        help="Maximum high-confidence segments to query per speaker for self-training (default: 50)",
    )
    parser.add_argument(
        "--self-train-thresholds",
        type=str,
        default=None,
        help="Custom thresholds per actor for self-training (e.g. 'Alois:0.42,Dinda:0.44')",
    )
    parser.add_argument(
        "--reclassify-unmatched",
        action="store_true",
        help="Reclassify previously unmatched/third-party speeches using the enriched centroids",
    )
    parser.add_argument(
        "--export-actor-clusters",
        action="store_true",
        help="Export actor-centric speech clusters (CSV, JSON, longitudinal report) for data science",
    )
    parser.add_argument(
        "--cluster-output-dir",
        type=str,
        default="export/actor_clusters",
        help="Root directory for actor cluster portfolio output (default: export/actor_clusters)",
    )
    parser.add_argument(
        "--min-cluster-confidence",
        type=float,
        default=0.70,
        help="Minimum biometric confidence to include a segment in an actor cluster (default: 0.70)",
    )
    parser.add_argument(
        "--actor-thresholds",
        type=str,
        default=None,
        help="Custom thresholds per actor for classification matching (e.g. 'Alois:0.42,Dinda:0.44')",
    )

    args = parser.parse_args()

    # Parse custom thresholds string to dict
    actor_thresholds = {}
    if args.actor_thresholds:
        for item in args.actor_thresholds.split(","):
            if ":" in item:
                actor, thresh = item.split(":")
                actor_thresholds[actor.strip()] = float(thresh.strip())

    engine = VoiceBiometricEngine(
        profiles_dir=args.profiles_dir,
        db_path=args.db_path,
        match_threshold=args.threshold,
        ambiguity_margin=args.ambiguity_margin,
        verbose=not args.quiet,
        actor_thresholds=actor_thresholds,
    )

    if args.export_actor_clusters:
        engine.export_actor_clusters(
            output_dir=args.cluster_output_dir,
            min_confidence=args.min_cluster_confidence,
        )
    elif args.export_file or args.export_samples:
        engine.export_candidate_samples(max_samples=args.limit or 15, source_file=args.export_file)
    elif args.enroll_only:
        engine.enroll_voice_vault(force_recompute=True)
    elif args.self_train:
        # Parse custom thresholds string to dict
        custom_thresholds = {}
        if args.self_train_thresholds:
            for item in args.self_train_thresholds.split(","):
                if ":" in item:
                    actor, thresh = item.split(":")
                    custom_thresholds[actor.strip()] = float(thresh.strip())

        engine.self_train_enrichment(
            min_confidence=args.self_train_threshold,
            max_pseudo_samples=args.max_pseudo_samples,
            custom_thresholds=custom_thresholds,
        )
        if args.reclassify_unmatched:
            engine.process_all_database_speeches(
                record_id=args.record_id,
                limit=args.limit,
                dry_run=args.dry_run,
                force=args.force,
                reclassify_unmatched=True,
            )
    else:
        engine.process_all_database_speeches(
            record_id=args.record_id,
            limit=args.limit,
            dry_run=args.dry_run,
            force=args.force,
            reclassify_unmatched=args.reclassify_unmatched,
        )


if __name__ == "__main__":
    main()
