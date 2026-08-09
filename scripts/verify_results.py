import sqlite3
import os
import sys
import json
from datetime import datetime

DB_PATH = "aivoicetagger_state.db"
EXPORT_DIR = "export"

def audit_database():
    if not os.path.exists(DB_PATH):
        print(f"❌ Database file '{DB_PATH}' not found.")
        return

    print("=" * 75)
    print(f"📊 AIVOICETAGGER ENHANCED RESULT REVIEW & AUDIT REPORT")
    print(f"Database: {os.path.abspath(DB_PATH)}")
    print(f"Time    : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 75)

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # 1. Processing State Breakdown
    cursor.execute("SELECT state, COUNT(*), SUM(duration_seconds) FROM records GROUP BY state ORDER BY COUNT(*) DESC;")
    state_counts = cursor.fetchall()
    
    print("\n--- 1. Processing State & Duration Breakdown ---")
    total_records = 0
    failed_count = 0
    done_count = 0
    total_seconds = 0.0

    for state, count, dur in state_counts:
        dur_hrs = (dur or 0.0) / 3600.0
        print(f"  • {state:<24}: {count:>5,} records  ({dur_hrs:>6.2f} hours audio)")
        total_records += count
        total_seconds += (dur or 0.0)
        if state in ("DeadLetter", "DEAD_LETTER", "Failed", "FAILED"):
            failed_count += count
        elif state in ("Done", "DONE", "EXPORTED", "TRANSCRIBED", "TriagedLowInterest", "TriagedHighInterest"):
            done_count += count
            
    print(f"\n  Total Audio Discovered   : {total_records:,} files ({total_seconds / 3600.0:.2f} hours)")
    print(f"  Processed / Triaged      : {done_count:,} ({done_count/total_records*100:.1f}%)" if total_records else "")
    print(f"  Interrupted / DeadLetter : {failed_count:,} ({failed_count/total_records*100:.1f}%)" if total_records else "")

    # 2. Audio Quality & Signal Breakdown
    cursor.execute("SELECT is_degraded, COUNT(*), AVG(duration_seconds) FROM records GROUP BY is_degraded;")
    degraded_counts = cursor.fetchall()
    print("\n--- 2. Audio Signal Quality Breakdown ---")
    for is_deg, count, avg_dur in degraded_counts:
        label = "Degraded / Low Confidence" if is_deg else "Good Quality Clear Audio"
        print(f"  • {label:<28}: {count:>5,} records  (avg {avg_dur:.1f}s / file)")

    # 3. High-Interest Watchlist Matches Breakdown
    cursor.execute("SELECT record_id, name, triage_keywords_json, story FROM records WHERE state = 'TriagedHighInterest' OR state = 'TriagedLowInterest' AND triage_keywords_json IS NOT NULL ORDER BY length_bytes DESC LIMIT 5;")
    high_interest = cursor.fetchall()
    if high_interest:
        print("\n--- 3. Top High-Interest Flagged Record Previews ---")
        for rec_id, name, kw_json, story in high_interest:
            kws = json.loads(kw_json) if kw_json else []
            preview = (story[:100] + "...") if story else "No text preview"
            print(f"  🚨 [{name[:40]}]")
            print(f"     Matched Keywords: {kws}")
            print(f"     Snippet Preview : {preview}\n")

    # 4. Dead Letter & Network Disconnection Root Causes
    cursor.execute("SELECT stage, error, COUNT(*) FROM dead_letter GROUP BY stage, error ORDER BY COUNT(*) DESC LIMIT 5;")
    dead_letters = cursor.fetchall()
    if dead_letters:
        print("--- 4. Dead-Letter & Failure Stage Breakdown ---")
        for stage, err, count in dead_letters:
            clean_err = err.split('\n')[0] if err else "Unknown Error"
            print(f"  • [{stage}] ({count:,} files): {clean_err[:85]}")
    else:
        # Fallback to records table last_error
        cursor.execute("SELECT last_error, COUNT(*) FROM records WHERE state = 'DeadLetter' AND last_error IS NOT NULL GROUP BY last_error ORDER BY COUNT(*) DESC LIMIT 5;")
        rec_errors = cursor.fetchall()
        if rec_errors:
            print("--- 4. Interruption Root Causes ---")
            for err, count in rec_errors:
                clean_err = err.split('\n')[0] if err else "Unknown Error"
                print(f"  • ({count:,} files): {clean_err[:85]}")

    # 5. Verification of Export Directory Artifacts
    print("\n--- 5. Export Artifact Verification ---")
    if os.path.exists(EXPORT_DIR):
        export_files = os.listdir(EXPORT_DIR)
        for ef in export_files:
            path = os.path.join(EXPORT_DIR, ef)
            if os.path.isfile(path):
                size_mb = os.path.getsize(path) / (1024 * 1024)
                print(f"  📄 {ef:<35}: {size_mb:>6.2f} MB")
    else:
        print("  ⚠️ Export directory not found.")

    print("\n" + "=" * 75)
    print("💡 ACTIONABLE RESUMPTION COMMANDS")
    print("=" * 75)
    print("1. To reset interrupted DeadLetter files back to DISCOVERED state:")
    print("   python -c \"import sqlite3; c=sqlite3.connect('aivoicetagger_state.db'); c.execute(\\\"UPDATE records SET state='DISCOVERED', lease_owner=NULL WHERE state IN ('DeadLetter','DEAD_LETTER','Failed','FAILED')\\\"); c.commit(); print('Reset done!')\"")
    print("2. Once NAS is connected, relaunch with Parakeet ONNX:\n   .\\bootstart.bat\n")

    conn.close()

if __name__ == "__main__":
    audit_database()

