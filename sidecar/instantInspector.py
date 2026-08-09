import sqlite3
import json
import csv
from pathlib import Path
from datetime import datetime, timezone

now_dt = datetime.now()
now_iso = now_dt.strftime("%Y-%m-%d %H:%M:%S")
timestamp_prefix = now_dt.strftime("%Y%m%d_%H%M%S")

base_dir = Path(__file__).resolve().parent.parent
db_path = base_dir / "aivoicetagger_state.db"
export_dir = base_dir / "export"
export_dir.mkdir(exist_ok=True)

print(f"Connecting to database: {db_path.resolve()}")
if not db_path.exists():
    print(f"❌ Database file does NOT exist at {db_path.resolve()}")
    exit(1)

conn = sqlite3.connect(db_path)
conn.row_factory = sqlite3.Row
cursor = conn.cursor()

print(f"\n--- 📊 DATABASE TABLE SUMMARY [{now_iso}] ---")

# Check records count by state
try:
    cursor.execute("SELECT state, COUNT(*) FROM records GROUP BY state")
    record_states = cursor.fetchall()
    print("Records count by state:")
    if not record_states:
        print("  (No rows in 'records' table)")
    for row in record_states:
        print(f"  • {row[0]}: {row[1]}")
except Exception as e:
    print(f"Error querying 'records': {e}")

# Check speeches count
try:
    cursor.execute("SELECT COUNT(*) FROM speeches")
    speech_cnt = cursor.fetchone()[0]
    print(f"\nTotal Speeches / Transcribed Segments: {speech_cnt}")
except Exception as e:
    print(f"Error querying 'speeches': {e}")

# Check chunks count by state
try:
    cursor.execute("SELECT state, COUNT(*) FROM chunks GROUP BY state")
    chunk_states = cursor.fetchall()
    print("\nChunks count by state:")
    if not chunk_states:
        print("  (No rows in 'chunks' table)")
    for row in chunk_states:
        print(f"  • {row[0]}: {row[1]}")
except Exception as e:
    print(f"Error querying 'chunks': {e}")

# Check dead_letter count
try:
    cursor.execute("SELECT COUNT(*) FROM dead_letter")
    dead_cnt = cursor.fetchone()[0]
    print(f"\nDead Letter / Failures count: {dead_cnt}")
except Exception as e:
    print(f"Error querying 'dead_letter': {e}")

# Fetch all records regardless of state to export whatever is available
cursor.execute("""
    SELECT record_id, name, directory, date_record_day, date_last_write, 
           length_bytes, duration_seconds, speech_count, story, 
           stats_verbatim_json, state, is_degraded, updated_at
    FROM records
""")
rows = cursor.fetchall()

print(f"\nTotal records fetched for export: {len(rows)}")

# Export to timestamped CSV & update Live_RecordList.csv
timestamped_filename = f"{timestamp_prefix}_Live_RecordList.csv"
timestamped_csv_path = export_dir / timestamped_filename
latest_csv_path = export_dir / "Live_RecordList.csv"

def write_csv_report(target_path):
    with open(target_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([
            "RecordID", "Name", "Directory", "DateRecordDay", "DateLastWrite",
            "DurationSeconds", "SpeechCount", "IsDegraded", "State", "UpdatedAt",
            "ReportGeneratedAt", "Transcript"
        ])
        for r in rows:
            writer.writerow([
                r["record_id"], r["name"], r["directory"], r["date_record_day"],
                r["date_last_write"], r["duration_seconds"], r["speech_count"],
                bool(r["is_degraded"]), r["state"], r["updated_at"],
                now_iso, r["story"]
            ])

write_csv_report(timestamped_csv_path)
write_csv_report(latest_csv_path)

print(f"✅ Timestamped Export: {timestamped_csv_path.resolve()}")
print(f"✅ Latest Export File: {latest_csv_path.resolve()}")
conn.close()
