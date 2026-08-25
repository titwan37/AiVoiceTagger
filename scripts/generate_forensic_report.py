#!/usr/bin/env python3
"""
scripts/generate_forensic_report.py — AiVoiceTagger Swiss Legal Evidence & Forensic Analytics Generator

Generates executive legal reports (Markdown, JSON, interactive HTML Dashboard)
in both French (_fr) and German (_de) under the Swiss Legal Framework (CC RS 210 / ZGB SR 210, CO RS 220 / OR SR 220, CP RS 311.0 / StGB SR 311.0).
Includes interactive Chart.js stacked bar chart histograms of the Eskalationsverlauf.
"""

import json
import os
import re
import sqlite3
import sys
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

from datetime import datetime

# Define Watch Categories & Swiss Legal Qualification Mappings (Bilingual)
WATCH_CATEGORIES_FR = {
    "WATCH_LETHAL": {
        "title": "🔴 WATCH_LETHAL",
        "qualification": "Code Pénal suisse (Art. 180 CP / Art. 111 CP) — Menaces de mort & violences graves",
        "keywords": [
            "arme", "assassiner", "cadavre", "couteau", "crever", "crève",
            "égorger", "fusil", "meurtre", "mort", "pistolet", "sang",
            "suicide", "suicider", "tu vas mourir", "tuer"
        ]
    },
    "WATCH_PHYSICAL_THREATS": {
        "title": "🟠 WATCH_PHYSICAL_THREATS",
        "qualification": "Code Pénal suisse (Art. 180 CP Menaces / Art. 181 CP Contrainte) — Menaces de voies de fait & coercition",
        "keywords": [
            "attaque", "attraper", "bousiller", "brûler", "casser",
            "casser la gueule", "défoncer", "détruire", "faire payer", "frapper",
            "je vais te defoncer", "je vais te faire", "menace", "menacer",
            "pas fini avec toi", "retrouver", "tu va voir", "tu vas voir ta gueule",
            "éclater"
        ]
    },
    "WATCH_VERBAL_ABUSE": {
        "title": "🟡 WATCH_VERBAL_ABUSE",
        "qualification": "Code Civil suisse (Art. 28, 28b CC Atteinte à la personnalité & Harcèlement) & Art. 177 CP Injure",
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
        "title": "🟣 WATCH_DOMESTIC_COERCION",
        "qualification": "Code Civil suisse (Art. 28b CC Protection contre le harcèlement) & Art. 186 CP Violation de domicile",
        "keywords": [
            "argent", "cagibi", "chambre", "chantage", "harcèlement", "mon frère"
        ]
    },
    "WATCH_LEGAL_PROCEDURAL": {
        "title": "🔵 WATCH_LEGAL_PROCEDURAL",
        "qualification": "Procédure judiciaire suisse — Police, tribunaux, avocats & plaintes",
        "keywords": [
            "avocat", "commissariat", "gendarmerie", "huissier", "juge",
            "juridique", "justice", "loi", "plainte", "police", "prison",
            "procès", "tribunal"
        ]
    },
    "WATCH_EVIDENCE_INTEGRITY": {
        "title": "🟢 WATCH_EVIDENCE_INTEGRITY",
        "qualification": "Droit suisse (Art. 41/49 CO & Art. 28 CC) — Intégrité des preuves & enregistrements",
        "keywords": [
            "illégal", "preuve"
        ]
    }
}

WATCH_CATEGORIES_DE = {
    "WATCH_LETHAL": {
        "title": "🔴 WATCH_LETHAL",
        "qualification": "Schweizerisches Strafgesetzbuch (StGB Art. 180 / Art. 111) — Todesdrohungen & schwere Gewalt",
        "keywords": WATCH_CATEGORIES_FR["WATCH_LETHAL"]["keywords"]
    },
    "WATCH_PHYSICAL_THREATS": {
        "title": "🟠 WATCH_PHYSICAL_THREATS",
        "qualification": "Strafgesetzbuch (StGB Art. 180 Drohung / Art. 181 Nötigung) — Drohungen mit physischer Gewalt",
        "keywords": WATCH_CATEGORIES_FR["WATCH_PHYSICAL_THREATS"]["keywords"]
    },
    "WATCH_VERBAL_ABUSE": {
        "title": "🟡 WATCH_VERBAL_ABUSE",
        "qualification": "Zivilgesetzbuch (ZGB Art. 28/28b Persönlichkeitsschutz) & StGB Art. 177 Beschimpfung",
        "keywords": WATCH_CATEGORIES_FR["WATCH_VERBAL_ABUSE"]["keywords"]
    },
    "WATCH_DOMESTIC_COERCION": {
        "title": "🟣 WATCH_DOMESTIC_COERCION",
        "qualification": "Zivilgesetzbuch (ZGB Art. 28b Schutz vor Nachstellung) & StGB Art. 186 Hausfriedensbruch",
        "keywords": WATCH_CATEGORIES_FR["WATCH_DOMESTIC_COERCION"]["keywords"]
    },
    "WATCH_LEGAL_PROCEDURAL": {
        "title": "🔵 WATCH_LEGAL_PROCEDURAL",
        "qualification": "Schweizerisches Gerichtsverfahren — Polizei, Gerichte & Anwälte",
        "keywords": WATCH_CATEGORIES_FR["WATCH_LEGAL_PROCEDURAL"]["keywords"]
    },
    "WATCH_EVIDENCE_INTEGRITY": {
        "title": "🟢 WATCH_EVIDENCE_INTEGRITY",
        "qualification": "Schweizer Recht (OR Art. 41/49 & ZGB Art. 28) — Beweissicherung & Rechtswidrigkeit",
        "keywords": WATCH_CATEGORIES_FR["WATCH_EVIDENCE_INTEGRITY"]["keywords"]
    }
}

# Regex patterns for specific Legal Density Analysis
EXPULSION_PATTERN = re.compile(r"(?i)\b(dégage|degage|casse-toi|tu dégages|va-t'en|de mon toit|hors de ma vue)\b")
INSULT_PATTERN = re.compile(r"(?i)\b(ta gueule|gros nase|vermine|gros porc|t'es nul|connard|salope|bâtard|abruti|ordure)\b")
THREAT_PATTERN = re.compile(r"(?i)\b(casser la gueule|claque|mettre à terre|te défoncer|te faire|frapper|je dicte ma loi|faire venir mon frère)\b")
COERCION_PATTERN = re.compile(r"(?i)\b(argent|cagibi|chambre|chantage|harcèlement|volige|sous mon toit|mon droit à moi)\b")

def extract_year(name, directory, date_record_day):
    for text in [str(name), str(directory), str(date_record_day)]:
        match = re.search(r'(20\d{2})', text)
        if match:
            return match.group(1)
    return "Unknown"

def generate_markdown_report(export_dir, lang, data):
    is_fr = lang == "fr"
    filename = f"Forensic_Legal_Evidence_Report_{lang}.md"
    md_path = os.path.join(export_dir, filename)

    watch_cats = WATCH_CATEGORIES_FR if is_fr else WATCH_CATEGORIES_DE

    title = "⚖️ AiVoiceTagger — Rapport de Preuve Judiciaire & Analyse Forensique (Droit Suisse)" if is_fr else "⚖️ AiVoiceTagger — Gerichtlicher Beweisbericht & Forensische Analyse (Schweizer Recht)"
    jurisdiction = "Confédération Suisse (*Swiss Jurisdiction*)" if is_fr else "Schweizerische Eidgenossenschaft (*Swiss Jurisdiction*)"
    legal_basis = "Code Civil suisse (CC RS 210, Art. 28 & 28b), Code des Obligations (CO RS 220, Art. 41 & 49), Code Pénal suisse (CP RS 311.0, Art. 177, 180, 181, 186)" if is_fr else "Schweizerisches Zivilgesetzbuch (ZGB SR 210, Art. 28 & 28b), Obligationenrecht (OR SR 220, Art. 41 & 49), Strafgesetzbuch (StGB SR 311.0, Art. 177, 180, 181, 186)"

    with open(md_path, "w", encoding="utf-8") as f:
        f.write(f"# {title}\n")
        f.write(f"**Généré le / Erstellt am:** `{data['timestamp_str']}`  \n")
        f.write(f"**Juridiction / Gerichtsbarkeit:** {jurisdiction}  \n")
        f.write(f"**Bases Légales / Rechtsgrundlagen:** {legal_basis}  \n")
        f.write(f"**Total Fichiers / Total Dateien:** **{data['total_records']:,}** | **Indices Élevés / Beweisrelevante Treffer:** **{len(data['triaged_high_interest']):,}**\n\n")
        f.write("---\n\n")

        if is_fr:
            f.write("## 📊 Vue d'Ensemble Forensique\n\n")
            f.write("| Métrique | Quantité | Description / Portée Juridique |\n")
            f.write("| :--- | :---: | :--- |\n")
            f.write(f"| **Enregistrements Catalogués** | `{data['total_records']:,}` | Catalogue audio complet (2015–2026) |\n")
            f.write(f"| **Segments Vocaux Transcrits** | `{data['total_speeches']:,}` | Transcriptions textuelles horodatées |\n")
            f.write(f"| **Dossiers à Fort Intérêt Probatoire** | `{data['state_counts'].get('TriagedHighInterest', 0):,}` | Preuves prioritaires soumises à analyse |\n")
            f.write(f"| **Dossiers Traités (`Done`)** | `{data['state_counts'].get('Done', 0):,}` | Transcriptions finales validées |\n")
            f.write(f"| **Fichiers Inaccessibles (`Dead Letter`)** | `{data['dead_letter_count']:,}` | Fichiers corrompus ou hors ligne |\n\n")
        else:
            f.write("## 📊 Forensische Gesamtübersicht\n\n")
            f.write("| Metrik | Anzahl | Beschreibung / Rechtliche Bedeutung |\n")
            f.write("| :--- | :---: | :--- |\n")
            f.write(f"| **Katalogisierte Dateien** | `{data['total_records']:,}` | Gesamtes Audioarchiv (2015–2026) |\n")
            f.write(f"| **Transkribierte Sprachsegmente** | `{data['total_speeches']:,}` | Zeitgestempelte Texttranskripte |\n")
            f.write(f"| **Hohe Beweisrelevanz** | `{data['state_counts'].get('TriagedHighInterest', 0):,}` | Prioritäre Beweise zur Analyse |\n")
            f.write(f"| **Abgeschlossen (`Done`)** | `{data['state_counts'].get('Done', 0):,}` | Validierte Endtranskripte |\n")
            f.write(f"| **Nicht lesbar (`Dead Letter`)** | `{data['dead_letter_count']:,}` | Beschädigte oder fehlende Dateien |\n\n")

        f.write("---\n\n")
        f.write(f"## 🏷️ {'Répartition par Catégories de Surveillance' if is_fr else 'Kategorien der rechtlichen Überwachung'}\n\n")
        f.write(f"| {'Catégorie' if is_fr else 'Kategorie'} | {'Qualification Légale' if is_fr else 'Rechtliche Qualifikation'} | {'Occurrences' if is_fr else 'Treffer'} |\n")
        f.write("| :--- | :--- | :---: |\n")
        for cat_key, cat_data in watch_cats.items():
            f.write(f"| **{cat_data['title']}** | {cat_data['qualification']} | `{data['category_counts'][cat_key]:,}` |\n")

        f.write("\n---\n\n")
        histo_title = "## 📈 Histogramme & Trajectoire d'Escalade (2015–2026)" if is_fr else "## 📈 Histogramm & Eskalationsverlauf (2015–2026)"
        f.write(f"{histo_title}\n\n")
        if is_fr:
            f.write("| Année | Total Fichiers | Indices Élevés | Injonctions Expulsion | Injures / Attaques | Menaces de Violences | Coercition / Emprise | Visualisation |\n")
        else:
            f.write("| Jahr | Total Dateien | Beweisrelevant | Ausweisungsdruck | Beschimpfungen | Gewaltandrohungen | Nötigung / Druck | Visualisierung |\n")
        f.write("| :---: | :---: | :---: | :---: | :---: | :---: | :---: | :--- |\n")
        for y in data['sorted_years']:
            st = data['yearly_stats'][y]
            pt = data['pattern_density_by_year'][y]
            bars = "█" * min(20, (st['high_interest'] // 2) + 1) if st['high_interest'] > 0 else "—"
            f.write(f"| **{y}** | `{st['total']:,}` | `{st['high_interest']:,}` | `{pt['expulsion']:,}` | `{pt['insult']:,}` | `{pt['threat']:,}` | `{pt['coercion']:,}` | `{bars}` |\n")

        f.write("\n---\n\n")
        f.write(f"## 🚨 {'Matrice des Preuves Principales (Top 50)' if is_fr else 'Hauptbeweismittel-Matrix (Top 50)'}\n\n")
        f.write(f"| {'Année' if is_fr else 'Jahr'} | {'Nom du Fichier' if is_fr else 'Dateiname'} | {'Catégories' if is_fr else 'Kategorien'} | {'Mots-Clés' if is_fr else 'Schlüsselwörter'} | {'Extrait Transcription' if is_fr else 'Transkriptauszug'} |\n")
        f.write("| :---: | :--- | :--- | :--- | :--- |\n")
        for item in data['triaged_high_interest'][:50]:
            cats = ", ".join([c.replace("WATCH_", "") for c in item["matched_categories"]]) or "HighInterest"
            terms = ", ".join(item["matched_keywords"][:4]) or "—"
            sample = item["sample_transcript"].replace("\n", " ").strip()
            if len(sample) > 80:
                sample = sample[:77] + "..."
            f.write(f"| {item['year']} | `{item['name']}` | `{cats}` | **{terms}** | {sample} |\n")

    # Mirror default output to Forensic_Legal_Evidence_Report.md
    if is_fr:
        default_md = os.path.join(export_dir, "Forensic_Legal_Evidence_Report.md")
        with open(default_md, "w", encoding="utf-8") as f_def:
            with open(md_path, "r", encoding="utf-8") as f_src:
                f_def.write(f_src.read())

    print(f"✅ Generated Markdown report ({lang}): {os.path.abspath(md_path)}")

def generate_html_dashboard(export_dir, lang, data):
    is_fr = lang == "fr"
    filename = f"Forensic_Dashboard_{lang}.html"
    html_path = os.path.join(export_dir, filename)

    watch_cats = WATCH_CATEGORIES_FR if is_fr else WATCH_CATEGORIES_DE

    title = "🇨🇭 AiVoiceTagger — Tableau de Bord Forensique (Droit Suisse)" if is_fr else "🇨🇭 AiVoiceTagger — Forensisches Dashboard (Schweizer Recht)"
    subtitle = f"Généré le {data['timestamp_str']} | Juridiction Suisse | CC RS 210, CO RS 220, CP RS 311.0" if is_fr else f"Erstellt am {data['timestamp_str']} | Schweizer Gerichtsbarkeit | ZGB SR 210, OR SR 220, StGB SR 311.0"

    # Define variables to avoid backslashes inside f-strings
    legal_title = "Cadre Légal Suisse Applicable" if is_fr else "Anwendbare Schweizer Rechtsgrundlagen"
    legal_basis_html = (
        '<p><strong>• Protection de la personnalité (Art. 28 & 28b CC RS 210):</strong> Atteinte illicite, harcèlement psychologique & stalking.</p>'
        '<p><strong>• Menaces (Art. 180 CP RS 311.0):</strong> Intimidation & menaces de violences physiques.</p>'
        '<p><strong>• Contrainte (Art. 181 CP RS 311.0):</strong> Coercition & entrave à la liberté d\'action.</p>'
        '<p><strong>• Violation de domicile (Art. 186 CP RS 311.0):</strong> Intrusion & injonctions forcées d\'expulsion.</p>'
        '<p><strong>• Tort Moral (Art. 41 & 49 CO RS 220):</strong> Réparation financière du préjudice moral.</p>'
        if is_fr else
        '<p><strong>• Persönlichkeitsschutz (Art. 28 & 28b ZGB SR 210):</strong> Widerrechtliche Verletzungen, psychische Nachstellung & Mobbing.</p>'
        '<p><strong>• Drohung (Art. 180 StGB SR 311.0):</strong> Versetzen in Angst und Schrecken durch Gewaltandrohung.</p>'
        '<p><strong>• Nötigung (Art. 181 StGB SR 311.0):</strong> Rechtswidrige Einschränkung der Handlungsfreiheit.</p>'
        '<p><strong>• Hausfriedensbruch (Art. 186 StGB SR 311.0):</strong> Unberechtigtes Eindringen & Ausweisungsdruck.</p>'
        '<p><strong>• Genugtuung (Art. 41 & 49 OR SR 220):</strong> Finanzieller Ausgleich für seelischen Schmerz.</p>'
    )
    escalation_title = "📊 Histogramme de la Trajectoire d'Escalade (Eskalationsverlauf)" if is_fr else "📊 Histogramm des Eskalationsverlaufs (Eskalationsverlauf)"
    cat_summary_title = "Répartition des Catégories de Surveillance" if is_fr else "Übersicht der Überwachungskategorien"
    pattern_density_title = "Tableau de Densité de Motifs (2015–2026)" if is_fr else "Musterdichte-Tabelle (2015–2026)"
    evidence_register_title = f"Registre des Preuves Principales ({len(data['triaged_high_interest']):,} Total)" if is_fr else f"Hauptbeweismittel-Register ({len(data['triaged_high_interest']):,} Total)"
    search_placeholder = "Rechercher par nom de fichier, mot-clé, ou année..." if is_fr else "Suche nach Dateiname, Schlüsselwort oder Jahr..."

    # Prepare datasets for Chart.js Histogram
    chart_years = [str(y) for y in data['sorted_years']]
    chart_lethal = [data['yearly_stats'][y]['categories']['WATCH_LETHAL'] for y in data['sorted_years']]
    chart_threats = [data['yearly_stats'][y]['categories']['WATCH_PHYSICAL_THREATS'] for y in data['sorted_years']]
    chart_abuse = [data['yearly_stats'][y]['categories']['WATCH_VERBAL_ABUSE'] for y in data['sorted_years']]
    chart_coercion = [data['yearly_stats'][y]['categories']['WATCH_DOMESTIC_COERCION'] for y in data['sorted_years']]
    chart_procedural = [data['yearly_stats'][y]['categories']['WATCH_LEGAL_PROCEDURAL'] for y in data['sorted_years']]
    chart_integrity = [data['yearly_stats'][y]['categories']['WATCH_EVIDENCE_INTEGRITY'] for y in data['sorted_years']]

    html_content = f"""<!DOCTYPE html>
<html lang="{lang}">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title}</title>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;600;700&display=swap" rel="stylesheet">
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <style>
        :root {{
            --bg: #0f172a;
            --card-bg: #1e293b;
            --accent: #38bdf8;
            --danger: #ef4444;
            --warning: #f59e0b;
            --success: #10b981;
            --purple: #a855f7;
            --text: #f8fafc;
            --text-muted: #94a3b8;
            --border: #334155;
            --swiss-red: #dc2626;
        }}
        * {{ box-sizing: border-box; margin: 0; padding: 0; font-family: 'Inter', sans-serif; }}
        body {{ background-color: var(--bg); color: var(--text); padding: 2rem; line-height: 1.6; }}
        header {{ margin-bottom: 2rem; border-bottom: 1px solid var(--border); padding-bottom: 1rem; display: flex; justify-content: space-between; align-items: center; }}
        header h1 {{ font-size: 1.8rem; font-weight: 700; color: var(--accent); }}
        header p {{ color: var(--text-muted); font-size: 0.85rem; margin-top: 0.25rem; }}

        .lang-switch {{ display: flex; gap: 0.5rem; }}
        .lang-btn {{ padding: 0.4rem 0.8rem; border-radius: 6px; font-weight: 600; text-decoration: none; font-size: 0.85rem; border: 1px solid var(--border); color: var(--text); background: var(--card-bg); }}
        .lang-btn.active {{ background: var(--accent); color: #0f172a; border-color: var(--accent); }}

        .stats-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 1rem; margin-bottom: 2rem; }}
        .stat-card {{ background: var(--card-bg); border: 1px solid var(--border); border-radius: 12px; padding: 1.25rem; text-align: center; }}
        .stat-card h3 {{ font-size: 0.8rem; color: var(--text-muted); text-transform: uppercase; letter-spacing: 0.05em; }}
        .stat-card p {{ font-size: 1.8rem; font-weight: 700; color: var(--text); margin-top: 0.5rem; }}

        .section-title {{ font-size: 1.3rem; font-weight: 600; margin-bottom: 1rem; color: var(--accent); }}
        
        .legal-box {{ background: rgba(30, 41, 59, 0.6); border: 1px solid var(--border); border-left: 4px solid var(--swiss-red); border-radius: 12px; padding: 1.25rem; margin-bottom: 2rem; }}
        .legal-box h3 {{ color: #f87171; font-size: 1rem; margin-bottom: 0.5rem; display: flex; align-items: center; gap: 0.5rem; }}
        .legal-box p {{ font-size: 0.85rem; color: var(--text-muted); margin-bottom: 0.5rem; }}

        .chart-box {{ background: var(--card-bg); border: 1px solid var(--border); border-radius: 12px; padding: 1.5rem; margin-bottom: 2.5rem; }}
        .chart-container {{ position: relative; height: 380px; width: 100%; }}

        .cats-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 1rem; margin-bottom: 2.5rem; }}
        .cat-card {{ background: var(--card-bg); border-left: 4px solid var(--accent); border-radius: 8px; padding: 1rem; border: 1px solid var(--border); }}
        .cat-card.lethal {{ border-left-color: var(--danger); }}
        .cat-card.threat {{ border-left-color: var(--warning); }}
        .cat-card.abuse {{ border-left-color: #eab308; }}
        .cat-card.coercion {{ border-left-color: var(--purple); }}
        .cat-card h4 {{ font-size: 1rem; font-weight: 600; margin-bottom: 0.25rem; }}
        .cat-card p {{ font-size: 0.8rem; color: var(--text-muted); margin-bottom: 0.5rem; }}
        .cat-card .badge {{ font-size: 1.2rem; font-weight: 700; }}

        table {{ width: 100%; border-collapse: collapse; background: var(--card-bg); border-radius: 8px; overflow: hidden; margin-bottom: 2rem; }}
        th, td {{ padding: 0.75rem 1rem; text-align: left; border-bottom: 1px solid var(--border); font-size: 0.85rem; }}
        th {{ background: #0f172a; color: var(--text-muted); font-weight: 600; text-transform: uppercase; font-size: 0.75rem; }}
        tr:hover {{ background: rgba(56, 189, 248, 0.05); }}

        input[type="text"] {{ width: 100%; padding: 0.75rem 1rem; background: var(--card-bg); border: 1px solid var(--border); border-radius: 8px; color: var(--text); margin-bottom: 1.5rem; outline: none; font-size: 0.9rem; }}
        input[type="text"]:focus {{ border-color: var(--accent); }}

        .tag {{ display: inline-block; padding: 0.2rem 0.5rem; border-radius: 4px; font-size: 0.75rem; font-weight: 600; background: rgba(56, 189, 248, 0.2); color: var(--accent); margin-right: 0.25rem; }}
        .tag.danger {{ background: rgba(239, 68, 68, 0.2); color: var(--danger); }}
        .tag.warning {{ background: rgba(245, 158, 11, 0.2); color: var(--warning); }}
        .tag.purple {{ background: rgba(168, 85, 247, 0.2); color: var(--purple); }}
    </style>
</head>
<body>
    <header>
        <div>
            <h1>{title}</h1>
            <p>{subtitle}</p>
        </div>
        <div class="lang-switch">
            <a href="Forensic_Dashboard_fr.html" class="lang-btn {'active' if is_fr else ''}">🇫🇷 Français (_fr)</a>
            <a href="Forensic_Dashboard_de.html" class="lang-btn {'active' if not is_fr else ''}">🇩🇪 Deutsch (_de)</a>
        </div>
    </header>

    <div class="stats-grid">
        <div class="stat-card">
            <h3>{'Total Fichiers Catalogués' if is_fr else 'Total Katalogisierte Dateien'}</h3>
            <p>{data['total_records']:,}</p>
        </div>
        <div class="stat-card">
            <h3>{'Indices Probants Élevés' if is_fr else 'Beweisrelevante Treffer'}</h3>
            <p style="color: var(--danger);">{len(data['triaged_high_interest']):,}</p>
        </div>
        <div class="stat-card">
            <h3>{'Segments Vocaux Transcrits' if is_fr else 'Transkribierte Sprachsegmente'}</h3>
            <p style="color: var(--accent);">{data['total_speeches']:,}</p>
        </div>
        <div class="stat-card">
            <h3>{'Fichiers Inaccessibles' if is_fr else 'Nicht lesbare Dateien'}</h3>
            <p style="color: var(--warning);">{data['dead_letter_count']:,}</p>
        </div>
    </div>

    <div class="legal-box">
        <h3>🇨🇭 {legal_title}</h3>
        {legal_basis_html}
    </div>

    <!-- 📊 HISTOGRAM CHART OF ESKALATIONSVERLAUF -->
    <div class="chart-box">
        <h2 class="section-title">{escalation_title}</h2>
        <div class="chart-container">
            <canvas id="escalationChart"></canvas>
        </div>
    </div>

    <h2 class="section-title">🏷️ {cat_summary_title}</h2>
    <div class="cats-grid">
"""
    for cat_key, cat_data in watch_cats.items():
        cls_name = "lethal" if "LETHAL" in cat_key else ("threat" if "PHYSICAL" in cat_key else ("coercion" if "COERCION" in cat_key else "abuse"))
        html_content += f"""
        <div class="cat-card {cls_name}">
            <h4>{cat_data['title']}</h4>
            <p>{cat_data['qualification']}</p>
            <div class="badge">{data['category_counts'][cat_key]:,} {'termes trouvés' if is_fr else 'Treffer'}</div>
        </div>
        """

    html_content += f"""
    </div>

    <h2 class="section-title">📈 {pattern_density_title}</h2>
    <table>
        <thead>
            <tr>
                <th>{'Année' if is_fr else 'Jahr'}</th>
                <th>{'Total Fichiers' if is_fr else 'Total Dateien'}</th>
                <th>{'Indices Élevés' if is_fr else 'Beweisrelevant'}</th>
                <th>{'Expulsion' if is_fr else 'Ausweisung'}</th>
                <th>{'Injures' if is_fr else 'Beschimpfungen'}</th>
                <th>{'Menaces' if is_fr else 'Drohungen'}</th>
                <th>{'Coercition' if is_fr else 'Nötigung'}</th>
            </tr>
        </thead>
        <tbody>
"""
    for y in data['sorted_years']:
        st = data['yearly_stats'][y]
        pt = data['pattern_density_by_year'][y]
        html_content += f"""
            <tr>
                <td><strong>{y}</strong></td>
                <td>{st['total']:,}</td>
                <td><span class="tag warning">{st['high_interest']:,}</span></td>
                <td><span class="tag danger">{pt['expulsion']:,}</span></td>
                <td><span class="tag">{pt['insult']:,}</span></td>
                <td><span class="tag danger">{pt['threat']:,}</span></td>
                <td><span class="tag purple">{pt['coercion']:,}</span></td>
            </tr>
        """

    html_content += f"""
        </tbody>
    </table>

    <h2 class="section-title">🚨 {evidence_register_title}</h2>
    <input type="text" id="searchInput" onkeyup="filterTable()" placeholder="{search_placeholder}">

    <table id="evidenceTable">
        <thead>
            <tr>
                <th>{'Année' if is_fr else 'Jahr'}</th>
                <th>{'Nom du Fichier' if is_fr else 'Dateiname'}</th>
                <th>{'Catégories' if is_fr else 'Kategorien'}</th>
                <th>{'Mots-Clés' if is_fr else 'Schlüsselwörter'}</th>
                <th>{'Extrait Transcription' if is_fr else 'Transkriptauszug'}</th>
            </tr>
        </thead>
        <tbody>
"""
    for item in data['triaged_high_interest']:
        cats = " ".join([f'<span class="tag">{c.replace("WATCH_", "")}</span>' for c in item["matched_categories"]])
        terms = ", ".join(item["matched_keywords"][:5]) or "—"
        sample = item["sample_transcript"].replace("<", "&lt;").replace(">", "&gt;").strip()
        if len(sample) > 120:
            sample = sample[:117] + "..."
        html_content += f"""
            <tr>
                <td>{item['year']}</td>
                <td><strong>{item['name']}</strong></td>
                <td>{cats}</td>
                <td style="color: var(--accent);">{terms}</td>
                <td style="color: var(--text-muted);">{sample}</td>
            </tr>
        """

    # Interactive Chart.js setup for Eskalationsverlauf Histogram
    lbl_lethal = "🔴 WATCH_LETHAL (Todesdrohungen)" if not is_fr else "🔴 WATCH_LETHAL (Menaces de mort)"
    lbl_threats = "🟠 WATCH_PHYSICAL_THREATS (Gewalt)" if not is_fr else "🟠 WATCH_PHYSICAL_THREATS (Voies de fait)"
    lbl_abuse = "🟡 WATCH_VERBAL_ABUSE (Beschimpfung)" if not is_fr else "🟡 WATCH_VERBAL_ABUSE (Injures)"
    lbl_coercion = "🟣 WATCH_DOMESTIC_COERCION (Nötigung)" if not is_fr else "🟣 WATCH_DOMESTIC_COERCION (Contrainte)"
    lbl_procedural = "🔵 WATCH_LEGAL_PROCEDURAL (Polizei/Gericht)" if not is_fr else "🔵 WATCH_LEGAL_PROCEDURAL (Justice/Police)"
    lbl_integrity = "🟢 WATCH_EVIDENCE_INTEGRITY (Beweise)" if not is_fr else "🟢 WATCH_EVIDENCE_INTEGRITY (Preuves)"

    html_content += f"""
        </tbody>
    </table>

    <script>
        function filterTable() {{
            var input = document.getElementById("searchInput");
            var filter = input.value.toLowerCase();
            var table = document.getElementById("evidenceTable");
            var tr = table.getElementsByTagName("tr");

            for (var i = 1; i < tr.length; i++) {{
                var text = tr[i].textContent || tr[i].innerText;
                if (text.toLowerCase().indexOf(filter) > -1) {{
                    tr[i].style.display = "";
                }} else {{
                    tr[i].style.display = "none";
                }}
            }}
        }}

        // Render Chart.js Stacked Bar Chart Histogram
        document.addEventListener("DOMContentLoaded", function() {{
            const ctx = document.getElementById('escalationChart').getContext('2d');
            new Chart(ctx, {{
                type: 'bar',
                data: {{
                    labels: {json.dumps(chart_years)},
                    datasets: [
                        {{ label: '{lbl_lethal}', data: {json.dumps(chart_lethal)}, backgroundColor: '#ef4444' }},
                        {{ label: '{lbl_threats}', data: {json.dumps(chart_threats)}, backgroundColor: '#f59e0b' }},
                        {{ label: '{lbl_abuse}', data: {json.dumps(chart_abuse)}, backgroundColor: '#eab308' }},
                        {{ label: '{lbl_coercion}', data: {json.dumps(chart_coercion)}, backgroundColor: '#a855f7' }},
                        {{ label: '{lbl_procedural}', data: {json.dumps(chart_procedural)}, backgroundColor: '#38bdf8' }},
                        {{ label: '{lbl_integrity}', data: {json.dumps(chart_integrity)}, backgroundColor: '#10b981' }}
                    ]
                }},
                options: {{
                    responsive: true,
                    maintainAspectRatio: false,
                    scales: {{
                        x: {{ stacked: true, grid: {{ color: '#334155' }}, ticks: {{ color: '#94a3b8' }} }},
                        y: {{ stacked: true, grid: {{ color: '#334155' }}, ticks: {{ color: '#94a3b8' }} }}
                    }},
                    plugins: {{
                        legend: {{ labels: {{ color: '#f8fafc', font: {{ family: 'Inter', size: 11 }} }} }},
                        tooltip: {{ backgroundColor: '#1e293b', titleColor: '#38bdf8', bodyColor: '#f8fafc', borderColor: '#334155', borderWidth: 1 }}
                    }}
                }}
            }});
        }});
    </script>
</body>
</html>
"""
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html_content)

    # Mirror default dashboard to Forensic_Dashboard.html
    if is_fr:
        default_html = os.path.join(export_dir, "Forensic_Dashboard.html")
        with open(default_html, "w", encoding="utf-8") as f_def:
            with open(html_path, "r", encoding="utf-8") as f_src:
                f_def.write(f_src.read())

    print(f"✅ Generated Interactive HTML Dashboard ({lang}): {os.path.abspath(html_path)}")

def main():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    db_path = os.path.join(script_dir, '..', 'aivoicetagger_state.db')
    export_dir = os.path.join(script_dir, '..', 'export')
    os.makedirs(export_dir, exist_ok=True)

    print(f"Connecting to database: {os.path.abspath(db_path)}")
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # Query record state counts
    state_counts = dict(cursor.execute("SELECT state, COUNT(*) FROM records GROUP BY state").fetchall())
    total_records = sum(state_counts.values())

    # Query dead letter count
    dead_letter_count = cursor.execute("SELECT COUNT(*) FROM dead_letter").fetchone()[0]

    # Query speeches count
    total_speeches = cursor.execute("SELECT COUNT(*) FROM speeches").fetchone()[0]

    # Query all records for forensic analysis
    records = cursor.execute("SELECT * FROM records").fetchall()

    # Query speeches grouped by record_id
    speeches_by_record = {}
    for sp in cursor.execute("SELECT record_id, script, confidence, time_frame FROM speeches").fetchall():
        rid = sp["record_id"]
        if rid not in speeches_by_record:
            speeches_by_record[rid] = []
        speeches_by_record[rid].append(dict(sp))

    # Process data analytics
    yearly_stats = {}
    category_counts = {cat: 0 for cat in WATCH_CATEGORIES_FR}
    pattern_density_by_year = {}
    triaged_high_interest = []

    for r in records:
        r_dict = dict(r)
        rid = r_dict["record_id"]
        name = r_dict.get("name", "")
        directory = r_dict.get("directory", "")
        date_record_day = r_dict.get("date_record_day", "")
        state = r_dict.get("state", "")
        story = r_dict.get("story", "")

        year = extract_year(name, directory, date_record_day)
        if year not in yearly_stats:
            yearly_stats[year] = {"total": 0, "high_interest": 0, "categories": {cat: 0 for cat in WATCH_CATEGORIES_FR}}
            pattern_density_by_year[year] = {"expulsion": 0, "insult": 0, "threat": 0, "coercion": 0}

        yearly_stats[year]["total"] += 1

        # Combine text for pattern search
        speech_texts = " ".join([sp["script"] for sp in speeches_by_record.get(rid, [])])
        combined_text = f"{name} {story} {speech_texts}"
        combined_text_lower = combined_text.lower()

        # Count specific pattern matches
        exp_count = len(EXPULSION_PATTERN.findall(combined_text))
        ins_count = len(INSULT_PATTERN.findall(combined_text))
        thr_count = len(THREAT_PATTERN.findall(combined_text))
        coe_count = len(COERCION_PATTERN.findall(combined_text))

        pattern_density_by_year[year]["expulsion"] += exp_count
        pattern_density_by_year[year]["insult"] += ins_count
        pattern_density_by_year[year]["threat"] += thr_count
        pattern_density_by_year[year]["coercion"] += coe_count

        matched_cats = set()
        matched_kws = set()

        for cat_key, cat_data in WATCH_CATEGORIES_FR.items():
            for kw in cat_data["keywords"]:
                if kw in combined_text_lower:
                    matched_cats.add(cat_key)
                    matched_kws.add(kw)
                    category_counts[cat_key] += 1
                    yearly_stats[year]["categories"][cat_key] += 1

        is_high_interest = state == "TriagedHighInterest" or len(matched_cats) > 0
        if is_high_interest:
            yearly_stats[year]["high_interest"] += 1
            triaged_high_interest.append({
                "record_id": rid,
                "name": name,
                "directory": directory,
                "duration_seconds": r_dict.get("duration_seconds", 0.0),
                "state": state,
                "year": year,
                "matched_categories": list(matched_cats),
                "matched_keywords": list(matched_kws),
                "story": story,
                "speech_count": len(speeches_by_record.get(rid, [])),
                "sample_transcript": speech_texts[:300] if speech_texts else story[:300]
            })

    sorted_years = sorted([y for y in yearly_stats.keys() if y != "Unknown"]) + (["Unknown"] if "Unknown" in yearly_stats else [])
    timestamp_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    data = {
        "timestamp_str": timestamp_str,
        "total_records": total_records,
        "total_speeches": total_speeches,
        "dead_letter_count": dead_letter_count,
        "state_counts": state_counts,
        "category_counts": category_counts,
        "yearly_stats": yearly_stats,
        "pattern_density_by_year": pattern_density_by_year,
        "triaged_high_interest": triaged_high_interest,
        "sorted_years": sorted_years
    }

    # Generate French & German Markdown Reports
    generate_markdown_report(export_dir, "fr", data)
    generate_markdown_report(export_dir, "de", data)

    # Generate French & German HTML Dashboards with Interactive Histograms
    generate_html_dashboard(export_dir, "fr", data)
    generate_html_dashboard(export_dir, "de", data)

    conn.close()
    print("\n🎉 Bilingual Swiss Law Forensic Reporting Phase with Interactive Histograms complete!")

if __name__ == "__main__":
    main()
