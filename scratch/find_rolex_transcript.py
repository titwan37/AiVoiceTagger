import sqlite3

db_path = r'c:\Dev\AiVoiceTagger\aivoicetagger_state_interview.db'
conn = sqlite3.connect(db_path)
conn.row_factory = sqlite3.Row
cursor = conn.cursor()

# Find the record
cursor.execute("SELECT record_id, name, directory FROM records WHERE name LIKE '%Rolex%' OR name LIKE '%260818%' OR directory LIKE '%Rolex%'")
res = cursor.fetchall()
if not res:
    print("No matching records found in 'records' table.")
else:
    for row in res:
        record_id = row['record_id']
        name = row['name']
        print(f"Found record: ID={record_id}, Name={name}")
        
        # Now get the speeches for this record_id
        print(f"--- Speeches for {name} ---")
        cursor.execute("SELECT time_frame, script FROM speeches WHERE record_id = ? ORDER BY offset_ms ASC", (record_id,))
        speeches = cursor.fetchall()
        for speech in speeches:
            print(f"[{speech['time_frame']}]: {speech['script']}")
        
        # If speeches is empty, maybe chunks?
        if not speeches:
            print(f"--- Chunks for {name} ---")
            cursor.execute("SELECT transcript_text FROM chunks WHERE record_id = ? ORDER BY start_ms ASC", (record_id,))
            chunks = cursor.fetchall()
            for chunk in chunks:
                print(chunk['transcript_text'])
