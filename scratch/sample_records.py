import sqlite3

db_path = r'c:\Dev\AiVoiceTagger\aivoicetagger_state.db'
conn = sqlite3.connect(db_path)
conn.row_factory = sqlite3.Row
cursor = conn.cursor()

query = "SELECT record_id, name, directory FROM records LIMIT 5"
cursor.execute(query)
res = cursor.fetchall()

for row in res:
    print(f"ID: {row['record_id']}, Name: {row['name']}, Dir: {row['directory']}")
