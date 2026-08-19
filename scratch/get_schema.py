import sqlite3

db_path = r'c:\Dev\AiVoiceTagger\aivoicetagger_state.db'
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

cursor.execute("PRAGMA table_info(records)")
res = cursor.fetchall()
for row in res:
    print(row)
