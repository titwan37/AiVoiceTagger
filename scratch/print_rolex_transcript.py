import sqlite3
import time
import sys

db_path = r'c:\Dev\AiVoiceTagger\aivoicetagger_state_interview.db'

def get_transcript():
    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cursor.execute("SELECT state FROM records WHERE record_id = 'rec_rolex_interview'")
        row = cursor.fetchone()
        
        if not row:
            print("Record not found yet.")
            return False
            
        state = row['state']
        if state.upper() not in ('DONE', 'EXPORTED'):
            print(f"Still processing... Current state is: {state}")
            return False
            
        print("\nTranscription completed! Here is the transcript:\n" + "="*50)
        
        cursor.execute("SELECT time_frame, script FROM speeches WHERE record_id = 'rec_rolex_interview' ORDER BY offset_ms ASC")
        speeches = cursor.fetchall()
        
        if not speeches:
            print("No speeches found. Maybe no speech was detected?")
        else:
            for s in speeches:
                print(f"[{s['time_frame']}]: {s['script']}")
                
        print("="*50)
        return True

    except Exception as e:
        print(f"Database error: {e}")
        return False

if __name__ == "__main__":
    if not get_transcript():
        print("Run this script again once the pipeline says 'Pipeline finished.'")
