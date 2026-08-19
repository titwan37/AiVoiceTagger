import sqlite3
import sys

db_path = r'c:\Dev\AiVoiceTagger\aivoicetagger_state_interview.db'
try:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute("SELECT record_id, name, state, is_degraded, last_error FROM records")
    res = cursor.fetchall()
    print("Records in DB:")
    for row in res:
        print(f"ID: {row['record_id']} | Name: {row['name']} | State: {row['state']} | Err: {row['last_error']}")
        
        # Check if speeches exist
        cursor.execute("SELECT count(*) FROM speeches WHERE record_id = ?", (row['record_id'],))
        scount = cursor.fetchone()[0]
        print(f"  Speeches count: {scount}")
except Exception as e:
    print(f"Error: {e}")
