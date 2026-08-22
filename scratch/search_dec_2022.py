import csv

with open(r"c:\Dev\AiVoiceTagger\inventory_manifest.csv", 'r', encoding='utf-8', errors='ignore') as f:
    reader = csv.DictReader(f)
    print("Searching for December 2022 (2022-12 or 2022_12 or 27/12/2022)...")
    matches = []
    for row in reader:
        text = f"{row.get('name', '')} {row.get('directory', '')} {row.get('date_record_day', '')}"
        if "2022" in text and ("12" in text or "Dec" in text):
            matches.append(row)
            
print(f"Found {len(matches)} potential Dec 2022 matches.")
for m in matches[:20]:
    print(m.get('name'), "||", m.get('date_record_day'), "||", m.get('directory'))
