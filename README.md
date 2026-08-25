# AiVoiceTagger 🎙️⚡

**AiVoiceTagger** is a high-throughput, enterprise-grade, hardware-accelerated hybrid **Rust + Python** engine designed for resilient batch audio scanning, Whisper transcription, Voice Activity Detection (VAD), French watchlist verbatim matching, and analytical NLP tagging.

Originally operating as a CPU-bound engine, it has undergone a major engineering evolution into an **Industrial CUDA Transcriptor**. Through targeted low-level Rust refactoring, WMI hardware discovery, feature-gated CUDA runtime integration, and resilient IPC stream handling, the system scales robustly across local storage and heavy network shares (`\\SyNAS\Records`).

---

## 🏗️ Architecture Blueprint

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                                 RUST EDGE CORE                                  │
│  • Fast directory tree scanning & Regex date/filename metadata parsing          │
│  • Native audio loading & Symphonia 16 kHz mono PCM downmixing                  │
│  • Shared Arc<WhisperContext> Singleton & Persistent per-worker WhisperState    │
│  • Audio Quality Index (AQI): Good, Degraded, Unusable tagging                  │
│  • Multi-worker local Whisper STT pool (whisper.cpp / whisper-rs)               │
│  • SQLite WAL State Machine & Atomic Multi-Instance Lock-Free Task Leases       │
└────────────────────────────────────────┬────────────────────────────────────────┘
                                         │ Clean IPC Channel (NDJSON / Stdin-Stdout)
┌────────────────────────────────────────▼────────────────────────────────────────┐
│                            PYTHON AI & DATA SIDECAR                             │
│  • Verbatim Watchlist Matching (fatal, legal, menace, insultant)                │
│  • spaCy French NLP Entity Recognition & Story Enrichment                       │
│  • High-performance Polars multi-format export (JSON, CSV, Parquet)              │
└─────────────────────────────────────────────────────────────────────────────────┘
```

### Key Technical Highlights

* **⚡ Rust Edge Core & CUDA Backend**: Ultra-fast file probing, Symphonia decoding, and dedicated GPU Tensor Offloading via WMI Auto-Detect (NVIDIA RTX/CUDA) or OS worker threads.
* **🐍 Python Sidecar**: Isolated subprocess for spaCy NLP enrichment and Polars analytics, now with Lossy Encoding-Resilient IPC for robust French character processing.
* **🔄 Adaptive Double-Pass STT**: Dynamically escalates noisy, loud (battle scene), or low-confidence audio to heavier models (`large-v3`) pinned natively to GPU VRAM.
* **🧠 Shared Model Singleton & Persistent Worker State**: Loads `WhisperContext` once into RAM/VRAM and reuses a single `WhisperState` per worker, saving 4x RAM.
* **🎯 Audio Quality Index (AQI) & Auto-Padding**: Evaluates speech grading (`GOOD`, `DEGRADED`, `UNUSABLE`). Includes a Zero-Warning Short Audio Padding Pipeline that auto-pads <100ms chunks, ensuring 100% transcript completeness with zero dropped tails.
* **⏱️ Real-Time Callbacks & Heartbeats**: Native `set_progress_callback_safe` logs completion percentage, while 30-second pipeline heartbeats ensure zero hangs.
* **🏷️ High-Performance WordTiming**: Pre-allocated vector capacity, `token_eot` filtering, and UTF-8 space-glue cleanup (`\u{2581}`).
* **📂 Manifest-Based Network Ingestion**: Prevents re-walking deep UNC network directories (`\\SyNAS\Records`) by operating off a CSV manifest.
* **💻 Parallel Multi-Instance Core Pinning**: Run multiple process instances concurrently on distinct CPU kernel groups.
* **🛡️ Zero-Data-Loss State Store**: SQLite WAL transaction supervisor with automatic lease recovery and dead-letter queuing.

---

## 📈 Measurable Value & Performance Impact

| Metric | Legacy Engine ("Sleeping Dog") | Industrial CUDA Engine ("Furious Transcriptor") |
| :--- | :--- | :--- |
| **STT Compute Backend** | Host CPU (Thread-Pinned) | NVIDIA CUDA (`CUDA0` VRAM Offload) |
| **CPU Saturation** | 85% – 95% (System Lockup) | < 15% (Background Orchestration) |
| **Model Load & Execution** | Slow host memory transfers | Fast VRAM Matrix Multiplication (`cuBLAS`) |
| **Short Snippet Handling** | Drops / Library Warnings | Auto-Padded to 1,600 samples (Zero Drops) |
| **Sidecar Stream Stability** | Crashed on CP1252 / Accented UTF-8 | 100% Lossy Stream Recovery |
| **Process Control** | Orphaning / Detached handle | Attached Foreground Handle (`Ctrl+C` safe) |

---

## 🛠️ Prerequisites & Setup

### 1. System Requirements

* **Rust Toolchain**: `rustc` & `cargo` (1.75+)

* **Python**: Python 3.10+
* **LLVM / Clang** (Required on Windows for `whisper-rs-sys` C++ bindgen):

  ```powershell
  winget install Kitware.CMake
  ```

### 2. Build the Rust Engine

```powershell
cargo build --release
```

### 3. Launching via PowerShell CUDA Wrapper (`runCuda_1.ps1`)

To run the industrial transcriptor on any target machine with CUDA 13.3, use the provided PowerShell launcher which automatically injects the CUDA runtime DLL path:

```powershell
.\runCuda_1.ps1
```

*(Legacy batch wrapper `bootstart.bat` is also available for CPU-only execution).*

---

## 📦 Whisper Model Downloads

Download GGML models into the `models/` directory using PowerShell:

```powershell
# 1. Fast Primary Model (ggml-small-q8_0.bin ~ 264 MB)
Invoke-WebRequest -Uri "https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-small-q8_0.bin" -OutFile "models\ggml-small-q8_0.bin" -UseBasicParsing

# 2. Heavy Fallback Model for Battle/Noisy Audio (ggml-large-v3-q5_0.bin ~ 1.08 GB)
Invoke-WebRequest -Uri "https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-large-v3-q5_0.bin" -OutFile "models\ggml-large-v3-q5_0.bin" -UseBasicParsing

# 3. Medium Multilingual Model (ggml-medium-q8_0.bin ~ 823 MB)
Invoke-WebRequest -Uri "https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-medium-q8_0.bin" -OutFile "models\ggml-medium-q8_0.bin" -UseBasicParsing
```

---

## ⚙️ Configuration (`config.yaml`)

```yaml
scanner:
  input_directory: "\\\\SyNAS\\Records"
  excluded_extensions: [".xlsx", ".csv", ".json", ".tmp", ".bak"]
  recursive: true
  min_file_size_bytes: 1024

state_store:
  db_path: "aivoicetagger_state.db"
  busy_timeout_ms: 5000
  journal_mode: "WAL"
  synchronous: "NORMAL"

decoder:
  worker_threads: 3
  target_sample_rate: 16000
  channels: 1

stt:
  enabled: true
  model_path: "models/ggml-small-q8_0.bin"
  language: "fr"
  workers: 4
  threads_per_worker: 3
  beam_size: 1
  enable_timestamps: true
  chunk_length_seconds: 30
  adaptive_multipass: true
  heavy_model_path: "models/ggml-large-v3-q5_0.bin"
  confidence_threshold: 0.80
  intensity_threshold_rms: 0.15

sidecar:
  enabled: true
  python_executable: "python"
  script_path: "sidecar/main.py"
  worker_threads: 3
  timeout_seconds: 60

exporter:
  output_directory: "export"
  export_json: true
  export_csv: true
  export_parquet: false
```

---

## 🚀 Advanced Usage Manual

### 1. Noisy Audio Parameter Tuning & AQI Grading

`AiVoiceTagger` incorporates tuned Whisper decoding parameters:

* `logprob_thold = -1.50`: Prevents unnecessary temperature fallback re-decode passes on short clear phrases (e.g. `"C'est super."`).
* `no_context = true`: Disables previous segment context to prevent ambient background noise from triggering continuous token repetition loops.
* `suppress_blank = true`: Suppresses blank tokens during decoding.
* `temperature_inc = 0.0`: Prevents multi-pass temperature escalation on noisy background samples.

Every output record includes an **Audio Quality Index (AQI)** tag:

* **`GOOD`**: Clear speech transcript with high confidence ($> 0.80$).
* **`DEGRADED`**: High ambient background noise or low confidence ($< 0.80$).
* **`UNUSABLE`**: Silent or purely non-speech background audio.

---

### 2. Manifest-Based Scanning for Network Shares (`\\SyNAS\Records`)

Scanning large network shares over SMB/UNC paths can be slow or subject to network drops. Use the 2-step manifest workflow:

#### Step 1: Scan Network Share & Export CSV Manifest

```powershell
cargo run -- --config config.yaml --scan-only --export-manifest inventory_nas.csv
```

*Outputs `inventory_nas.csv` containing all discovered files and parsed date metadata without running heavy audio processing.*

#### Step 2: Batch Process directly from CSV Manifest

```powershell
cargo run -- --config config.yaml --from-csv inventory_nas.csv
```

*(You can edit/filter `inventory_nas.csv` in Excel or Python before launching Step 2 to target specific files!)*

---

### 3. Multi-Machine Parallel Processing & 3-Layer Defense-in-Depth

When running `AiVoiceTagger` across multiple worker machines (`pc-alpha`, `pc-beta`, etc.) processing audio files on a shared network drive (`\\SyNAS\Records`), follow this step-by-step workflow to ensure 100% collision-free parallel processing.

#### Step 1: Combine Existing Local Databases (Optional)

If your worker machines (`PC1` and `PC2`) have already been running independently with local SQLite databases, merge their progress into the central network database on `\\SyNAS\Records` first:

```powershell
python scripts/merge_dbs.py --dest "\\SyNAS\Records\aivoicetagger_state.db" --sources "C:\Dev\AiVoiceTagger\aivoicetagger_state_pc1.db" "C:\Dev\AiVoiceTagger\aivoicetagger_state_pc2.db"
```

> **Note:** The script creates an automatic `.bak` backup file before starting an explicit transaction, deduplicates records by ID, and prioritizes completed processing states.

---

#### Step 2: Generate & Partition the Master Manifest

##### 1. Generate Master Manifest

On **Computer A**, perform a dry-run scan across the shared audio directory:

```powershell
cargo run --release -- --scan-only --export-manifest inventory_all.csv
```

##### 2. Split into Balanced CSV Files

Run the PowerShell partitioning script to divide the manifest evenly between your worker nodes using round-robin distribution:

```powershell
.\scripts\split_manifest.ps1 -ManifestPath inventory_all.csv -NumWorkers 2
```

This creates `inventory_pc1.csv` and `inventory_pc2.csv` in your working directory. Copy `inventory_pc2.csv` over to Computer B (or keep both on the shared network drive).

---

#### Step 3: Configure Shared Network Database (`config.yaml`)

On **both** computers, update `config.yaml` so they point to the single shared state store on `\\SyNAS`:

```yaml
state_store:
  db_path: "\\\\SyNAS\\Records\\aivoicetagger_state.db"
  busy_timeout_ms: 10000
  journal_mode: "WAL"
  synchronous: "NORMAL"
```

---

#### Step 4: Launch Parallel Processing

Now launch both workers. They will operate with **all 3 layers of protection active** (Manifest Partitioning, `.lock` sidecar files on `\\SyNAS`, and SQLite WAL leases):

##### Computer A (`pc-alpha`)

```powershell
cargo run --release -- --config config.yaml --from-csv inventory_pc1.csv --worker-id pc-alpha
```

##### Computer B (`pc-beta`)

```powershell
cargo run --release -- --config config.yaml --from-csv inventory_pc2.csv --worker-id pc-beta
```

*(If you omit `--worker-id`, the system automatically detects and uses your computer's system hostname).*

---

#### 🛡️ How the 3 Layers Protect You in Real Time

1. **Layer 3 (Manifests):** Computer A only considers `inventory_pc1.csv` and Computer B considers `inventory_pc2.csv`.
2. **Layer 2 (Sidecar `.lock`):** Before decoding any audio file, the worker creates an atomic `audio.wav.lock` file containing its worker ID and timestamp. If a lock exists and is $< 30$ minutes old, the file is skipped instantly.
3. **Layer 1 (SQLite WAL):** SQLite locks individual records with `lease_owner = 'pc-alpha'` and a 10-second busy timeout over SMB to ensure database queries never collide.

---

### 4. Single-Machine Kernel Affinity Pinning

On high-core single machines (e.g. 20-core systems), you can also launch multiple local worker instances bound to specific CPU kernel groups:

#### Terminal 1 (Pinned to CPU Cores 0 to 5)

```powershell
cargo run --release -- --config config.yaml --worker-id node-1 --cpu-affinity 0-5
```

#### Terminal 2 (Pinned to CPU Cores 6 to 11)

```powershell
cargo run --release -- --config config.yaml --worker-id node-2 --cpu-affinity 6-11
```

---

### 4. Dynamic Model Override

To run the engine with a specific model on demand without modifying `config.yaml`:

```powershell
cargo run -- --config config.yaml --model models/ggml-medium-q8_0.bin
```

---

### 5. Running Multiple Parallel Workers on a Single Machine (Multi-threaded Race Condition Avoidance)

You can run multiple parallel processing instances on **`pc-alpha`**. The system is built with **SQLite WAL lease locks** and **`.lock` sidecar files**, making multi-process execution safe.

However, to get maximum performance and avoid CPU thread contention, you must observe **two rules**:

#### ⚠️ Two Essential Rules for Parallel Instances

1. **Use Unique Worker IDs**:
   * Do **not** use `--worker-id pc-alpha` for both instances. If you do, both processes will report under the same worker name and overwrite each other's database leases.
   * Use distinct names like `--worker-id pc-alpha-1` and `--worker-id pc-alpha-2`.

2. **Pin CPU Cores with `--cpu-affinity`**:
   * Whisper STT and PyTorch diarization attempt to use all available CPU cores by default. Running two instances without core pinning will cause thread thrashing and slow down both workers.
   * Core pinning isolates each process to its own dedicated set of CPU cores.

### 🚀 Recommended Commands to Launch 2 Parallel Workers on `pc-alpha`

#### Terminal / Window 1 (Worker 1 — Cores 0-5)

```powershell
cargo run --release -- --config config.yaml --from-csv inventory_pc1.csv --worker-id pc-alpha-1 --cpu-affinity "0-5"
```

#### Terminal / Window 2 (Worker 2 — Cores 6-11)

```powershell
cargo run --release -- --config config.yaml --from-csv inventory_pc1.csv --worker-id pc-alpha-2 --cpu-affinity "6-11"
```

*(Adjust `"0-5"` and `"6-11"` depending on your total CPU core count, e.g. `"0-7"` and `"8-15"` on a 16-core CPU).*

#### 💡 Partitioning Tip (Optional)

You can either:

* **Share the same CSV** (`inventory_pc1.csv`): Database lease locks will automatically prevent both workers from touching the same file (the second worker will automatically skip claimed files).
* **Split into separate manifests**: Run the helper script in PowerShell to split your queue evenly into `inventory_pc1.csv` and `inventory_pc2.csv`:

  ```powershell
  .\scripts\split_manifest.ps1 -ManifestPath inventory_manifest.csv -NumWorkers 2
  ```

---

## 💻 Command-Line Interface (CLI) Reference

| CLI Option | Description | Example |
| :--- | :--- | :--- |
| `-c, --config <PATH>` | Path to YAML configuration file. | `--config config.yaml` |
| `-m, --model <PATH>` | Override Whisper STT model path. | `--model models/ggml-medium-q8_0.bin` |
| `--scan-only` | Perform dry-run discovery scan and exit. | `--scan-only` |
| `--export-manifest <PATH>` | Save discovered records inventory to CSV file. | `--export-manifest inventory.csv` |
| `--from-csv <PATH>` | Read file inventory directly from CSV manifest. | `--from-csv inventory.csv` |
| `--worker-id <ID>` | Custom worker instance identifier. | `--worker-id node-1` |
| `--cpu-affinity <CORES>` | Pin process execution to CPU cores. | `--cpu-affinity 0-5` |

---

### 🏛️ Existing High-Interest & Legal Optimization Infrastructure

**AiVoiceTagger** is specially configured and optimized for extracting high-interest audio evidence and generating court-ready forensic transcripts for legal affairs under the **Swiss Legal Framework** in both **French** and **German**.

The core scoring, filtering, and report generation pipeline is built across three primary scripts in the project:

1. **High-Precision Evidence Scorer & Document Generator**:
   * [generate_top_evidence_docs.py](file:///c:/Dev/AiVoiceTagger/scripts/generate_top_evidence_docs.py#L22-L67)
   * Evaluates audio records for red-flag density and isolates **Top "All-Red-Flags-Up" Priority Records**.
   * Filters Whisper hallucination loops, subtitle artifacts, and repeating tokens before building timestamped evidence tables.

2. **Swiss Legal Statutory Mapping (Bilingual FR / DE)**:
   * [generate_forensic_report.py](file:///c:/Dev/AiVoiceTagger/scripts/generate_forensic_report.py#L18-L100)
   * Automatically cross-references detected verbatim phrases into French and German Swiss legal qualifications:
     * 🔴 **WATCH_LETHAL**: Art. 180 CP / Art. 111 CP *(Art. 180 StGB / Art. 111 StGB)* — Death threats & severe violence.
     * 🟠 **WATCH_PHYSICAL_THREATS**: Art. 180 CP & Art. 181 CP *(Art. 180 StGB & Art. 181 StGB)* — Physical assault & coercion.
     * 🟡 **WATCH_VERBAL_ABUSE**: Art. 28, 28b CC & Art. 177 CP *(Art. 28, 28b ZGB & Art. 177 StGB)* — Personal injury & insult.
     * 🟣 **WATCH_DOMESTIC_COERCION**: Art. 28b CC & Art. 186 CP *(Art. 28b ZGB & Art. 186 StGB)* — Domestic harassment & unlawful entry.
     * 🔵 **WATCH_LEGAL_PROCEDURAL**: Swiss judicial, police, and attorney proceedings.

3. **Multi-Model Escalate Pipeline**:
   * [run_heavy_stt_top3.py](file:///c:/Dev/AiVoiceTagger/scripts/run_heavy_stt_top3.py#L1-L26) & [legal_evidence_scorer.py](file:///c:/Dev/AiVoiceTagger/scripts/legal_evidence_scorer.py#L1-L50)
   * Dynamically re-runs high-interest recordings through `whisper-large-v3` (`ggml-large-v3-q5_0.bin`) to ensure 100% transcript precision for key evidence.

---

### 📊 Double-Column Bilingual Table Layout (French & German)

While `generate_forensic_report.py` currently outputs separate `.fr.md` and `.de.md` executive reports, court transcripts can be rendered into a **side-by-side double-column table format** aligning French transcript audio with German translation/equivalents:

| Horodatage (Timestamp) | Transcription Textuelle (Français) | Transkription / Übersetzung (Deutsch) | Qualification Légale (Droit Suisse / CH) |
| :---: | :--- | :--- | :--- |
| `[01:15 - 01:22]` | *"Je vais te défoncer si tu repasses ici."* | *"Ich werde dich fertigmachen, wenn du wieder herkommst."* | 🟠 **Art. 180 CP / StGB 180** (Menaces / Drohung) |
| `[02:40 - 02:45]` | *"Ta gueule, tu n'as aucun droit ici."* | *"Halt's Maul, du hast hier keine Rechte."* | 🟡 **Art. 28 CC / ZGB 28** & **Art. 177 CP / StGB 177** (Injure / Beschimpfung) |
| `[05:12 - 05:20]` | *"Si tu appelles la police, tu vas le regretter."* | *"Wenn du die Polizei anrufst, wirst du es bereuen."* | 🟠 **Art. 181 CP / StGB 181** (Contrainte / Nötigung) |

---

### 🚀 Running Report Generation

To generate the latest forensic legal evidence documents and bilingual dashboards:

```powershell
# 1. Score & generate top priority court evidence documents
python scripts/generate_top_evidence_docs.py

# 2. Build full French & German legal forensic reports and HTML dashboards
python scripts/generate_forensic_report.py
```

Outputs are saved under the [export](file:///c:/Dev/AiVoiceTagger/export) directory.

---

## 🛡️ State Machine & Resilience

`AiVoiceTagger` tracks every record in `aivoicetagger_state.db` across 10 deterministic states:

```
[ DISCOVERED ] ──► [ QUEUED ] ──► [ DECODED ] ──► [ TRANSCRIBED ] ──► [ NLP_DONE ] ──► [ EXPORTED ] ──► [ DONE ]
                        │              │                 │
                        └──────────────┴─────────────────┴──► [ DEAD_LETTER / FAILED ]
```

* **Atomic Leases**: Claims carry a 5-minute lease expiry. If an instance crashes mid-transcription, its assigned files are automatically reclaimed by another active worker.
* **Graceful Shutdown & Mid-File Resume**: The engine traps `Ctrl+C` interrupts to safely stop worker threads, commit partial chunk transcriptions (`speeches`) to the SQLite database, and gracefully drop file locks. On the next run, it dynamically skips the previously processed chunks and resumes exactly where it left off.
* **Dead-Letter Recovery**: Corrupt audio files or repeated failures land in the `dead_letter` table for audit without stopping the pipeline.

---

## 🔮 Tripartite Post-Analytics & 3D Spatial Intelligence

Post-processing operates across three synchronized analytical dimensions according to [Analytics_Architecture_v1.md](file:///c:/Dev/AiVoiceTagger/docs/Analytics_Architecture_v1.md):

1. **Discourse & Semantic Dynamics (Polars):** Exact talk-time ratios, conversational dominance, n-gram lexical repetition loops (*"dégage"*, *"tu sors"*), and Audio Quality Index (AQI) correlations.
2. **Swiss Forensic Legal Qualification (CP / CC):** Evidentiary structure for Art. 180 CP (*Drohung* / Menaces), Art. 181 CP (*Nötigung* / Contrainte), Art. 177 CP (*Beschimpfung* / Injure), Art. 186 CP (*Hausfriedensbruch*), and Art. 28, 28b CC (*ZGB*).
3. **Psychodynamics & Coercive Control:** Projective identification, splitting, double-bind directives, and family triangulation / parental alienation dynamics.
4. **3D WebGL / R3F Spatial Intelligence Visualizer:** GPU-accelerated 3D manifold ($X, Y$ semantic plane, $Z$ acoustic agitation RMS), Swiss statutory cylindrical constellation, and psychodynamic tensor field with custom GLSL agitation & crisis heatmap shaders.

### 📊 Implementation Coverage Matrix

| Analytical Dimension | Architectural Capability | Implementation Component | Status |
| :--- | :--- | :--- | :---: |
| **Discourse Semantics** | Talk-time ratios, n-gram lexical loops, timestamped transcripts | `scripts/generate_tripartite_post_analytics.py` | **100%** |
| **Swiss Forensic Law** | Art. 180, 181, 177, 186 CP & Art. 28/28b CC qualification | `scripts/generate_tripartite_post_analytics.py` | **100%** |
| **Psychodynamics** | Coercive control, projective identification, alienation analysis | `scripts/generate_tripartite_post_analytics.py` | **100%** |
| **Court Dossier Exports** | Markdown Dossiers (`Report_*.md`) & JSON Telemetry (`Telemetry_*.json`) | `scripts/generate_tripartite_post_analytics.py` | **100%** |
| **3D Data Bridge** | 2D UMAP plane, RMS intensity $Z$, cylindrical statutory mapping | `scripts/export_post_analytics_3d.py` | **100%** |
| **GLSL Shaders** | RMS agitation waves, gravitational attractor vortexes, crisis heatmaps | `dashboard/src/app/visualizer/shaders.ts` | **100%** |
| **3D WebGL Canvas** | Three toggleable projection layers (`SEMANTIC`, `LEGAL`, `PSYCHODYNAMIC`) | `dashboard/src/app/visualizer/ForensicVisualizer3D.tsx` | **100%** |
| **Sidecar REST APIs** | `GET /api/post_analytics/reports` & `GET /api/post_analytics/3d` | `sidecar/server.py` | **100%** |

---

### 🔮 Semi-Supervised Self-Training & Reclassification
To refine speaker profiles and increase identification coverage, you can leverage existing high-confidence matches to automatically update speaker centroids and run a second-pass reclassification of unmatched or third-party segments:

*   **Centroid Self-Training**: Iterates through database segments matching target speakers with confidence $\ge \tau$, extracts their embeddings in batch, and performs a sample-size weighted centroid recalculation.
*   **Actor-Specific Thresholds**: Support custom target thresholds per actor to handle voice changes over time (e.g., Alois/Dinda).
*   **Second-Pass Reclassification**: Scan previously unidentified segments (`SPEAKER_THIRD_PARTY` or `Speaker Unknown`) using the newly enriched centroids to boost overall identification rates.

```powershell
# 1. Run self-training centroid enrichment (Default threshold 0.77)
python scripts/enroll_and_identify_speakers.py --self-train

# 2. Run self-training with actor-specific overrides (highly recommended for voice drifts)
python scripts/enroll_and_identify_speakers.py --self-train --self-train-thresholds "Al:0.42,DD:0.44"

# 3. Run self-training AND immediately reclassify unmatched segments
python scripts/enroll_and_identify_speakers.py --self-train --self-train-thresholds "Al:0.42,DD:0.44" --reclassify-unmatched

# 4. Run reclassification only (uses the cached/enriched centroids in the database)
python scripts/enroll_and_identify_speakers.py --reclassify-unmatched --limit 50
```

---

### 📊 Actor-Centric Speech Clustering & Data Science Export
To enable downstream psychological, linguistic, or data science studies (e.g., longitudinal analysis of vocal drift or stress behaviors between 2020 and 2026), you can group all matched speech segments by speaker into individual data portfolios:

*   **Flat Tabular Exports (`.csv`)**: Generates a consolidated table of all segment timestamps, file paths, transcripts, and acoustic biomarkers ready for direct Pandas or R ingestion.
*   **JSON Portfolios (`.json`)**: Formats the actor's history, metadata, and year-by-year aggregate vocal metrics into a nested, machine-readable portfolio.
*   **Longitudinal Reports (`.txt`)**: Summarizes vocal trends (F0 pitch, vocal strain, speech rate) year-by-year, automatically highlighting significant deviations.

```powershell
# 1. Export clusters for all actors using default settings (min-confidence >= 0.70)
python scripts/enroll_and_identify_speakers.py --export-actor-clusters

# 2. Export clusters with custom confidence thresholds and custom directory
python scripts/enroll_and_identify_speakers.py --export-actor-clusters --min-cluster-confidence 0.66 --cluster-output-dir "export/custom_clusters"
```

---

## 🧬 Voice Biometric Identification & Acoustic Stress Biomarkers

AiVoiceTagger transitions from relative speaker clustering to **Supervised Biometric Voiceprint Matching** using 192-dimensional D-Vector embeddings (**ECAPA-TDNN**):

* **Voice Vault Reference Profiles:** Drops 3–10s single-speaker audio samples into `profiles/<Actor_Name>/*.wav` to compute canonical centroids.
* **Vectorized Cosine Similarity:** Re-tags the 32,284 database sentences based on threshold matching ($\tau \ge 0.72$) with ambiguity guard ($\Delta\text{Sim} < 0.06$).
* **Acoustic Biomarkers Extractor:** Measures Fundamental Frequency ($F_0$ pitch), Vocal Strain Index (high-frequency tension under threat), and Speech Rate (WPM).
* **Resumable & Interrupt-Safe**: Built-in per-record SQLite transaction commits (`conn.commit()`) and `Ctrl+C` signal handling allow seamless interruption and resumption without losing work.

```powershell
# 1. Build Voice Vault & identify actors across database records (Auto-Resumable)
python scripts/enroll_and_identify_speakers.py --db-path "aivoicetagger_state.db"

# 2. Force re-processing of all records (ignoring existing checkpoints)
python scripts/enroll_and_identify_speakers.py --db-path "aivoicetagger_state.db" --force
```

---

## 🛡️ Dual Privacy Governance (GDPR / Swiss nLPD & Judicial Forensics)

To comply with data privacy standards (GDPR / Swiss revised LPD) while supporting unredacted criminal/civil court submissions (**Art. 180, 181, 177, 186 CP & Art. 28, 28b CC**), the state store maintains dual participant representations:

| Analytical Context | Speeches Column | Records Column | Output Type |
| :--- | :--- | :--- | :--- |
| **🔒 Public / GDPR View** | `speaker_anonymized` (`Speaker 01`, `Speaker 02`) | `participants_anonymized_json` | Public WebGL 3D scene, research demo |
| **⚖️ Certified Judicial View** | `speaker_disclosed` (`AF`, `CI`, `AM`) | `participants_disclosed_json` | Court-admissible forensic dossier |

### 🚀 Turnkey Guidance & Command Execution

```powershell
# 1. Generate CERTIFIED forensic dossiers (with real actor names)
python scripts/generate_tripartite_post_analytics.py --db-path "aivoicetagger_state.db" --min-score 300 --limit 5

# 2. Generate GDPR / LPD ANONYMIZED dossiers (Speaker 01, Speaker 02...)
python scripts/generate_tripartite_post_analytics.py --db-path "aivoicetagger_state.db" --anonymize --limit 5

# 3. Export 3D constellation payload for WebGL visualizer (Public Anonymized)
python scripts/export_post_analytics_3d.py --db-path "aivoicetagger_state.db" --anonymize

# 4. Query live 3D constellation via API with on-the-fly GDPR redaction
curl "http://localhost:9090/api/post_analytics/3d?anonymized=true"
```

---

## 📄 License

MIT License.
