import sqlite3

db_path = r'c:\Dev\AiVoiceTagger\aivoicetagger_state.db'
conn = sqlite3.connect(db_path)
conn.row_factory = sqlite3.Row
cursor = conn.cursor()

cursor.execute("SELECT state, COUNT(*) as count FROM records GROUP BY state")
res = cursor.fetchall()
print("Record States in DB:")
for row in res:
    print(f"- {row['state']}: {row['count']}")

try:
    print("Testing claim_unprocessed_record query...")
    cursor.execute("""
        SELECT record_id, name, directory, date_record_day, date_last_write, length_bytes, COALESCE(processed_chunks, 0), lease_expires_at FROM records
        WHERE (UPPER(state) = 'DISCOVERED' OR UPPER(state) = 'QUEUED' OR UPPER(state) = 'DECODED' OR UPPER(state) = 'TRIAGEDHIGHINTEREST')
        AND (lease_expires_at IS NULL OR lease_expires_at < 9999999999)
        ORDER BY 
            CASE WHEN UPPER(state) = 'TRIAGEDHIGHINTEREST' THEN 1 ELSE 0 END DESC,
            COALESCE(priority, 0) DESC,
            length_bytes ASC
        LIMIT 5
    """)
    rows = cursor.fetchall()
    print(f"Found {len(rows)} matching rows!")
    for row in rows:
        print(f"- {row['record_id']} ({row['name']}) [lease={row['lease_expires_at']}]")
except Exception as e:
    print(f"Error executing query: {e}")

cursor.execute("SELECT record_id, name, state FROM records WHERE state NOT IN ('DONE', 'EXPORTED', 'DEAD_LETTER', 'FAILED') LIMIT 5")
pending = cursor.fetchall()
print("\nSome Pending Records:")
for row in pending:
    print(f"- {row['record_id']} | {row['name']} | {row['state']}")
