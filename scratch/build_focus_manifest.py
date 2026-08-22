import csv
import re
import os
from pathlib import Path

def generate_focus_manifest():
    manifest_path = Path(r"c:\Dev\AiVoiceTagger\inventory_manifest.csv")
    focus_path = Path(r"c:\Dev\AiVoiceTagger\focus_list.txt")
    export_dir = Path(r"c:\Dev\AiVoiceTagger\export")
    export_dir.mkdir(parents=True, exist_ok=True)
    
    out_all_csv = export_dir / "Focused_Priority_Records.csv"
    out_pc1_csv = export_dir / "Focused_batch_pc1.csv"
    out_pc2_csv = export_dir / "Focused_batch_pc2.csv"
    
    with open(focus_path, 'r', encoding='utf-8') as f:
        raw_patterns = [line.strip() for line in f if line.strip() and not line.startswith('#')]
        
    print(f"Loaded {len(raw_patterns)} target focus patterns from {focus_path.name}:")
    for p in raw_patterns:
        print(f"  • {p}")

    # Build regexes. If pattern is like 2022_12_27_13, also allow matching 2022_12_27
    compiled = []
    for pat in raw_patterns:
        # standard exact pattern
        parts = pat.split('_')
        rgx_exact = re.compile(r"[-_hH :]?".join(parts), re.IGNORECASE)
        # date-only prefix if pattern had hours
        rgx_prefix = None
        if len(parts) >= 3:
            date_prefix = parts[:3] # year, month, day
            rgx_prefix = re.compile(r"[-_hH :]?".join(date_prefix), re.IGNORECASE)
        compiled.append((pat, rgx_exact, rgx_prefix))

    seen_ids = set()
    matched_records = []
    
    with open(manifest_path, 'r', encoding='utf-8', errors='ignore') as f:
        reader = csv.DictReader(f)
        header = reader.fieldnames
        for row in reader:
            rec_id = row.get('record_id')
            if not rec_id or rec_id in seen_ids:
                continue
                
            text = f"{row.get('name', '')} {row.get('directory', '')} {row.get('date_record_day', '')}"
            
            matched_tag = None
            for pat, rgx_exact, rgx_prefix in compiled:
                if rgx_exact.search(text):
                    matched_tag = pat
                    break
                elif rgx_prefix and rgx_prefix.search(text):
                    matched_tag = f"{pat} (day-match)"
                    break
                    
            if matched_tag:
                seen_ids.add(rec_id)
                matched_records.append((matched_tag, row))
                
    print("\n" + "="*50)
    print(" FOCUSED MANIFEST MATCH SUMMARY")
    print("="*50)
    print(f"Total Unique Targeted Records Found: {len(matched_records)}")
    
    # Summary by pattern
    for pat in raw_patterns:
        cnt = sum(1 for tag, _ in matched_records if tag.startswith(pat))
        print(f"  * {pat:20s} -> {cnt:2d} records")
        
    # Write master focused CSV
    with open(out_all_csv, 'w', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=header)
        writer.writeheader()
        for _, row in matched_records:
            writer.writerow(row)
            
    # Write PC1 & PC2 splits
    pc1_rows = [r for idx, (_, r) in enumerate(matched_records) if idx % 2 == 0]
    pc2_rows = [r for idx, (_, r) in enumerate(matched_records) if idx % 2 == 1]
    
    with open(out_pc1_csv, 'w', encoding='utf-8', newline='') as f1:
        w1 = csv.DictWriter(f1, fieldnames=header)
        w1.writeheader()
        w1.writerows(pc1_rows)
        
    with open(out_pc2_csv, 'w', encoding='utf-8', newline='') as f2:
        w2 = csv.DictWriter(f2, fieldnames=header)
        w2.writeheader()
        w2.writerows(pc2_rows)

    print(f"\nGenerated Export Files:")
    print(f"  1. Master Focused Manifest: {out_all_csv} ({len(matched_records)} records)")
    print(f"  2. PC 1 Batch:              {out_pc1_csv} ({len(pc1_rows)} records)")
    print(f"  3. PC 2 Batch:              {out_pc2_csv} ({len(pc2_rows)} records)")
    print("="*50)

if __name__ == "__main__":
    generate_focus_manifest()
