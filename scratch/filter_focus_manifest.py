import csv
import re
from pathlib import Path

def filter_manifest():
    manifest_path = Path(r"c:\Dev\AiVoiceTagger\inventory_manifest.csv")
    focus_path = Path(r"c:\Dev\AiVoiceTagger\focus_list.txt")
    out_csv = Path(r"c:\Dev\AiVoiceTagger\export\Focused_Priority_Records.csv")
    
    with open(focus_path, 'r', encoding='utf-8') as f:
        focus_patterns = [line.strip() for line in f if line.strip() and not line.startswith('#')]
        
    print(f"Loaded {len(focus_patterns)} focus patterns: {focus_patterns}")
    
    # Compile regex variations for each pattern
    # e.g. 2020_08_01_13 -> 2020[-_]08[-_]01[-_hH ]?13
    compiled_patterns = []
    for pat in focus_patterns:
        # replace _ with [-_hH ]? or similar separator
        parts = pat.split('_')
        regex_str = r"[-_hH :]?".join(parts)
        compiled_patterns.append((pat, re.compile(regex_str, re.IGNORECASE)))
        
    matched_records = []
    
    with open(manifest_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        header = reader.fieldnames
        for row in reader:
            # check name, directory, date_record_day
            search_text = f"{row.get('name', '')} {row.get('directory', '')} {row.get('date_record_day', '')}"
            matched_pat = None
            for orig_pat, rgx in compiled_patterns:
                if rgx.search(search_text):
                    matched_pat = orig_pat
                    break
            if matched_pat:
                matched_records.append((matched_pat, row))
                
    print(f"\nTotal matched records: {len(matched_records)}")
    for pat in focus_patterns:
        count = sum(1 for p, _ in matched_records if p == pat)
        print(f" - [{pat}]: {count} records found")
        
    # Write focused CSV
    with open(out_csv, 'w', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=header)
        writer.writeheader()
        for _, row in matched_records:
            writer.writerow(row)
            
    print(f"\nSaved focused manifest to: {out_csv}")
    
    # Print sample matches
    print("\nSample matches:")
    for pat, row in matched_records[:15]:
        print(f"[{pat}] -> {row['name']} ({row.get('directory', '')})")

if __name__ == "__main__":
    filter_manifest()
