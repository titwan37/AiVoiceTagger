import sqlite3
import shutil
import os

local_db = r"C:\Dev\AiVoiceTagger\aivoicetagger_state.db"
remote_db = r"X:\Dev\AiVoiceTagger\aivoicetagger_state.db"

print("Checking Local DB...")
if os.path.exists(local_db):
    try:
        conn = sqlite3.connect(local_db)
        cur = conn.cursor()
        print("Local PRAGMA integrity_check:", cur.execute("PRAGMA integrity_check;").fetchall())
        print("Checkpointing local WAL...")
        cur.execute("PRAGMA wal_checkpoint(TRUNCATE);")
        print("Setting local journal_mode = DELETE...")
        res = cur.execute("PRAGMA journal_mode = DELETE;").fetchall()
        print("Result:", res)
        conn.close()
        print("Local DB successfully switched to DELETE journal mode.")
    except Exception as e:
        print("Error with local DB:", e)

print("\nChecking Remote DB on X: ...")
if os.path.exists(remote_db):
    for ext in ["-wal", "-shm"]:
        p = remote_db + ext
        if os.path.exists(p):
            print(f"Found orphaned remote file: {p}, removing...")
            try:
                os.remove(p)
            except Exception as e:
                print(f"Could not remove {p}: {e}")
    try:
        conn = sqlite3.connect(remote_db)
        cur = conn.cursor()
        print("Remote PRAGMA integrity_check:", cur.execute("PRAGMA integrity_check;").fetchall())
        conn.close()
    except Exception as e:
        print("Remote DB integrity error:", e)
        print("\nReplacing remote DB with cleanly checkpointed local DB...")
        try:
            shutil.copy2(local_db, remote_db)
            print("Successfully copied clean local DB to remote X: drive!")
        except Exception as copy_err:
            print("Copy error:", copy_err)
