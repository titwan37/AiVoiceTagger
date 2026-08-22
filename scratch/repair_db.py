import sqlite3
import shutil
import os

db_path = r'c:\Dev\AiVoiceTagger\aivoicetagger_state.db'
backup_path = r'c:\Dev\AiVoiceTagger\aivoicetagger_state_corrupt_backup.db'
repaired_path = r'c:\Dev\AiVoiceTagger\aivoicetagger_state_repaired.db'

# Create backup if not already present
if not os.path.exists(backup_path):
    print("1. Creating backup of corrupt database files...")
    shutil.copy2(db_path, backup_path)
    for ext in ['-wal', '-shm']:
        if os.path.exists(db_path + ext):
            shutil.copy2(db_path + ext, backup_path + ext)
    print(f"Backup created at {backup_path}")

# Connect to corrupt DB
conn = sqlite3.connect(db_path)
conn.text_factory = lambda b: b.decode('utf-8', 'replace')
cursor = conn.cursor()

# Get table names
cursor.execute("SELECT name, sql FROM sqlite_master WHERE type='table'")
tables = cursor.fetchall()
print("Tables found:", [t[0] for t in tables])

# Prepare repaired database
if os.path.exists(repaired_path):
    os.remove(repaired_path)

conn_rep = sqlite3.connect(repaired_path)
cursor_rep = conn_rep.cursor()

# Enable WAL mode on repaired DB
cursor_rep.execute("PRAGMA journal_mode=WAL;")

# Recreate schema
for table_name, schema in tables:
    if table_name == 'sqlite_sequence':
        continue
    if schema:
        print(f"Creating schema for table: {table_name}")
        cursor_rep.execute(schema)

# Salvage table rows by rowid iteration
for table_name, _ in tables:
    if table_name == 'sqlite_sequence':
        continue

    cursor.execute(f"PRAGMA table_info('{table_name}')")
    cols = [info[1] for info in cursor.fetchall()]
    cols_str = ", ".join([f'"{c}"' for c in cols])
    placeholders = ", ".join(["?"] * len(cols))

    print(f"\nSalvaging rows from '{table_name}'...")

    # Find max rowid
    try:
        cursor.execute(f"SELECT MAX(rowid) FROM '{table_name}'")
        max_rowid = cursor.fetchone()[0] or 0
    except Exception as e:
        print(f"  Could not get max rowid for '{table_name}': {e}")
        max_rowid = 1000000  # Fallback

    saved_count = 0
    error_count = 0
    
    # Iterate through rowids to isolate corrupt pages
    for r_id in range(1, max_rowid + 1):
        try:
            cursor.execute(f"SELECT {cols_str} FROM '{table_name}' WHERE rowid = ?", (r_id,))
            row = cursor.fetchone()
            if row is not None:
                cursor_rep.execute(f"INSERT INTO '{table_name}' ({cols_str}) VALUES ({placeholders})", row)
                saved_count += 1
                if saved_count % 10000 == 0:
                    conn_rep.commit()
                    print(f"  Processed {saved_count} rows...")
        except Exception:
            error_count += 1
            continue

    conn_rep.commit()
    print(f"Finished table '{table_name}': {saved_count} rows saved, {error_count} corrupt rowids skipped.")

# Recreate indexes, triggers, views
cursor.execute("SELECT type, name, sql FROM sqlite_master WHERE type IN ('index', 'trigger', 'view') AND sql IS NOT NULL")
other_objects = cursor.fetchall()

for obj_type, obj_name, sql in other_objects:
    try:
        cursor_rep.execute(sql)
        print(f"Recreated {obj_type}: {obj_name}")
    except Exception as e:
        print(f"Could not recreate {obj_type} '{obj_name}': {e}")

conn_rep.commit()

# Run integrity check on repaired DB
res = cursor_rep.execute("PRAGMA integrity_check;").fetchall()
print("\nRepaired DB Integrity check result:", res)

conn.close()
conn_rep.close()

if res == [('ok',)]:
    print("\nRepair successfully completed! Replacing old database file...")
    # Remove existing WAL and SHM files of original DB so stale WAL doesn't overwrite repaired DB
    for ext in ['-wal', '-shm']:
        wal_file = db_path + ext
        if os.path.exists(wal_file):
            os.remove(wal_file)
            print(f"Removed stale WAL/SHM file: {wal_file}")
            
    # Replace original corrupt db with repaired db
    shutil.move(repaired_path, db_path)
    print(f"Replaced {db_path} with repaired database!")
