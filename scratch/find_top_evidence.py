import csv
import json
import os
import re
import sqlite3
from datetime import datetime

script_dir = os.path.dirname(os.path.abspath(__file__))
db_path = os.path.join(script_dir, '..', 'aivoicetagger_state.db')
export_dir = os.path.join(script_dir, '..', 'export')
os.makedirs(export_dir, exist_ok=True)

print(f"Connecting to database: {os.path.abspath(db_path)}")
conn = sqlite3.connect(db_path)
conn.row_factory = sqlite3.Row
cursor = conn.cursor()

# Categories & Swiss Statutory Mappings
CATEGORIES = {
    "LETHAL": {
        "title": "🔴 LETHAL (Menaces de mort)",
        "law": "Art. 180 / 111 CP (StGB)",
        "keywords": ["arme", "assassiner", "cadavre", "couteau", "crever", "crève", "égorger", "fusil", "meurtre", "mort", "pistolet", "sang", "suicide", "suicider", "tu vas mourir", "tuer"]
    },
    "PHYSICAL": {
        "title": "🟠 PHYSICAL THREATS (Voies de fait & Contrainte)",
        "law": "Art. 180 / 181 CP (StGB)",
        "keywords": ["attaque", "attraper", "bousiller", "brûler", "casser", "casser la gueule", "défoncer", "détruire", "faire payer", "frapper", "je vais te defoncer", "je vais te faire", "menace", "menacer", "pas fini avec toi", "retrouver", "tu va voir", "tu vas voir ta gueule", "éclater"]
    },
    "ABUSE": {
        "title": "🟡 VERBAL ABUSE (Atteinte à la personnalité & Injure)",
        "law": "Art. 28 CC / Art. 177 CP",
        "keywords": ["abruti", "blanc bec", "bouffon", "bâtard", "casse-toi", "con", "connard", "dégage", "enculé", "gros nase", "gros porc", "imbécile", "insulte", "merde", "ordure", "porc", "putain", "pute", "sale", "sale blanc bec", "salop", "salope", "t'es moche", "t'es nul", "t'es un gros nul", "t'es vilain", "ta gueule", "un gros nase", "va chier", "va te faire foutre", "vermine"]
    },
    "COERCION": {
        "title": "🟣 DOMESTIC COERCION (Violation de domicile & Expropriation)",
        "law": "Art. 28b CC / Art. 186 CP",
        "keywords": ["argent", "cagibi", "chambre", "chantage", "harcèlement", "mon frère", "sous mon toit", "mon droit à moi", "volige"]
    }
}

records = cursor.execute("SELECT * FROM records").fetchall()
speeches_by_record = {}
for sp in cursor.execute("SELECT record_id, script FROM speeches").fetchall():
    rid = sp["record_id"]
    if rid not in speeches_by_record:
        speeches_by_record[rid] = []
    speeches_by_record[rid].append(sp["script"])

ranked = []
for r in records:
    r_dict = dict(r)
    rid = r_dict["record_id"]
    name = r_dict.get("name", "")
    directory = r_dict.get("directory", "")
    story = r_dict.get("story", "")
    sp_list = speeches_by_record.get(rid, [])
    speech_text = " ".join(sp_list)
    full_text = f"{name} {story} {speech_text}".lower()

    matched_cats = {}
    total_matched_words = 0
    for cat_name, cat_data in CATEGORIES.items():
        found = [kw for kw in cat_data["keywords"] if kw in full_text]
        if found:
            matched_cats[cat_name] = found
            total_matched_words += len(found)

    cat_count = len(matched_cats)
    if cat_count >= 2: # At least 2 red flag categories
        score = (cat_count * 100) + total_matched_words + (len(sp_list) * 2)
        ranked.append({
            "record_id": rid,
            "name": name,
            "directory": directory,
            "full_path": os.path.join(directory, name),
            "duration": r_dict.get("duration_seconds", 0),
            "state": r_dict.get("state", ""),
            "categories": matched_cats,
            "cat_count": cat_count,
            "term_hits": total_matched_words,
            "score": score,
            "story": story,
            "speech_count": len(sp_list),
            "sample_text": speech_text[:300] if speech_text else story[:300]
        })

ranked.sort(key=lambda x: (x["cat_count"], x["score"]), reverse=True)

print(f"Total Candidate Records with multiple red flag categories: {len(ranked)}\n")

# ==========================================
# 1. Export CSV Report
# ==========================================
csv_path = os.path.join(export_dir, "All_Red_Flags_Records.csv")
with open(csv_path, "w", encoding="utf-8", newline="") as f:
    writer = csv.writer(f)
    writer.writerow([
        "Rank", "RecordID", "FileName", "Directory", "RedFlagCategoryCount", 
        "Score", "State", "DurationSeconds", "MatchedCategories", "MatchedKeywords", "Path"
    ])
    for rank_idx, item in enumerate(ranked, 1):
        cats_str = "; ".join(item["categories"].keys())
        kws_str = "; ".join([f"{k}:{','.join(v)}" for k, v in item["categories"].items()])
        writer.writerow([
            rank_idx, item["record_id"], item["name"], item["directory"], item["cat_count"],
            item["score"], item["state"], f"{item['duration']:.1f}", cats_str, kws_str, item["full_path"]
        ])

print(f"✅ Generated CSV Report: {os.path.abspath(csv_path)}")

# ==========================================
# 2. Export Markdown Report
# ==========================================
md_path = os.path.join(export_dir, "All_Red_Flags_Report.md")
timestamp_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

with open(md_path, "w", encoding="utf-8") as f:
    f.write(f"# 🚨 AiVoiceTagger — All Red Flags Evidence & Multi-Category Inventory Report\n")
    f.write(f"**Généré le / Erstellt am:** `{timestamp_str}`  \n")
    f.write(f"**Juridiction:** Confédération Suisse (Tribunal suisse) | Bases légales: CC RS 210, CP RS 311.0, CO RS 220  \n")
    f.write(f"**Nombre Total de Dossiers Multi-Drapeaux Rouges:** **{len(ranked)} dossiers**  \n\n")
    f.write("---\n\n")

    f.write("## 📊 Répartition par Nombre de Catégories Critiques Détectées\n\n")
    all_4_count = sum(1 for x in ranked if x["cat_count"] == 4)
    all_3_count = sum(1 for x in ranked if x["cat_count"] == 3)
    all_2_count = sum(1 for x in ranked if x["cat_count"] == 2)
    f.write(f"- 🚨 **4 / 4 Catégories Activées (Score Maximal):** `{all_4_count}` dossiers\n")
    f.write(f"- 🟠 **3 / 4 Catégories Activées (Haute Priorité):** `{all_3_count}` dossiers\n")
    f.write(f"- 🟡 **2 / 4 Catégories Activées (Priorité Moyenne):** `{all_2_count}` dossiers\n\n")

    f.write("---\n\n")
    f.write("## 🚨 Inventaire Complet des Dossiers Multi-Drapeaux Rouges (Triés par Gravité)\n\n")
    f.write("| Rang | Nom du Fichier | Catégories (Score) | Mots-Clés Détectés | Durée | Statut | Extrait Transcription |\n")
    f.write("| :---: | :--- | :---: | :--- | :---: | :---: | :--- |\n")

    for rank_idx, item in enumerate(ranked, 1):
        cats = ", ".join(item["categories"].keys())
        all_kws = [f"{k}:{','.join(v)}" for k, v in item["categories"].items()]
        kws_formatted = "<br>".join(all_kws)
        sample = item["sample_text"].replace("\n", " ").strip()
        if len(sample) > 90:
            sample = sample[:87] + "..."
        f.write(f"| **#{rank_idx}** | `{item['name']}` | **{item['cat_count']}/4** ({item['score']}) | {kws_formatted} | `{item['duration']:.1f}s` | `{item['state']}` | {sample} |\n")

print(f"✅ Generated Markdown Report: {os.path.abspath(md_path)}")

# ==========================================
# 3. Export Top 3 Target CSV for Heavy STT
# ==========================================
top3_csv_path = os.path.join(export_dir, "Top3_Priority_Records.csv")
with open(top3_csv_path, "w", encoding="utf-8", newline="") as f:
    writer = csv.writer(f)
    writer.writerow(["RecordID", "Name", "Directory", "FlagCount", "Score", "MatchedCategories"])
    for item in ranked[:3]:
        cats = "; ".join(item["categories"].keys())
        writer.writerow([item["record_id"], item["name"], item["directory"], item["cat_count"], item["score"], cats])

print(f"✅ Generated Top 3 Target CSV for Heavy STT: {os.path.abspath(top3_csv_path)}")

conn.close()
print("\n🎉 All CSV & Markdown reports successfully generated in export/!")
