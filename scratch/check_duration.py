import sqlite3

db_path = r'c:\Dev\AiVoiceTagger\aivoicetagger_state_interview.db'
try:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute("SELECT duration_seconds, length_bytes FROM records WHERE record_id = 'rec_rolex_interview'")
    row = cursor.fetchone()
    if row:
        print(f"Duration: {row['duration_seconds']}s")
        print(f"Length: {row['length_bytes']} bytes")
    else:
        print("Record not found.")
except Exception as e:
    print(e)
