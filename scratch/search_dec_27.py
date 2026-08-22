import csv

with open(r"c:\Dev\AiVoiceTagger\inventory_manifest.csv", 'r', encoding='utf-8', errors='ignore') as f:
    reader = csv.DictReader(f)
    print("Searching for Dec 27 2022 or late Dec 2022...")
    for row in reader:
        text = f"{row.get('name', '')} {row.get('directory', '')} {row.get('date_record_day', '')}"
        if "2022" in text and ("27" in text or "26" in text or "28" in text) and ("12" in text or "Dec" in text):
            print(row.get('name'), "||", row.get('date_record_day'), "||", row.get('directory'))
