#!/usr/bin/env python3
"""
AiVoiceTagger — Tripartite Post-Analytics Pipeline
===================================================
Automated Semantic, Swiss Forensic Legal, and Psychodynamic dialogue analysis
powered by Polars, SQLite WAL State Store, and LiteLLM.

Author: Antoine Guillaume Falempin, M.Sc.
Version: 2.1
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sqlite3
import sys
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import polars as pl
try:
    from litellm import completion  # type: ignore
    HAS_LITELLM = True
except ImportError:
    HAS_LITELLM = False

# ---------------------------------------------------------------------------
# Logging Configuration
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("PostAnalytics")

# ---------------------------------------------------------------------------
# System Prompt Definitions
# ---------------------------------------------------------------------------
SYSTEM_PROMPT = """# SYSTEM PROMPT: Forensic Speech & Behavioral Post-Analytics Engine

## OBJECTIVE
You are a Senior Forensic Computational Linguist, Swiss Legal Expert (Swiss Criminal Code CP RS 311.0 & Civil Code CC RS 210), and Clinical Psychodynamic Interaction Analyst.
Your task is to analyze the provided timestamped dialogue transcription and discourse telemetry to produce an exhaustive, court-admissible, tripartite forensic report.

## JURISDICTION & STATUTORY FRAMEWORK (SWITZERLAND)
- **Art. 180 CP (Drohung / Menaces):** Putting an individual in serious fear or alarm through threats of bodily harm, death, or severe prejudice.
- **Art. 181 CP (Nötigung / Contrainte):** Coercive restriction of behavioral autonomy by violence, threat of serious detriment, or other hindrance.
- **Art. 177 CP (Beschimpfung / Injure):** Direct attack upon a person's moral honor by formal words, images, or gestures.
- **Art. 186 CP (Hausfriedensbruch / Violation de domicile):** Intrusion into a domicile or unlawful refusal to leave upon request.
- **Art. 28 & 28b CC (Persönlichkeitsverletzung & Gewaltschutz / Protection de la personnalité & Harcèlement):** Systemic emotional violence, surveillance, domestic harassment, psychological intimidation, and residential exclusion.

---

## REQUIRED STRUCTURE OF OUTPUT REPORT (MARKDOWN)

### 1. RECORD METADATA & FORENSIC EXECUTIVE SUMMARY
- Transcript File, Recording Period & Environmental Setting
- Conversational Balance & Speaker Distribution Metrics
- Core Relational Conflict Vector & Severity Rating (Scale 1–10)
- Executive Forensic Thesis (1 paragraph)

### 2. DISCOURSE, LINGUISTIC & SEMANTIC ANALYSIS
- **Verbatim Cycles & Repetitive Fixations:** Identify persistent commands (e.g., expulsion loops: "dégage", "casse-toi", "sors"), semantic anchors, and obsessive themes.
- **Conversational Asymmetry & Dominance Dynamics:** Turn-taking latency, interruptions, weaponized monologues, and acoustic escalation indicators.
- **Cognitive & Narrative Distortion:** Gaslighting patterns, denial of objective realities, projective blame, and topic derailment techniques.

### 3. SWISS FORENSIC LEGAL EVALUATION
Provide a structured evidence table in the following exact layout:
| Horodatage (Timestamp) | Locuteur (Speaker) | Verbatim Transcription (FR) | Translation / Meaning (DE/EN) | Qualification Légale (Droit Suisse) | Gravité (Severity) |
| :---: | :---: | :--- | :--- | :--- | :---: |

- **Statutory Cross-Examination:** Detailed justification for qualifications under Art. 180 CP, 181 CP, 177 CP, 186 CP, and 28b CC.
- **Mens Rea & Intentionality:** Evidence of premeditation, intimidation strategies, and awareness of illegality.
- **Child Protection Implications (if applicable):** Document exposure of minors to verbal/physical domestic strife.

### 4. PSYCHODYNAMIC & BEHAVIORAL DYNAMICS
- **Relational Mechanics:** Identification of defense mechanisms (projective identification, splitting, inversion of victim/aggressor roles).
- **Coercive Control Architecture:** Modalities of spatial deprivation, financial leverage, threat of institutional weaponization (police/courts), or social isolation.
- **Double-Bind Directives:** Document contradictory instructions where compliance is rendered impossible.

### 5. SYNTHESIS & FORENSIC PROBATORY RECOMMENDATIONS
- Probative synthesis of the record's evidence value.
- Cross-referencing recommendations for judicial submission before Swiss civil/criminal courts.

---

## OUTPUT GUIDELINES
- Strict objectivity: Rely exclusively on verifiable verbatim quotes and provided timestamps.
- Maintain high formal forensic and scholarly standards.
- Language: French (with bilingual FR/DE statutory citations).
"""


@dataclass
class RecordTelemetry:
    record_id: str
    file_name: str
    file_path: str
    duration_seconds: float
    aqi_grade: str
    total_segments: int
    speakers_detected: List[str]
    speaker_durations: Dict[str, float]
    speaker_word_counts: Dict[str, int]
    top_repeated_phrases: List[Tuple[str, int]]
    transcript_text: str


class PostAnalyticsEngine:
    def __init__(
        self,
        db_path: str,
        output_dir: str = "export/post_analytics",
        model_name: str = "gpt-4o",
        temperature: float = 0.1,
        max_tokens: int = 4096,
        anonymize: bool = False,
    ):
        self.db_path = Path(db_path)
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.model_name = model_name
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.anonymize = anonymize

        if not self.db_path.exists():
            raise FileNotFoundError(f"SQLite State Store not found at {self.db_path}")

    def _get_connection(self) -> sqlite3.Connection:
        """Establish a safe SQLite WAL connection with timeout."""
        conn = sqlite3.connect(str(self.db_path), timeout=10.0)
        conn.execute("PRAGMA journal_mode = WAL;")
        conn.execute("PRAGMA busy_timeout = 10000;")
        return conn

    def fetch_records_to_analyze(
        self,
        record_id: Optional[str] = None,
        min_score: int = 0,
        limit: Optional[int] = None,
    ) -> pl.DataFrame:
        """Fetch records and speech transcripts into a unified Polars DataFrame."""
        conn = self._get_connection()

        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info(records);")
        columns = [row[1] for row in cursor.fetchall()]

        id_col = "record_id" if "record_id" in columns else "id"
        name_col = "name" if "name" in columns else ("file_name" if "file_name" in columns else f"'{id_col}' AS file_name")
        dir_col = "directory" if "directory" in columns else ("file_path" if "file_path" in columns else "'' AS file_path")
        aqi_col = "aqi_grade" if "aqi_grade" in columns else "'' AS aqi_grade"
        select_score = "triage_score" if "triage_score" in columns else "0 AS triage_score"

        query_records = f"""
            SELECT 
                {id_col} AS record_id,
                {name_col} AS file_name,
                {dir_col} AS file_path,
                duration_seconds,
                {aqi_col},
                state,
                {select_score}
            FROM records
            WHERE state IN ('Done', 'TriagedHighInterest', 'NLP_DONE', 'Transcribed')
        """
        if record_id:
            query_records += f" AND {id_col} = '{record_id}'"
        elif min_score > 0 and "triage_score" in columns:
            query_records += f" AND triage_score >= {min_score}"

        if "triage_score" in columns:
            query_records += " ORDER BY triage_score DESC, duration_seconds DESC"
        else:
            query_records += " ORDER BY duration_seconds DESC"

        if limit:
            query_records += f" LIMIT {limit}"

        df_records = pl.read_database(query_records, conn)
        conn.close()

        logger.info(f"Loaded {len(df_records)} target records for post-analytics.")
        return df_records

    def fetch_speeches_for_record(self, record_id: str) -> pl.DataFrame:
        """Fetch chronological speech segments with timestamps and speaker tags."""
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info(speeches);")
        speech_cols = [row[1] for row in cursor.fetchall()]

        text_col = "script" if "script" in speech_cols else ("text" if "text" in speech_cols else "'' AS text")
        valid_spk_cols = [c for c in ["speaker_disclosed", "speaker_tag", "speaker_anonymized"] if c in speech_cols]
        if self.anonymize:
            if "speaker_anonymized" in speech_cols:
                speaker_col = "speaker_anonymized"
            else:
                speaker_col = f"COALESCE({', '.join(valid_spk_cols)}, 'Speaker 01')" if valid_spk_cols else "'Speaker 01'"
        else:
            if valid_spk_cols:
                speaker_col = f"COALESCE({', '.join(valid_spk_cols)}, 'Speaker 01')"
            else:
                speaker_col = "'Speaker 01'"
        
        if "offset_ms" in speech_cols and "duration_ms" in speech_cols:
            time_select = "(offset_ms / 1000.0) AS start_time, ((offset_ms + duration_ms) / 1000.0) AS end_time"
            order_by = "offset_ms ASC"
        else:
            time_select = "start_time, end_time"
            order_by = "start_time ASC"

        query_speeches = f"""
            SELECT 
                record_id,
                {time_select},
                {speaker_col} AS speaker,
                {text_col} AS text,
                confidence
            FROM speeches
            WHERE record_id = '{record_id}'
            ORDER BY {order_by}
        """
        df_speeches = pl.read_database(query_speeches, conn)
        conn.close()
        return df_speeches

    def compute_discourse_telemetry(
        self, record_meta: Dict[str, Any], df_speeches: pl.DataFrame
    ) -> RecordTelemetry:
        """Calculate statistical discourse metrics using Polars."""
        if df_speeches.is_empty():
            return RecordTelemetry(
                record_id=record_meta["record_id"],
                file_name=record_meta["file_name"],
                file_path=record_meta["file_path"],
                duration_seconds=record_meta["duration_seconds"] or 0.0,
                aqi_grade=record_meta["aqi_grade"] or "UNKNOWN",
                total_segments=0,
                speakers_detected=[],
                speaker_durations={},
                speaker_word_counts={},
                top_repeated_phrases=[],
                transcript_text="[NO_SPEECH_DATA]",
            )

        # 1. Speaker distribution
        df_speeches = df_speeches.with_columns(
            (pl.col("end_time") - pl.col("start_time")).alias("segment_duration"),
            pl.col("text").fill_null("").str.split(" ").list.len().alias("word_count"),
        )

        speaker_summary = (
            df_speeches.group_by("speaker")
            .agg(
                pl.col("segment_duration").sum().alias("total_duration"),
                pl.col("word_count").sum().alias("total_words"),
            )
            .to_dicts()
        )

        speaker_durations = {
            (row["speaker"] or "SPEAKER_UNKNOWN"): round(row["total_duration"] or 0.0, 2)
            for row in speaker_summary
        }
        speaker_word_counts = {
            (row["speaker"] or "SPEAKER_UNKNOWN"): (row["total_words"] or 0)
            for row in speaker_summary
        }
        speakers_detected = list(speaker_durations.keys())

        # 2. Extract Lexical Repetitions (2-word n-grams)
        all_text = " ".join(df_speeches["text"].drop_nulls().to_list()).lower()
        words = re.findall(r"\b[a-zA-Zàâäéèêëîïôöùûüç'-]{3,}\b", all_text)
        
        phrase_counts: Dict[str, int] = {}
        if len(words) > 1:
            n_grams = [f"{words[i]} {words[i+1]}" for i in range(len(words) - 1)]
            for phrase in n_grams:
                phrase_counts[phrase] = phrase_counts.get(phrase, 0) + 1

        top_repeated = sorted(
            [(k, v) for k, v in phrase_counts.items() if v > 2],
            key=lambda x: x[1],
            reverse=True,
        )[:8]

        # 3. Build formatted chronological transcript with millisecond timestamps
        formatted_segments = []
        for row in df_speeches.iter_rows(named=True):
            start_fmt = self._format_timestamp(row["start_time"])
            end_fmt = self._format_timestamp(row["end_time"])
            spk = row["speaker"] if row["speaker"] else "SPEAKER_UNKNOWN"
            txt = row["text"].strip() if row["text"] else ""
            formatted_segments.append(f"[{start_fmt} --> {end_fmt}] [{spk}] {txt}")

        transcript_text = "\n".join(formatted_segments)

        return RecordTelemetry(
            record_id=record_meta["record_id"],
            file_name=record_meta["file_name"],
            file_path=record_meta["file_path"],
            duration_seconds=round(record_meta["duration_seconds"] or 0.0, 2),
            aqi_grade=record_meta["aqi_grade"] or "UNKNOWN",
            total_segments=len(df_speeches),
            speakers_detected=speakers_detected,
            speaker_durations=speaker_durations,
            speaker_word_counts=speaker_word_counts,
            top_repeated_phrases=top_repeated,
            transcript_text=transcript_text,
        )

    @staticmethod
    def _format_timestamp(seconds: Optional[float]) -> str:
        """Convert float seconds to HH:MM:SS.mmm format."""
        if seconds is None:
            return "00:00:00.000"
        m, s = divmod(seconds, 60)
        h, m = divmod(m, 60)
        millis = int((s - int(s)) * 1000)
        return f"{int(h):02d}:{int(m):02d}:{int(s):02d}.{millis:03d}"

    def build_user_payload(self, telem: RecordTelemetry) -> str:
        """Compile statistical discourse telemetry and raw transcript for LLM analysis."""
        speaker_stats_lines = []
        total_time = telem.duration_seconds if telem.duration_seconds > 0 else 1.0
        for spk in telem.speakers_detected:
            dur = telem.speaker_durations.get(spk, 0.0)
            words = telem.speaker_word_counts.get(spk, 0)
            pct = (dur / total_time) * 100
            speaker_stats_lines.append(f"- **{spk}**: {dur}s ({pct:.1f}% talk time), {words} words")

        reps_lines = [f"- \"{p}\": {c} occurrences" for p, c in telem.top_repeated_phrases]
        reps_str = "\n".join(reps_lines) if reps_lines else "None detected above threshold."

        payload = f"""### INPUT RECORD TELEMETRY
- **File Name**: `{telem.file_name}`
- **Record Identifier**: `{telem.record_id}`
- **Storage Path**: `{telem.file_path}`
- **Total Duration**: `{telem.duration_seconds} seconds`
- **Audio Quality Index (AQI)**: `{telem.aqi_grade}`
- **Total Speech Segments**: `{telem.total_segments}`

### DISCOURSE & STATISTICAL METRICS
#### Speaker Talk-Time Distribution:
{chr(10).join(speaker_stats_lines)}

#### Dominant Lexical N-Gram Repetitions:
{reps_str}

---

### TIMESTAMPED DIARIZED TRANSCRIPTION (CHRONOLOGICAL):
{telem.transcript_text}
"""
        return payload

    def execute_analytics_llm(self, user_payload: str) -> str:
        """Call LLM via LiteLLM with structured system/user messages or fallback to deterministic report."""
        if not HAS_LITELLM:
            return (
                "## Rapport Automatisé (Mode Télémétrie Hors-Ligne)\n\n"
                "*Note: `litellm` n'est pas installé dans cet environnement. "
                "Le résumé statistique a été calculé et sauvegardé avec succès dans le fichier télémétrique .json adjacent.*\n\n"
                + user_payload
            )

        try:
            response = completion(
                model=self.model_name,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_payload},
                ],
                temperature=self.temperature,
                max_tokens=self.max_tokens,
            )
            return response.choices[0].message.content
        except Exception as e:
            logger.warning(f"LLM completion error ({e}), generating deterministic telemetry report.")
            return (
                f"## Rapport Automatisé de Télémétrie (Fallback)\n\n"
                f"*Erreur lors de l'appel LLM ({self.model_name}): {e}*\n\n"
                + user_payload
            )

    def process_record(self, record_meta: Dict[str, Any]) -> Path:
        """End-to-end processing pipeline for a single audio record."""
        rec_id = record_meta["record_id"]
        file_name = record_meta["file_name"]
        logger.info(f"Processing Record [{rec_id}] — {file_name}")

        df_speeches = self.fetch_speeches_for_record(rec_id)
        telem = self.compute_discourse_telemetry(record_meta, df_speeches)

        if telem.total_segments == 0:
            logger.warning(f"Skipping Record [{rec_id}] — No speech segments found.")
            return Path()

        user_payload = self.build_user_payload(telem)
        report_markdown = self.execute_analytics_llm(user_payload)

        # Output Markdown file
        clean_base = re.sub(r"[^\w\-.]", "_", Path(file_name).stem)
        report_path = self.output_dir / f"Report_{clean_base}_{rec_id[:8]}.md"
        
        confidentiality_mode = (
            "🔒 **Mode:** `RGPD / LPD Anonymisé (Identités Protégées — Speaker 01, 02...)`"
            if self.anonymize
            else "⚖️ **Mode:** `Expertise Forensique — Identification Nominative Certifiée`"
        )

        with open(report_path, "w", encoding="utf-8") as f:
            f.write(f"# 🛡️ AiVoiceTagger — Rapport Tripartite Forensique & Sémantique\n\n")
            f.write(f"**Généré le:** `{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}`  \n")
            f.write(f"**Modèle d'Inférence:** `{self.model_name}`  \n")
            f.write(f"**Identifiant Dossier:** `{rec_id}`  \n")
            f.write(f"{confidentiality_mode}  \n\n---\n\n")
            f.write(report_markdown)

        # Output Structured JSON Sidecar
        json_path = self.output_dir / f"Telemetry_{clean_base}_{rec_id[:8]}.json"
        with open(json_path, "w", encoding="utf-8") as jf:
            json.dump(asdict(telem), jf, indent=2, ensure_ascii=False)

        logger.info(f"✅ Generated Forensic Report: {report_path.name}")
        return report_path

    def run_batch(
        self,
        record_id: Optional[str] = None,
        min_score: int = 0,
        limit: Optional[int] = None,
        max_workers: int = 2,
    ) -> List[Path]:
        """Execute parallel batch processing across selected records."""
        df_targets = self.fetch_records_to_analyze(
            record_id=record_id, min_score=min_score, limit=limit
        )

        records_list = df_targets.to_dicts()
        if not records_list:
            logger.warning("No records matched the specified query filters.")
            return []

        generated_reports: List[Path] = []
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_rec = {
                executor.submit(self.process_record, rec): rec for rec in records_list
            }
            for future in as_completed(future_to_rec):
                rec = future_to_rec[future]
                try:
                    res_path = future.result()
                    if res_path and res_path.exists():
                        generated_reports.append(res_path)
                except Exception as exc:
                    logger.error(f"Failed processing record {rec['file_name']}: {exc}", exc_info=True)

        logger.info(f"🎉 Batch analytics completed! Total Reports Created: {len(generated_reports)}")
        return generated_reports


# ---------------------------------------------------------------------------
# CLI Entry Point
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(
        description="AiVoiceTagger Tripartite Semantic, Legal & Psychodynamic Post-Analytics Engine"
    )
    parser.add_argument(
        "--db-path",
        type=str,
        default="aivoicetagger_state.db",
        help="Path to central SQLite state database (e.g., \\\\SyNAS\\Records\\aivoicetagger_state.db)",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default="export/post_analytics",
        help="Target folder for markdown reports and JSON telemetry",
    )
    parser.add_argument(
        "--model",
        type=str,
        default=os.getenv("POST_ANALYTICS_MODEL", "gpt-4o"),
        help="LiteLLM model descriptor (e.g. gpt-4o, claude-3-7-sonnet, ollama/qwen2.5:32b)",
    )
    parser.add_argument(
        "--record-id",
        type=str,
        default=None,
        help="Target a single specific record_id for deep analysis",
    )
    parser.add_argument(
        "--min-score",
        type=int,
        default=300,
        help="Minimum triage score filter (default: 300 for high red-flag files)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=10,
        help="Maximum number of dossiers to analyze in batch",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=2,
        help="Concurrent LLM analysis threads",
    )
    parser.add_argument(
        "--anonymize",
        action="store_true",
        help="Enforce GDPR / LPD anonymization (use Speaker 01, Speaker 02... instead of real names)",
    )

    args = parser.parse_args()

    engine = PostAnalyticsEngine(
        db_path=args.db_path,
        output_dir=args.output_dir,
        model_name=args.model,
        anonymize=args.anonymize,
    )

    engine.run_batch(
        record_id=args.record_id,
        min_score=args.min_score,
        limit=args.limit,
        max_workers=args.workers,
    )


if __name__ == "__main__":
    main()
