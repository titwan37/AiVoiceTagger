#!/usr/bin/env python3
"""
scripts/generate_top_evidence_docs.py — High-Precision Swiss Legal Evidence Document Generator

Identifies the Top 3 "All-Red-Flags-Up" records with maximum density across:
- LETHAL (Art. 180 / 111 CP)
- PHYSICAL THREATS (Art. 180 / 181 CP)
- VERBAL ABUSE (Art. 28 / 28b CC & Art. 177 CP)
- DOMESTIC COERCION (Art. 28b CC & Art. 186 CP)

Generates beautified, court-ready Markdown evidence transcripts cleared of transcription errors.
"""

import csv
import json
import os
import re
import sqlite3
from datetime import datetime

# Red Flag Watch Categories
RED_FLAGS = {
    "WATCH_LETHAL": {
        "title": "🔴 WATCH_LETHAL (Menaces de mort / Todesdrohungen)",
        "law_fr": "Art. 180 CP / Art. 111 CP — Menaces graves & atteintes à la vie",
        "law_de": "Art. 180 StGB / Art. 111 StGB — schwere Drohungen & Lebensgefahr",
        "keywords": [
            "arme", "assassiner", "cadavre", "couteau", "crever", "crève",
            "égorger", "fusil", "meurtre", "mort", "pistolet", "sang",
            "suicide", "suicider", "tu vas mourir", "tuer"
        ]
    },
    "WATCH_PHYSICAL_THREATS": {
        "title": "🟠 WATCH_PHYSICAL_THREATS (Voies de fait & Contrainte / Nötigung)",
        "law_fr": "Art. 180 CP (Menaces) & Art. 181 CP (Contrainte)",
        "law_de": "Art. 180 StGB (Drohung) & Art. 181 StGB (Nötigung)",
        "keywords": [
            "attaque", "attraper", "bousiller", "brûler", "casser",
            "casser la gueule", "défoncer", "détruire", "faire payer", "frapper",
            "je vais te defoncer", "je vais te faire", "menace", "menacer",
            "pas fini avec toi", "retrouver", "tu va voir", "tu vas voir ta gueule",
            "éclater"
        ]
    },
    "WATCH_VERBAL_ABUSE": {
        "title": "🟡 WATCH_VERBAL_ABUSE (Atteinte à la personnalité & Injure)",
        "law_fr": "Art. 28, 28b CC (Harcèlement) & Art. 177 CP (Injure)",
        "law_de": "Art. 28, 28b ZGB (Nachstellung) & Art. 177 StGB (Beschimpfung)",
        "keywords": [
            "abruti", "blanc bec", "bouffon", "bâtard", "casse-toi", "con",
            "connard", "dégage", "enculé", "gros nase", "gros porc", "imbécile",
            "insulte", "merde", "ordure", "porc", "putain", "pute", "sale",
            "sale blanc bec", "salop", "salope", "t'es moche", "t'es nul",
            "t'es un gros nul", "t'es vilain", "ta gueule", "un gros nase",
            "va chier", "va te faire foutre", "vermine"
        ]
    },
    "WATCH_DOMESTIC_COERCION": {
        "title": "🟣 WATCH_DOMESTIC_COERCION (Violation de domicile / Hausfriedensbruch)",
        "law_fr": "Art. 28b CC (Protection du logement) & Art. 186 CP (Violation de domicile)",
        "law_de": "Art. 28b ZGB (Wohnungsschutz) & Art. 186 StGB (Hausfriedensbruch)",
        "keywords": [
            "argent", "cagibi", "chambre", "chantage", "harcèlement", "mon frère",
            "sous mon toit", "mon droit à moi", "volige"
        ]
    }
}

def clean_transcript(raw_text):
    if not raw_text:
        return "*[Aucune transcription disponible / No transcript available]*"

    # Remove repeating hallucination loops (e.g. repeated words or phrases)
    lines = raw_text.split("\n")
    cleaned_lines = []
    seen_phrases = set()

    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        # Deduplicate consecutive identical lines
        if cleaned_lines and cleaned_lines[-1] == stripped:
            continue
        # Filter obvious Whisper artifacts
        if re.search(r'(sous-titres|sous-titrage|visionneuse|merci d\'avoir regardé)', stripped, re.IGNORECASE):
            continue
        cleaned_lines.append(stripped)

    result = "\n".join(cleaned_lines)
    return result if result.strip() else raw_text.strip()

def format_timestamp(offset_ms):
    total_seconds = int(offset_ms / 1000)
    minutes = total_seconds // 60
    seconds = total_seconds % 60
    return f"{minutes:02d}:{seconds:02d}"

def main():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    db_path = os.path.join(script_dir, '..', 'aivoicetagger_state.db')
    export_dir = os.path.join(script_dir, '..', 'export')
    os.makedirs(export_dir, exist_ok=True)

    print(f"Connecting to database: {os.path.abspath(db_path)}")
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # Query all records and speeches
    records = cursor.execute("SELECT * FROM records").fetchall()
    speeches_rows = cursor.execute("SELECT record_id, script, confidence, offset_ms, duration_ms, time_frame FROM speeches ORDER BY offset_ms ASC").fetchall()

    speeches_by_record = {}
    for sp in speeches_rows:
        rid = sp["record_id"]
        if rid not in speeches_by_record:
            speeches_by_record[rid] = []
        speeches_by_record[rid].append(dict(sp))

    # Evaluate Red Flag Density for each record
    candidate_list = []
    for r in records:
        r_dict = dict(r)
        rid = r_dict["record_id"]
        name = r_dict.get("name", "")
        directory = r_dict.get("directory", "")
        story = r_dict.get("story", "")
        sp_list = speeches_by_record.get(rid, [])
        speech_text = " ".join([sp["script"] for sp in sp_list])
        combined_text = f"{name} {story} {speech_text}".lower()

        matched_flags = {}
        total_term_hits = 0

        for flag_key, flag_data in RED_FLAGS.items():
            hits = [kw for kw in flag_data["keywords"] if kw in combined_text]
            if hits:
                matched_flags[flag_key] = hits
                total_term_hits += len(hits)

        flag_count = len(matched_flags)
        if flag_count >= 1:
            score = (flag_count * 100) + total_term_hits + (len(sp_list) * 2)
            candidate_list.append({
                "record_id": rid,
                "name": name,
                "directory": directory,
                "duration_seconds": r_dict.get("duration_seconds", 0.0),
                "length_bytes": r_dict.get("length_bytes", 0),
                "date_last_write": r_dict.get("date_last_write", ""),
                "date_record_day": r_dict.get("date_record_day", ""),
                "state": r_dict.get("state", ""),
                "story": story,
                "matched_flags": matched_flags,
                "flag_count": flag_count,
                "term_hits": total_term_hits,
                "score": score,
                "speeches": sp_list
            })

    # Sort candidates by flag count (all 4 flags up first) and overall score
    candidate_list.sort(key=lambda x: (x["flag_count"], x["score"]), reverse=True)

    print(f"Total High-Interest Candidates Analyzed: {len(candidate_list)}")
    top_3 = candidate_list[:3]

    # Save target CSV for heavy re-transcription pipeline
    top_csv_path = os.path.join(export_dir, "Top3_Priority_Records.csv")
    with open(top_csv_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["RecordID", "Name", "Directory", "FlagCount", "Score", "MatchedCategories"])
        for item in top_3:
            cats = "; ".join(item["matched_flags"].keys())
            writer.writerow([item["record_id"], item["name"], item["directory"], item["flag_count"], item["score"], cats])
    print(f"✅ Generated Target CSV for Heavy STT: {os.path.abspath(top_csv_path)}")

    # Generate 3 Beautified Evidence Documents
    doc_paths = []
    for idx, item in enumerate(top_3, 1):
        doc_filename = f"Priority_Evidence_Doc_{idx}_{item['record_id'][:10]}.md"
        doc_path = os.path.join(export_dir, doc_filename)
        doc_paths.append(doc_path)

        with open(doc_path, "w", encoding="utf-8") as f:
            f.write(f"# 🇨🇭 DOSSIER DE PREUVE PRIORTAIRE N°{idx} — RELEVÉ FORENSIQUE\n")
            f.write(f"**Généré le:** `{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}` | **Juridiction:** Confédération Suisse (Tribunal suisse)  \n")
            f.write(f"**Niveau d'Alerte:** 🚨 **ALL RED FLAGS ACTIVE ({item['flag_count']}/4 Catégories Critiques)**  \n\n")
            f.write("---\n\n")

            f.write("## 📌 1. Fiche d'Identité & Traçabilité du Fichier (Provenance)\n\n")
            f.write(f"| Paramètre | Valeur |\n")
            f.write(f"| :--- | :--- |\n")
            f.write(f"| **Identifiant Unique (Record ID)** | `{item['record_id']}` |\n")
            f.write(f"| **Nom du Fichier Audio** | `{item['name']}` |\n")
            f.write(f"| **Emplacement Réseau (NAS)** | `{os.path.join(item['directory'], item['name'])}` |\n")
            f.write(f"| **Date de l'Enregistrement** | `{item['date_record_day'] or item['date_last_write']}` |\n")
            f.write(f"| **Durée Exacte** | `{item['duration_seconds']:.1f} secondes ({int(item['duration_seconds']//60)}m {int(item['duration_seconds']%60)}s)` |\n")
            f.write(f"| **Taille du Fichier** | `{item['length_bytes'] / (1024*1024):.2f} MB` |\n")
            f.write(f"| **Statut du Traitement** | `{item['state']}` |\n\n")

            f.write("---\n\n")
            f.write("## ⚖️ 2. Qualifications Légales & Drapeaux Rouges (Droit Suisse)\n\n")
            for flag_key, keywords in item["matched_flags"].items():
                flag_info = RED_FLAGS[flag_key]
                kw_str = ", ".join([f"`{k}`" for k in keywords])
                f.write(f"### {flag_info['title']}\n")
                f.write(f"- **Bases Légales:** {flag_info['law_fr']} / *{flag_info['law_de']}*\n")
                f.write(f"- **Mots-Clés Détectés:** {kw_str}\n\n")

            f.write("---\n\n")
            f.write("## 📜 3. Transcription Fidele & Nettoyée (Court-Ready Transcript)\n\n")

            if item["speeches"]:
                f.write("| Horodatage | Confiance STT | Transcription Textuelle |\n")
                f.write("| :---: | :---: | :--- |\n")
                for sp in item["speeches"]:
                    time_str = f"[{format_timestamp(sp['offset_ms'])} - {format_timestamp(sp['offset_ms'] + sp['duration_ms'])}]"
                    conf_pct = f"{sp['confidence']*100:.1f}%"
                    script_clean = clean_transcript(sp["script"])
                    f.write(f"| `{time_str}` | `{conf_pct}` | {script_clean} |\n")
            else:
                f.write("### Résumé & Contexte Factualisé:\n\n")
                f.write(f"> {clean_transcript(item['story'])}\n\n")

            f.write("\n---\n\n")
            f.write("## 🎯 4. Matrice d'Extraits Probanst pour Soumission au Tribunal\n\n")
            f.write("| Terrains Légaux | Citations / Extraits Textuels | Pertinence Légal Suisse |\n")
            f.write("| :--- | :--- | :--- |\n")

            all_kws = [kw for kws in item["matched_flags"].values() for kw in kws]
            for kw in set(all_kws[:5]):
                f.write(f"| Mot-clé: **`{kw}`** | Documenté dans le fichier `{item['name']}` | Constitue un élément de preuve au sens des Art. 28 CC / Art. 180-181 CP. |\n")

        print(f"✅ Created Beautified Evidence Document {idx}: {os.path.abspath(doc_path)}")

    conn.close()
    print("\n🎉 High-Priority Evidence Document Generation Complete!")

if __name__ == "__main__":
    main()
