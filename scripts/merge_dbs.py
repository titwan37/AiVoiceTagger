#!/usr/bin/env python3
"""
scripts/merge_dbs.py — AiVoiceTagger Offline SQLite State Store Merger

Merges isolated worker databases (e.g., aivoicetagger_state_pc1.db, aivoicetagger_state_pc2.db)
into a central destination database with conflict resolution, tag deduplication, and atomic backups.
"""

import argparse
import json
import shutil
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

# State priority for conflict resolution (higher index = higher precedence)
STATE_PRIORITY = {
    "DISCOVERED": 1,
    "QUEUED": 2,
    "DECODED": 3,
    "TRANSCRIBED": 4,
    "NLPDONE": 5,
    "EXPORTED": 6,
    "DONE": 7
}

def get_state_rank(state_str: str) -> int:
    return STATE_PRIORITY.get(str(state_str).upper(), 0)

def parse_iso_time(time_str: str) -> float:
    if not time_str:
        return 0.0
    try:
        dt = datetime.fromisoformat(time_str.replace("Z", "+00:00"))
        return dt.timestamp()
    except Exception:
        return 0.0

def merge_databases(dest_path: Path, source_paths: list[Path], backup: bool = True):
    print("==================================================")
    print(" 🛠️ AiVoiceTagger Database Merger & Harmonizer")
    print("==================================================")
    print(f"Destination DB: {dest_path.resolve()}")
    print(f"Source DBs:     {[str(p.resolve()) for p in source_paths]}")

    # Verify sources exist
    valid_sources = []
    for s in source_paths:
        if s.exists():
            valid_sources.append(s)
        else:
            print(f"⚠️ Source database not found, skipping: {s}")

    if not valid_sources:
        print("❌ No valid source databases found to merge.")
        sys.exit(1)

    # Backup destination DB if it exists
    if dest_path.exists() and backup:
        backup_path = dest_path.with_suffix(".db.bak")
        shutil.copy2(dest_path, backup_path)
        print(f"🛡️ Created atomic backup copy: {backup_path.name}")

    dest_conn = sqlite3.connect(dest_path)
    dest_conn.row_factory = sqlite3.Row
    dest_cursor = dest_conn.cursor()

    # Ensure tables exist in destination DB
    dest_cursor.executescript("""
        CREATE TABLE IF NOT EXISTS records (
            record_id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            directory TEXT NOT NULL,
            date_record_day TEXT,
            date_last_write TEXT NOT NULL,
            length_bytes INTEGER NOT NULL,
            duration_seconds REAL NOT NULL,
            speech_count INTEGER NOT NULL,
            story TEXT NOT NULL,
            stats_verbatim_json TEXT NOT NULL,
            state TEXT NOT NULL,
            is_degraded INTEGER NOT NULL,
            attempts INTEGER DEFAULT 0,
            last_error TEXT,
            lease_owner TEXT,
            lease_expires_at INTEGER,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS speeches (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            record_id TEXT NOT NULL,
            time_frame TEXT NOT NULL,
            script TEXT NOT NULL,
            confidence REAL NOT NULL,
            word_count INTEGER NOT NULL,
            offset_ms INTEGER NOT NULL,
            duration_ms INTEGER NOT NULL,
            words_json TEXT,
            FOREIGN KEY(record_id) REFERENCES records(record_id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS chunks (
            chunk_id TEXT PRIMARY KEY,
            record_id TEXT NOT NULL,
            start_ms INTEGER NOT NULL,
            end_ms INTEGER NOT NULL,
            state TEXT NOT NULL,
            transcript_text TEXT,
            confidence REAL,
            attempts INTEGER DEFAULT 0,
            last_error TEXT,
            updated_at TEXT NOT NULL,
            FOREIGN KEY(record_id) REFERENCES records(record_id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS dead_letter (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            record_id TEXT,
            chunk_id TEXT,
            stage TEXT NOT NULL,
            error TEXT NOT NULL,
            context_json TEXT,
            created_at TEXT NOT NULL
        );
    """)

    total_records_inserted = 0
    total_conflicts_resolved = 0
    total_speeches_inserted = 0
    total_chunks_inserted = 0
    total_dead_letters_inserted = 0

    dest_conn.execute("BEGIN TRANSACTION")

    try:
        for src_path in valid_sources:
            print(f"\n📂 Processing source database: {src_path.name}")
            src_conn = sqlite3.connect(src_path)
            src_conn.row_factory = sqlite3.Row
            src_cursor = src_conn.cursor()

            # 1. Merge Records Table
            src_cursor.execute("SELECT * FROM records")
            src_records = src_cursor.fetchall()

            for s_rec in src_records:
                record_id = s_rec["record_id"]
                dest_cursor.execute("SELECT * FROM records WHERE record_id = ?", (record_id,))
                d_rec = dest_cursor.fetchone()

                if d_rec is None:
                    # Insert new record
                    dest_cursor.execute("""
                        INSERT INTO records (
                            record_id, name, directory, date_record_day, date_last_write,
                            length_bytes, duration_seconds, speech_count, story,
                            stats_verbatim_json, state, is_degraded, attempts, last_error,
                            lease_owner, lease_expires_at, created_at, updated_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, tuple(s_rec[col] for col in s_rec.keys()))
                    total_records_inserted += 1
                else:
                    # Conflict Resolution: evaluate state rank & updated_at timestamp
                    s_rank = get_state_rank(s_rec["state"])
                    d_rank = get_state_rank(d_rec["state"])
                    s_ts = parse_iso_time(s_rec["updated_at"])
                    d_ts = parse_iso_time(d_rec["updated_at"])

                    should_update = False
                    if s_rank > d_rank:
                        should_update = True
                    elif s_rank == d_rank and s_ts > d_ts:
                        should_update = True
                    elif len(s_rec["story"]) > len(d_rec["story"]):
                        should_update = True

                    if should_update:
                        dest_cursor.execute("""
                            UPDATE records SET
                                name = ?, directory = ?, date_record_day = ?, date_last_write = ?,
                                length_bytes = ?, duration_seconds = ?, speech_count = ?, story = ?,
                                stats_verbatim_json = ?, state = ?, is_degraded = ?, attempts = ?,
                                last_error = ?, lease_owner = ?, lease_expires_at = ?, updated_at = ?
                            WHERE record_id = ?
                        """, (
                            s_rec["name"], s_rec["directory"], s_rec["date_record_day"], s_rec["date_last_write"],
                            s_rec["length_bytes"], s_rec["duration_seconds"], s_rec["speech_count"], s_rec["story"],
                            s_rec["stats_verbatim_json"], s_rec["state"], s_rec["is_degraded"], s_rec["attempts"],
                            s_rec["last_error"], s_rec["lease_owner"], s_rec["lease_expires_at"], s_rec["updated_at"],
                            record_id
                        ))
                        total_conflicts_resolved += 1

            # 2. Merge Speeches Table
            src_cursor.execute("SELECT * FROM speeches")
            for sp in src_cursor.fetchall():
                dest_cursor.execute("""
                    SELECT id FROM speeches 
                    WHERE record_id = ? AND offset_ms = ? AND script = ?
                """, (sp["record_id"], sp["offset_ms"], sp["script"]))
                if dest_cursor.fetchone() is None:
                    dest_cursor.execute("""
                        INSERT INTO speeches (
                            record_id, time_frame, script, confidence, word_count,
                            offset_ms, duration_ms, words_json
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        sp["record_id"], sp["time_frame"], sp["script"], sp["confidence"],
                        sp["word_count"], sp["offset_ms"], sp["duration_ms"], sp["words_json"]
                    ))
                    total_speeches_inserted += 1

            # 3. Merge Chunks Table
            src_cursor.execute("SELECT * FROM chunks")
            for ch in src_cursor.fetchall():
                dest_cursor.execute("SELECT chunk_id FROM chunks WHERE chunk_id = ?", (ch["chunk_id"],))
                if dest_cursor.fetchone() is None:
                    dest_cursor.execute("""
                        INSERT INTO chunks (
                            chunk_id, record_id, start_ms, end_ms, state,
                            transcript_text, confidence, attempts, last_error, updated_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        ch["chunk_id"], ch["record_id"], ch["start_ms"], ch["end_ms"], ch["state"],
                        ch["transcript_text"], ch["confidence"], ch["attempts"], ch["last_error"], ch["updated_at"]
                    ))
                    total_chunks_inserted += 1

            # 4. Merge Dead Letter Queue
            src_cursor.execute("SELECT * FROM dead_letter")
            for dl in src_cursor.fetchall():
                dest_cursor.execute("""
                    INSERT INTO dead_letter (record_id, chunk_id, stage, error, context_json, created_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (dl["record_id"], dl["chunk_id"], dl["stage"], dl["error"], dl["context_json"], dl["created_at"]))
                total_dead_letters_inserted += 1

            src_conn.close()

        dest_conn.commit()
        print("\n==================================================")
        print(" 🎉 MERGE SUMMARY REPORT")
        print("==================================================")
        print(f"  • Total Records Inserted:     {total_records_inserted}")
        print(f"  • Conflicts Resolved/Updated: {total_conflicts_resolved}")
        print(f"  • Speeches Deduped/Merged:    {total_speeches_inserted}")
        print(f"  • Chunks Merged:             {total_chunks_inserted}")
        print(f"  • Dead Letters Merged:       {total_dead_letters_inserted}")
        print("==================================================")

    except Exception as e:
        dest_conn.rollback()
        print(f"\n❌ Error during database merge. Transaction rolled back: {e}")
        dest_conn.close()
        sys.exit(1)

    dest_conn.close()

def main():
    parser = argparse.ArgumentParser(description="Merge isolated AiVoiceTagger SQLite databases into a central database.")
    parser.add_argument("--dest", type=Path, default=Path("aivoicetagger_state.db"), help="Destination central database path")
    parser.add_argument("--sources", type=Path, nargs="+", required=True, help="List of source SQLite database paths to merge")
    parser.add_argument("--no-backup", action="store_true", help="Disable automatic backup creation of destination DB")

    args = parser.parse_args()
    merge_databases(args.dest, args.sources, backup=not args.no_backup)

if __name__ == "__main__":
    main()
