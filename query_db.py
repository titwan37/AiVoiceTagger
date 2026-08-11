import sqlite3
import json

db_path = r'c:\Dev\AiVoiceTagger\aivoicetagger_state.db'

conn = sqlite3.connect(db_path)
conn.row_factory = sqlite3.Row
cursor = conn.cursor()

# 1. Total records and breakdown of states and degradation
cursor.execute("SELECT COUNT(*) FROM records")
total_records = cursor.fetchone()[0]

cursor.execute("SELECT state, COUNT(*) FROM records GROUP BY state")
state_counts = dict(cursor.fetchall())

cursor.execute("SELECT is_degraded, COUNT(*) FROM records GROUP BY is_degraded")
degraded_counts = dict(cursor.fetchall())

# Good samples count (state processed or triaged, non-degraded / high interest / good quality)
cursor.execute("SELECT COUNT(*) FROM records WHERE is_degraded = 0 AND (triage_summary IS NOT NULL OR story IS NOT NULL)")
good_samples_count = cursor.fetchone()[0]

# High interest / critical notice extracts
cursor.execute("""
    SELECT record_id, name, state, is_degraded, triage_keywords_json, triage_summary, story
    FROM records
    WHERE state = 'TriagedHighInterest' OR (triage_keywords_json IS NOT NULL AND triage_keywords_json != '[]' AND triage_keywords_json != '')
""")
high_interest_records = cursor.fetchall()

# Also general top-tier extracts / triaged records
cursor.execute("""
    SELECT record_id, name, state, is_degraded, triage_keywords_json, triage_summary, story
    FROM records
    WHERE (triage_summary IS NOT NULL AND triage_summary != '') OR (story IS NOT NULL AND story != '')
    ORDER BY is_degraded ASC, updated_at DESC
    LIMIT 30
""")
all_triage_records = cursor.fetchall()

output = []
output.append(f"Total Records in DB: {total_records}")
output.append(f"State Counts: {json.dumps(state_counts)}")
output.append(f"Degraded Breakdown (0=Good, 1=Degraded): {json.dumps(degraded_counts)}")
output.append(f"Good Samples Count (Non-degraded with text/summary): {good_samples_count}\n")

output.append("=== HIGH INTEREST / CRITICAL NOTICE EXTRACTS ===")
for r in high_interest_records:
    output.append(f"ID: {r['record_id']} | Name: {r['name']} | State: {r['state']} | Degraded: {r['is_degraded']}")
    output.append(f"Keywords: {r['triage_keywords_json']}")
    output.append(f"Triage Summary: {r['triage_summary']}")
    output.append(f"Story: {r['story']}")
    output.append("-" * 50)

output.append("\n=== TOP-TIER TRIAGED EXTRACTS SAMPLES ===")
for r in all_triage_records[:15]:
    output.append(f"ID: {r['record_id']} | Name: {r['name']} | State: {r['state']} | Degraded: {r['is_degraded']}")
    output.append(f"Keywords: {r['triage_keywords_json']}")
    output.append(f"Triage Summary: {r['triage_summary']}")
    output.append(f"Story: {r['story']}")
    output.append("-" * 50)

with open(r'c:\Dev\AiVoiceTagger\db_analysis.txt', 'w', encoding='utf-8') as f:
    f.write("\n".join(output))

print("Wrote analysis to db_analysis.txt")
