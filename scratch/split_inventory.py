import csv
from pathlib import Path

def split_manifest():
    manifest_path = Path("C:/Dev/AiVoiceTagger/inventory_manifest.csv")
    out1_path = Path("C:/Dev/AiVoiceTagger/export/batch_pc1.csv")
    out2_path = Path("C:/Dev/AiVoiceTagger/export/batch_pc2.csv")
    
    if not manifest_path.exists():
        print(f"Manifest not found: {manifest_path}")
        return
        
    with open(manifest_path, 'r', encoding='utf-8') as f:
        reader = csv.reader(f)
        header = next(reader)
        rows = list(reader)
        
    # Split 50/50 alternating
    pc1_rows = rows[0::2]
    pc2_rows = rows[1::2]
    
    # Write PC1
    with open(out1_path, 'w', encoding='utf-8', newline='') as f1:
        w = csv.writer(f1)
        w.writerow(header)
        w.writerows(pc1_rows)
        
    # Write PC2
    with open(out2_path, 'w', encoding='utf-8', newline='') as f2:
        w = csv.writer(f2)
        w.writerow(header)
        w.writerows(pc2_rows)
        
    print(f"✅ Successfully split {len(rows)} records!")
    print(f"PC 1 Batch: {len(pc1_rows)} records saved to {out1_path}")
    print(f"PC 2 Batch: {len(pc2_rows)} records saved to {out2_path}")

if __name__ == "__main__":
    split_manifest()
