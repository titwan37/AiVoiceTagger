import sqlite3

db_path = r'c:\Dev\AiVoiceTagger\aivoicetagger_state.db'
conn = sqlite3.connect(db_path)
conn.row_factory = sqlite3.Row
cursor = conn.cursor()

cursor.execute("SELECT name FROM records")
res = cursor.fetchall()
with open(r'c:\Dev\AiVoiceTagger\scratch\all_names.txt', 'w', encoding='utf-8') as f:
    for row in res:
        f.write(f"{row['name']}\n")
