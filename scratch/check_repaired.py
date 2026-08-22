import sqlite3

conn = sqlite3.connect(r'c:\Dev\AiVoiceTagger\aivoicetagger_state.db')
cursor = conn.cursor()

for table in ['records', 'speeches', 'dead_letter']:
    cursor.execute(f"SELECT MAX(rowid), MIN(rowid), COUNT(*) FROM '{table}'")
    print(f"Table {table}: MIN={cursor.fetchone()}")
