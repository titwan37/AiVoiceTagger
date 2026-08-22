import sqlite3
import sys
import os
import argparse

# Parse arguments
parser = argparse.ArgumentParser(description="Release deadlocked leases in AiVoiceTagger database.")
parser.add_argument('--worker-id', type=str, help="Release leases only for a specific worker (e.g. pc-alpha-1). If omitted, releases ALL stale leases.", default=None)
parser.add_argument('--db-path', type=str, help="Path to aivoicetagger_state.db. Defaults to the one in the project root.", default=None)
args = parser.parse_args()

# Resolve database path relative to this script's location if not provided
if args.db_path:
    db_path = args.db_path
else:
    script_dir = os.path.dirname(os.path.abspath(__file__))
    db_path = os.path.join(script_dir, '..', 'aivoicetagger_state.db')

try:
    print(f"Connecting to database: {db_path}")
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Release leases for any record that is not DONE
    base_query = "UPDATE records SET lease_owner = NULL, lease_expires_at = NULL WHERE state != 'Done' AND state != 'DONE'"
    params = []
    
    if args.worker_id:
        base_query += " AND lease_owner = ?"
        params.append(args.worker_id)
        print(f"Targeting leases ONLY for worker: {args.worker_id}")
    else:
        print("Targeting ALL stale leases across all workers.")
        
    cursor.execute(base_query, params)
    cleared_count = cursor.rowcount
    conn.commit()
    
    print(f"Successfully cleared {cleared_count} stale leases!")
    
    # Let's also check if there is a 'chunks' table and release those leases just in case
    tables = cursor.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    if 'chunks' in [t[0] for t in tables]:
        try:
            chunk_query = "UPDATE chunks SET lease_owner = NULL, lease_expires_at = NULL WHERE state != 'Done' AND state != 'DONE'"
            if args.worker_id:
                chunk_query += " AND lease_owner = ?"
                cursor.execute(chunk_query, params)
            else:
                cursor.execute(chunk_query)
                
            chunks_cleared = cursor.rowcount
            conn.commit()
            if chunks_cleared > 0:
                print(f"Successfully cleared {chunks_cleared} stale chunk leases!")
        except sqlite3.OperationalError as e:
            if "no such column: lease_owner" in str(e):
                pass
            else:
                raise

    conn.close()
    
except sqlite3.Error as e:
    print(f"Database error: {e}")
    sys.exit(1)
