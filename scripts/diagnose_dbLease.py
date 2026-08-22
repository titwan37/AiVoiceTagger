#!/usr/bin/env python

import sqlite3
import sys

import os

# Default database path: resolve relative to this script's location
script_dir = os.path.dirname(os.path.abspath(__file__))
db_path = os.path.join(script_dir, '..', 'aivoicetagger_state.db')

# Get database path from command line argument if provided
if len(sys.argv) > 1:
    db_path = sys.argv[1]

try:
    print(f"Analyzing database: {db_path}")
    conn = sqlite3.connect(db_path)
    
    # Get table names
    tables = conn.execute("SELECT name FROM sqlite_master WHERE type='table';").fetchall()
    print(f"Tables found: {[t[0] for t in tables]}")
    
    # Check record counts by state
    print("\nRecord counts by state:")
    state_counts = conn.execute('SELECT state, COUNT(*) FROM records GROUP BY state').fetchall()
    for state, count in state_counts:
        print(f"  {state}: {count}")
    
    # Check lease ownership
    print("\nLease ownership distribution:")
    lease_counts = conn.execute('SELECT lease_owner, COUNT(*) FROM records WHERE lease_owner IS NOT NULL GROUP BY lease_owner').fetchall()
    if lease_counts:
        total_leased = sum(count for _, count in lease_counts)
        print(f"  Total leased records: {total_leased}")
        for owner, count in lease_counts:
            print(f"  {owner}: {count} ({count/total_leased:.1%})")
    else:
        print("  No records have active leases")
    
    # Check for degraded records
    degraded_count = conn.execute('SELECT COUNT(*) FROM records WHERE is_degraded = 1').fetchone()[0]
    print(f"\nDegraded records: {degraded_count}")
    
    # Check for stuck chunks (if chunk table exists)
    if 'chunks' in [t[0] for t in tables]:
        stuck_chunks = conn.execute(
            "SELECT state, COUNT(*) FROM chunks GROUP BY state"
        ).fetchall()
        print("\nChunk state distribution:")
        for state, count in stuck_chunks:
            print(f"  {state}: {count}")
    
    conn.close()
    
except sqlite3.Error as e:
    print(f"Database error: {e}")
    sys.exit(1)