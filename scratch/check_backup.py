import sqlite3

backup_path = r'c:\Dev\AiVoiceTagger\aivoicetagger_state_corrupt_backup.db'

conn = sqlite3.connect(backup_path)
conn.text_factory = lambda b: b.decode('utf-8', 'replace')
cursor = conn.cursor()

found = 0
for r_id in range(7439, 50000):
    try:
        cursor.execute("SELECT rowid FROM speeches WHERE rowid = ?", (r_id,))
        row = cursor.fetchone()
        if row:
            found += 1
            print(f"Found rowid {r_id} in speeches!")
    except Exception:
        pass

print(f"Scan complete. Additional valid rows found in speeches: {found}")
