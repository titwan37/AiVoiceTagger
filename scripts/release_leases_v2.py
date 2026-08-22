import sqlite3
import argparse
import os

def main():
    parser = argparse.ArgumentParser(description="Release stale SQLite leases in AiVoiceTagger")
    parser.add_argument("--worker-id", type=str, help="Release leases for a specific worker ID (e.g. pc-alpha). If omitted, releases ALL stale leases.")
    parser.add_argument("--db-path", type=str, default=None, help="Path to SQLite database")
    args = parser.parse_args()

    if args.db_path:
        db_path = args.db_path
    else:
        # Always default to the db in the project root relative to this script
        script_dir = os.path.dirname(os.path.abspath(__file__))
        db_path = os.path.join(script_dir, '..', 'aivoicetagger_state.db')

    print(f"Connecting to database: {os.path.abspath(db_path)}")
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    if args.worker_id:
        print(f"Targeting leases ONLY for worker: {args.worker_id}")
        query = "UPDATE records SET lease_owner = NULL, lease_expires_at = NULL WHERE lease_owner = ? AND state != 'DONE'"
        cursor.execute(query, (args.worker_id,))
    else:
        print("Targeting ALL stale leases across ALL workers...")
        query = "UPDATE records SET lease_owner = NULL, lease_expires_at = NULL WHERE state != 'DONE'"
        cursor.execute(query)

    cleared = cursor.rowcount
    conn.commit()
    conn.close()
    print(f"✅ Successfully cleared {cleared} stale leases!")

if __name__ == "__main__":
    main()