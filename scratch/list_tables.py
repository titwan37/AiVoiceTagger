import sqlite3

db_path = r'c:\Dev\AiVoiceTagger\aivoicetagger_state.db'
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
tables = cursor.fetchall()

print("Tables:")
for table in tables:
    print(table[0])

cursor.execute("SELECT record_id, name, directory FROM records LIMIT 5")
res = cursor.fetchall()
print("\nSample records:")
for row in res:
    print(f"ID: {row[0]}, Name: {row[1]}")
