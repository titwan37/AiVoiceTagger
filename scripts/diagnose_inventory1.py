import csv
import sqlite3
import os

# Resolve paths relative to this script
script_dir = os.path.dirname(os.path.abspath(__file__))
db_path = os.path.join(script_dir, '..', 'aivoicetagger_state.db')
csv_path = os.path.join(script_dir, '..', 'inventory_pc1.csv')

def main():
    print(f"Connecting to DB: {os.path.abspath(db_path)}")
    conn = sqlite3.connect(db_path)
    
    print(f"Reading from CSV: {os.path.abspath(csv_path)}")
    with open(csv_path, 'r', encoding='utf-8') as f:
        reader = csv.reader(f)
        records = [row[0] for row in reader if row and row[0].strip()]
    
    # Process in chunks of 900 to safely stay under SQLite's default 999 parameter limit
    chunk_size = 900
    state_totals = {}
    
    for i in range(0, len(records), chunk_size):
        chunk = records[i:i + chunk_size]
        placeholders = ",".join(["?"] * len(chunk))
        query = f"SELECT state, COUNT(*) FROM records WHERE record_id IN ({placeholders}) GROUP BY state"
        
        results = conn.execute(query, chunk).fetchall()
        for state, count in results:
            state_totals[state] = state_totals.get(state, 0) + count
            
    print(f"DB states for ALL {len(records)} records in inventory_pc1.csv:")
    # Sort for cleaner output
    for state, count in sorted(state_totals.items()):
        print(f"  {state}: {count}")
        
    conn.close()

if __name__ == "__main__":
    main()
