import sqlite3
remote_db = r"X:\Dev\AiVoiceTagger\aivoicetagger_state.db"
conn = sqlite3.connect(remote_db)
cur = conn.cursor()
print("Remote DB integrity:", cur.execute("PRAGMA integrity_check;").fetchall())
print("Remote DB journal_mode:", cur.execute("PRAGMA journal_mode;").fetchall())
cur.execute("SELECT count(*) FROM records;")
print("Total records in remote DB:", cur.fetchone()[0])
conn.close()
