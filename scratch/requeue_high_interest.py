import sqlite3
import csv
import os

db_path = r'c:\Dev\AiVoiceTagger\aivoicetagger_state.db'
csv_path = r'c:\Dev\AiVoiceTagger\export\TriagedHighInterest.csv'

print(f"Using database: {db_path}")

conn = sqlite3.connect(db_path)
cursor = conn.cursor()

try:
    with open(csv_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        count = 0
        for row in reader:
            record_id = row['RecordID']
            # Reset state to TriagedHighInterest and processed_chunks to 0 so it runs from scratch
            cursor.execute("UPDATE records SET state = 'TriagedHighInterest', processed_chunks = 0 WHERE record_id = ?", (record_id,))
            if cursor.rowcount > 0:
                print(f"Re-queued {record_id} for High-Interest Heavy STT processing.")
                count += 1
            
        conn.commit()
        print(f"Successfully re-queued {count} records in the database.")
except FileNotFoundError:
    print(f"CSV file not found: {csv_path}")
except Exception as e:
    print(f"Error: {e}")
finally:
    conn.close()
