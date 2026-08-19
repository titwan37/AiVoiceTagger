import sqlite3
import json
import sys

db_path = r'c:\Dev\AiVoiceTagger\aivoicetagger_state.db'
conn = sqlite3.connect(db_path)
conn.row_factory = sqlite3.Row
cursor = conn.cursor()

query = "SELECT transcript, triage_summary, story FROM records WHERE name LIKE '%Voix 260818_141209 Rolex.m4a%'"
cursor.execute(query)
res = cursor.fetchall()

if not res:
    print("No records found.")
else:
    for row in res:
        print("=== Transcript ===")
        print(row['transcript'])
        print("=== Summary ===")
        print(row['triage_summary'])
        print("=== Story ===")
        print(row['story'])
