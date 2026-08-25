import sqlite3
import argparse
import sys
from datetime import datetime, timedelta, timezone

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

db_path = r"c:\Dev\AiVoiceTagger\aivoicetagger_state.db"

def query_history(hours: float, limit: int = 100):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cutoff_dt = datetime.now(timezone.utc) - timedelta(hours=hours)
    cutoff_iso = cutoff_dt.isoformat()

    cursor.execute("""
        SELECT 
            record_id,
            name,
            directory,
            state,
            is_degraded,
            lease_owner,
            updated_at,
            triage_summary,
            story
        FROM records
        WHERE updated_at >= ?
        ORDER BY updated_at DESC
        LIMIT ?
    """, (cutoff_iso, limit))

    rows = cursor.fetchall()

    print("====================================================================================================")
    print(f" PROCESSED RECORDS HISTORY (LAST {hours} HOURS) -- TOTAL MATCHES: {len(rows)}")
    print("====================================================================================================\n")

    if not rows:
        print(f"No records were processed in the last {hours} hours (since {cutoff_iso}).")
        return

    for idx, r in enumerate(rows, 1):
        directory = r['directory'] or ''
        if 'RecordStrike' in directory:
            origin_category = "Priority RecordStrike List"
        elif 'Select_Sort' in directory:
            origin_category = "Select_Sort Focus List"
        elif '2026' in directory:
            origin_category = "2026 Active Ingestion"
        elif '2024' in directory:
            origin_category = "2024 Historical Archive"
        else:
            origin_category = f"Directory: {directory}"

        treatment = r['state']
        worker = r['lease_owner'] or 'Unknown Worker'
        quality = "DEGRADED" if r['is_degraded'] else "GOOD"
        timestamp = r['updated_at']

        print(f"[{idx}] FILE: {r['name']}")
        print(f"    |- Origin / Category : {origin_category}")
        print(f"    |- Full Path        : {directory}\\{r['name']}")
        print(f"    |- Treated State     : {treatment} (Quality: {quality})")
        print(f"    |- Processed By      : {worker}")
        print(f"    |- Timestamp         : {timestamp}")
        if r['triage_summary']:
            print(f"    |- Summary          : {r['triage_summary'][:150]}...")
        elif r['story']:
            print(f"    |- Verbatim Extract : {r['story'][:150]}...")
        print()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Query AiVoiceTagger recent processing history.")
    parser.add_argument("--hours", type=float, default=1.0, help="Time window in hours (e.g., 1, 4, 12, 24)")
    parser.add_argument("--limit", type=int, default=50, help="Maximum number of records to list")
    args = parser.parse_args()

    query_history(args.hours, args.limit)
