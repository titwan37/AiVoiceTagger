import sqlite3

db_path = r'c:\Dev\AiVoiceTagger\aivoicetagger_state.db'
conn = sqlite3.connect(db_path)
conn.row_factory = sqlite3.Row
cursor = conn.cursor()

cursor.execute("SELECT state, COUNT(*) as count FROM records GROUP BY state")
res = cursor.fetchall()
print("Record States in DB:")
for row in res:
    print(f"- {row['state']}: {row['count']}")

cursor.execute("SELECT record_id, name, state FROM records WHERE state NOT IN ('DONE', 'EXPORTED', 'DEAD_LETTER', 'FAILED') LIMIT 5")
pending = cursor.fetchall()
print("\nSome Pending Records:")
for row in pending:
    print(f"- {row['record_id']} | {row['name']} | {row['state']}")
