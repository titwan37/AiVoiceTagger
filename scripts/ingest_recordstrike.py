#!/usr/bin/env python3
"""
ingest_recordstrike.py — Ingest RecordStrike & Select_Sort pre-selected files
into aivoicetagger_state.db with highest processing priority.

Reads inventory_pc1.csv and inventory_pc2.csv, filters for directories containing
'RecordStrike', 'Select_Sort', or 'Time_Sort', and inserts them into the records
table with priority = 10 (RecordStrike/Select_Sort) or priority = 5 (Time_Sort).

Usage:
    python scripts/ingest_recordstrike.py
"""

import csv
import sqlite3
import hashlib
from pathlib import Path
from datetime import datetime, timezone

BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = BASE_DIR / "aivoicetagger_state.db"

# Priority tiers for directory-based classification
PRIORITY_MAP = {
    "RecordStrike": 10,
    "Select_Sort": 10,
    "Time_Sort": 5,
}

# Default priority for unclassified directories
DEFAULT_PRIORITY = 0


def classify_priority(directory: str) -> int:
    """Return the highest matching priority tier for a directory path."""
    best = DEFAULT_PRIORITY
    for key, prio in PRIORITY_MAP.items():
        if key.lower() in directory.lower():
            best = max(best, prio)
    return best


def ingest_inventory(csv_path: Path, conn: sqlite3.Connection, dry_run: bool = False):
    """Read an inventory CSV and insert priority records into the state DB."""
    if not csv_path.exists():
        print(f"  ⚠ Inventory file not found: {csv_path}")
        return 0, 0, 0

    cursor = conn.cursor()
    inserted = 0
    skipped_existing = 0
    skipped_low_priority = 0

    with open(csv_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            directory = row.get("directory", "")
            priority = classify_priority(directory)

            if priority == DEFAULT_PRIORITY:
                skipped_low_priority += 1
                continue

            record_id = row.get("record_id", "")
            name = row.get("name", "")
            length_bytes = int(row.get("length_bytes", 0))
            date_record_day = row.get("date_record_day", "") or None
            date_last_write = row.get("date_last_write", "") or datetime.now(timezone.utc).isoformat()

            if not record_id or not name:
                continue

            # Check if record already exists
            existing = cursor.execute(
                "SELECT record_id, priority FROM records WHERE record_id = ?",
                (record_id,)
            ).fetchone()

            now_iso = datetime.now(timezone.utc).isoformat()

            if existing:
                # Update priority if the new priority is higher
                current_priority = existing[1] if existing[1] is not None else 0
                if priority > current_priority:
                    cursor.execute(
                        "UPDATE records SET priority = ?, updated_at = ? WHERE record_id = ?",
                        (priority, now_iso, record_id)
                    )
                    inserted += 1
                else:
                    skipped_existing += 1
            else:
                # Insert new record with priority
                cursor.execute("""
                    INSERT INTO records (
                        record_id, name, directory, date_record_day, date_last_write,
                        length_bytes, duration_seconds, speech_count, story,
                        stats_verbatim_json, state, is_degraded, priority,
                        created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, 0.0, 0, '', '{}', 'Discovered', 0, ?, ?, ?)
                """, (
                    record_id, name, directory, date_record_day, date_last_write,
                    length_bytes, priority, now_iso, now_iso
                ))
                inserted += 1

    if not dry_run:
        conn.commit()

    return inserted, skipped_existing, skipped_low_priority


def ensure_priority_column(conn: sqlite3.Connection):
    """Add priority column to records table if it doesn't exist."""
    cursor = conn.cursor()
    # Check if column exists
    cursor.execute("PRAGMA table_info(records)")
    columns = [row[1] for row in cursor.fetchall()]
    if "priority" not in columns:
        print("  📐 Adding 'priority' column to records table...")
        cursor.execute("ALTER TABLE records ADD COLUMN priority INTEGER DEFAULT 0")
        conn.commit()
        print("  ✅ Column 'priority' added successfully.")
    else:
        print("  ✅ Column 'priority' already exists.")


def update_existing_priorities(conn: sqlite3.Connection):
    """Set priority for existing records based on their directory paths."""
    cursor = conn.cursor()
    updated = 0

    for key, prio in PRIORITY_MAP.items():
        cursor.execute(
            "UPDATE records SET priority = ? WHERE directory LIKE ? AND (priority IS NULL OR priority < ?)",
            (prio, f"%{key}%", prio)
        )
        count = cursor.rowcount
        if count > 0:
            print(f"  🔄 Updated {count} existing records matching '{key}' → priority={prio}")
            updated += count

    conn.commit()
    return updated


def print_priority_summary(conn: sqlite3.Connection):
    """Print a summary of records by priority tier."""
    cursor = conn.cursor()
    cursor.execute("""
        SELECT 
            COALESCE(priority, 0) as prio,
            state,
            COUNT(*) as cnt
        FROM records
        GROUP BY prio, state
        ORDER BY prio DESC, state
    """)
    rows = cursor.fetchall()

    print("\n" + "=" * 70)
    print("📊 RECORD PRIORITY & STATE SUMMARY")
    print("=" * 70)

    current_prio = None
    for prio, state, cnt in rows:
        if prio != current_prio:
            label = {10: "🚨 CRITICAL (RecordStrike/Select_Sort)", 5: "⚡ HIGH (Time_Sort)", 0: "📁 DEFAULT"}.get(prio, f"Priority {prio}")
            print(f"\n  Priority {prio} — {label}")
            current_prio = prio
        print(f"    {state:30s} {cnt:>6,} records")

    # Total counts
    cursor.execute("SELECT COUNT(*) FROM records WHERE COALESCE(priority, 0) >= 10")
    critical = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM records WHERE COALESCE(priority, 0) >= 5 AND COALESCE(priority, 0) < 10")
    high = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM records")
    total = cursor.fetchone()[0]

    print(f"\n  {'─' * 50}")
    print(f"  🚨 Critical Priority (≥10): {critical:>6,} records")
    print(f"  ⚡ High Priority (5-9):     {high:>6,} records")
    print(f"  📁 Total Records:           {total:>6,} records")
    print("=" * 70)


def main():
    print("=" * 70)
    print("🚨 AiVoiceTagger — RecordStrike Priority Ingestion")
    print(f"   Database: {DB_PATH}")
    print(f"   Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 70)

    if not DB_PATH.exists():
        print(f"❌ Database not found: {DB_PATH}")
        return

    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row

    # Step 1: Ensure priority column exists
    print("\n📐 Step 1: Schema Migration")
    ensure_priority_column(conn)

    # Step 2: Update priorities for existing records
    print("\n🔄 Step 2: Updating priorities for existing records in DB...")
    updated = update_existing_priorities(conn)
    print(f"  Updated {updated} existing records with priority scores.")

    # Step 3: Ingest from inventory CSVs
    inventory_files = [
        BASE_DIR / "inventory_pc1.csv",
        BASE_DIR / "inventory_pc2.csv",
    ]

    total_inserted = 0
    total_skipped_existing = 0
    total_skipped_low = 0

    print("\n📥 Step 3: Ingesting priority records from inventory CSVs...")
    for inv_path in inventory_files:
        print(f"\n  Processing: {inv_path.name}")
        inserted, skipped_existing, skipped_low = ingest_inventory(inv_path, conn)
        total_inserted += inserted
        total_skipped_existing += skipped_existing
        total_skipped_low += skipped_low
        print(f"    ✅ Inserted/Updated: {inserted}")
        print(f"    ⏭  Skipped (already exists): {skipped_existing}")
        print(f"    💤 Skipped (low priority): {skipped_low}")

    print(f"\n  📊 Total ingested/updated: {total_inserted}")
    print(f"  📊 Total skipped (existing): {total_skipped_existing}")
    print(f"  📊 Total skipped (low priority): {total_skipped_low}")

    # Step 4: Summary
    print_priority_summary(conn)

    conn.close()
    print("\n🎉 RecordStrike ingestion complete!")


if __name__ == "__main__":
    main()
