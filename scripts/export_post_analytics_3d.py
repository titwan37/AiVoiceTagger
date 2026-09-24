#!/usr/bin/env python3
"""
AiVoiceTagger — 3D Forensic Semantic Constellation Exporter
============================================================
Generates 3D spatial coordinate payloads for WebGL / React Three Fiber
visualization (Semantic Manifold, Swiss Legal Constellation, Psychodynamic Tensors).

Author: Antoine Guillaume Falempin, M.Sc.
Version: 1.0
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import math
import sqlite3
import sys
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("Export3D")


def hash_to_unit_coords(text: str) -> tuple[float, float]:
    """Deterministic 2D projection from text hash for reproducible spatial clustering."""
    h = hashlib.sha256(text.encode("utf-8")).hexdigest()
    val_x = int(h[:8], 16) / 0xFFFFFFFF
    val_y = int(h[8:16], 16) / 0xFFFFFFFF
    return (val_x * 2.0 - 1.0, val_y * 2.0 - 1.0)


def extract_statute_category(text: str) -> Optional[str]:
    """Rule-based mapping from speech text to Swiss legal categories."""
    txt = text.lower()
    if any(k in txt for k in ["tuer", "mort", "defoncer", "défoncer", "crever", "buter"]):
        return "ART_180"  # Menaces de mort / atteinte corporelle grave
    if any(k in txt for k in ["oblige", "force", "dehors", "sommation", "interdit", "dégage"]):
        return "ART_181"  # Contrainte / Nötigung
    if any(k in txt for k in ["connard", "salaud", "salope", "merde", "ordure", "porc", "pute", "ferme"]):
        return "ART_177"  # Injure / Beschimpfung
    if any(k in txt for k in ["domicile", "chez moi", "serrure", "porte", "entrer", "intrusion"]):
        return "ART_186"  # Violation de domicile
    if any(k in txt for k in ["harcèle", "suis", "filme", "menace", "plainte", "justice", "avocat"]):
        return "ART_28B"  # Protection de la personnalité / Harcèlement
    return None


def calculate_severity(text: str, confidence: float) -> float:
    """Calculate severity index (0.0 to 1.0) based on statutory terms and confidence."""
    txt = text.lower()
    score = 0.3
    if any(k in txt for k in ["tuer", "mort", "défoncer", "crever", "buter"]):
        score += 0.5
    elif any(k in txt for k in ["dégage", "dégager", "sortir", "fous le camp", "police"]):
        score += 0.35
    elif any(k in txt for k in ["connard", "merde", "ordure", "pute", "porc"]):
        score += 0.25

    return min(1.0, max(0.1, score * (0.8 + 0.2 * confidence)))


def parse_year_offset(filename: str) -> float:
    """Extract approximate recording year (2015 - 2026) normalized to [0.0, 1.0]."""
    # Look for 4-digit year e.g. 2021, 2022, 2025
    import re
    match = re.search(r"\b(201[5-9]|202[0-6])\b", filename)
    if match:
        year = int(match.group(1))
        return (year - 2015) / (2026 - 2015)
    return 0.5  # Default middle


def generate_3d_constellation(
    db_path: str,
    output_path: str = "export/post_analytics/3d_constellation.json",
    limit_records: int = 50,
    anonymize: bool = False,
) -> Dict[str, Any]:
    db_file = Path(db_path)
    if not db_file.exists():
        raise FileNotFoundError(f"Database not found at {db_file}")

    conn = sqlite3.connect(str(db_file))
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute("PRAGMA table_info(records);")
    rec_cols = [row["name"] for row in cursor.fetchall()]
    id_col = "record_id" if "record_id" in rec_cols else "id"
    name_col = "name" if "name" in rec_cols else ("file_name" if "file_name" in rec_cols else f"'{id_col}'")
    dir_col = "directory" if "directory" in rec_cols else ("file_path" if "file_path" in rec_cols else "''")
    aqi_col = "aqi_grade" if "aqi_grade" in rec_cols else "''"

    cursor.execute("PRAGMA table_info(speeches);")
    speech_cols = [row["name"] for row in cursor.fetchall()]
    text_col = "script" if "script" in speech_cols else ("text" if "text" in speech_cols else "''")
    
    fallback_spk = ", speaker" if "speaker" in speech_cols else ""
    if anonymize:
        if "speaker_anonymized" in speech_cols:
            speaker_col = f"COALESCE(speaker_anonymized{fallback_spk}, 'Speaker 01')"
        else:
            speaker_col = "speaker" if "speaker" in speech_cols else "'Speaker 01'"
    else:
        if "speaker_disclosed" in speech_cols:
            speaker_col = f"COALESCE(speaker_disclosed, speaker_tag, speaker_anonymized{fallback_spk}, 'Speaker 01')"
        elif "speaker_tag" in speech_cols:
            speaker_col = f"COALESCE(speaker_tag{fallback_spk}, 'Speaker 01')"
        else:
            speaker_col = "speaker" if "speaker" in speech_cols else "'Speaker 01'"

    # Query top priority processed records
    cursor.execute(
        f"""
        SELECT {id_col} AS id, {name_col} AS file_name, {dir_col} AS file_path, duration_seconds, {aqi_col} AS aqi_grade
        FROM records
        WHERE state IN ('Done', 'TriagedHighInterest', 'NLP_DONE', 'Transcribed')
        ORDER BY duration_seconds DESC
        LIMIT ?
        """,
        (limit_records,),
    )
    records = cursor.fetchall()

    nodes: List[Dict[str, Any]] = []
    node_id_counter = 1

    for rec in records:
        rec_id = rec["id"]
        file_name = rec["file_name"] or "audio.wav"
        year_offset = parse_year_offset(file_name)

        if "offset_ms" in speech_cols and "duration_ms" in speech_cols:
            time_select = "(offset_ms / 1000.0) AS start_time, ((offset_ms + duration_ms) / 1000.0) AS end_time"
            order_by = "offset_ms ASC"
        else:
            time_select = "start_time, end_time"
            order_by = "start_time ASC"

        cursor.execute(
            f"""
            SELECT {time_select}, {speaker_col} AS speaker, {text_col} AS text, confidence
            FROM speeches
            WHERE record_id = ?
            ORDER BY {order_by}
            """,
            (rec_id,),
        )
        speeches = cursor.fetchall()

        for s in speeches:
            text = (s["text"] or "").strip()
            if not text:
                continue

            confidence = s["confidence"] or 0.85
            speaker = s["speaker"] or "SPEAKER_01"
            duration = (s["end_time"] or 0.0) - (s["start_time"] or 0.0)

            ux, uy = hash_to_unit_coords(text)
            statute = extract_statute_category(text)
            severity = calculate_severity(text, confidence)
            rms = min(1.0, max(0.1, 0.2 + 0.6 * severity + (0.1 if len(text) > 40 else 0.0)))

            start_s = s["start_time"] or 0.0
            m, sec = divmod(int(start_s), 60)
            h, m = divmod(m, 60)
            timestamp_str = f"{h:02d}:{m:02d}:{sec:02d}"

            nodes.append(
                {
                    "id": f"node_{node_id_counter:04d}",
                    "record_id": rec_id,
                    "file_name": file_name,
                    "speaker": speaker,
                    "timestamp": timestamp_str,
                    "text": text,
                    "rmsIntensity": round(rms, 3),
                    "umapX": round(ux, 4),
                    "umapY": round(uy, 4),
                    "statuteCategory": statute,
                    "severity": round(severity, 3),
                    "yearOffset": round(year_offset, 3),
                }
            )
            node_id_counter += 1

    conn.close()

    payload = {
        "generated_at": datetime.now().isoformat(),
        "total_nodes": len(nodes),
        "total_records": len(records),
        "nodes": nodes,
    }

    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)

    logger.info(f"✅ Successfully exported 3D constellation ({len(nodes)} nodes) to {out}")
    return payload


def main():
    parser = argparse.ArgumentParser(description="AiVoiceTagger 3D Constellation Data Bridge")
    parser.add_argument("--db-path", type=str, default="aivoicetagger_state.db")
    parser.add_argument("--output", type=str, default="export/post_analytics/3d_constellation.json")
    parser.add_argument("--limit", type=int, default=50)
    parser.add_argument(
        "--anonymize",
        action="store_true",
        help="Enforce GDPR / LPD anonymization on exported 3D node labels",
    )

    args = parser.parse_args()
    generate_3d_constellation(
        db_path=args.db_path,
        output_path=args.output,
        limit_records=args.limit,
        anonymize=args.anonymize,
    )


if __name__ == "__main__":
    main()
