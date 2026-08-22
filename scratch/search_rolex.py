import sqlite3
import json

db_path = r'c:\Dev\AiVoiceTagger\aivoicetagger_state.db'
conn = sqlite3.connect(db_path)
conn.row_factory = sqlite3.Row
cursor = conn.cursor()

query = "SELECT record_id, name, story, triage_summary FROM records WHERE name LIKE '%Rolex%'"
cursor.execute(query)
res = cursor.fetchall()

if not res:
    print("No Rolex records found.")
else:
    for row in res:
        print(f"ID: {row['record_id']}")
        print(f"Name: {row['name']}")
        print(f"Summary: {row['triage_summary']}")
        print(f"Story: {row['story']}")
