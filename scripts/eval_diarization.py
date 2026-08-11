import sqlite3
import json
from pathlib import Path

db_path = Path(r"c:\Dev\AiVoiceTagger\aivoicetagger_state.db")
if not db_path.exists():
    print("Database file not found at", db_path)
    exit(1)

conn = sqlite3.connect(db_path)
conn.row_factory = sqlite3.Row
cursor = conn.cursor()

# Check total records and states
cursor.execute("SELECT state, COUNT(*) FROM records GROUP BY state")
print("=== Record States ===")
for row in cursor.fetchall():
    print(f"State: {row[0]} -> {row[1]}")

# Check speeches count
cursor.execute("SELECT COUNT(*) FROM speeches")
speeches_count = cursor.fetchone()[0]
print(f"\nTotal Speeches / Diarization segments stored: {speeches_count}")

# Fetch top 3 records with highest speech counts
cursor.execute("""
    SELECT record_id, name, directory, duration_seconds, speech_count, story, triage_summary, updated_at
    FROM records
    WHERE speech_count > 0
    ORDER BY speech_count DESC
    LIMIT 5
""")
records = cursor.fetchall()
print(f"\n=== Top Records with Diarization (showing {len(records)}) ===")
for r in records:
    print(f"\nRecord ID: {r['record_id']}")
    print(f"File Name: {r['name']}")
    print(f"Duration: {r['duration_seconds']:.1f}s | Speeches Count: {r['speech_count']}")
    print(f"Summary / Story: {r['triage_summary'] or r['story']}")
    
    # Fetch speeches for this record
    cursor.execute("""
        SELECT time_frame, script, confidence, word_count, offset_ms, duration_ms
        FROM speeches
        WHERE record_id = ?
        ORDER BY offset_ms ASC
        LIMIT 10
    """, (r['record_id'],))
    speeches = cursor.fetchall()
    print("--- Diarization Segments (First 10) ---")
    for s in speeches:
        start_s = s['offset_ms'] / 1000.0
        end_s = (s['offset_ms'] + s['duration_ms']) / 1000.0
        print(f"  [{start_s:6.1f}s -> {end_s:6.1f}s] ({s['time_frame']}) Conf: {s['confidence']:.2f} | Text: {s['script']}")

conn.close()
