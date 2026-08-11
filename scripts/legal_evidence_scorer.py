#!/usr/bin/env python3
"""
legal_evidence_scorer.py — Legal Evidence Qualification & Chronological Timeline

Processes transcribed audio records from aivoicetagger_state.db and:
1. Tags each record with French penal code legal qualifications
2. Computes an intensity_rating (1-10) based on verbatim analysis
3. Generates a chronological escalation timeline (Markdown + JSON)

Legal Framework Applied:
- Art. 222-33-2-1 Code Pénal: Harcèlement moral au sein du couple
- Art. 222-14-3 Code Pénal: Menaces et violences
- Contrainte domestique et contrôle coercitif
- Art. 434-4 Code Pénal: Obstruction de preuve

Usage:
    python scripts/legal_evidence_scorer.py
"""

import sqlite3
import json
import re
from pathlib import Path
from datetime import datetime, timezone
from collections import Counter, defaultdict

BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = BASE_DIR / "aivoicetagger_state.db"
EXPORT_DIR = BASE_DIR / "export"
EXPORT_DIR.mkdir(parents=True, exist_ok=True)

# ═══════════════════════════════════════════════════════════════════════
# Legal Qualification Rules
# ═══════════════════════════════════════════════════════════════════════

LEGAL_CATEGORIES = {
    "Harcèlement Moral (Art. 222-33-2-1)": {
        "keywords": [
            "harcèlement", "insulte", "t'es nul", "t'es nulle", "un gros nase",
            "gros nase", "vermine", "ta gueule", "gros porc", "sale blanc bec",
            "t'es moche", "t'es vilain", "t'es un gros nul", "imbécile",
            "abruti", "bouffon", "ordure", "con", "connard", "salope",
            "pute", "enculé", "merde", "bâtard", "humiliation",
            "dégage", "casse-toi", "dégage ma vie",
        ],
        "description": "Harcèlement moral au sein du couple — dégradation répétée des conditions de vie",
        "severity_weight": 3,
    },
    "Menaces de Violences (Art. 222-14-3)": {
        "keywords": [
            "menace", "menacer", "casser la gueule", "je vais te frapper",
            "je vais te défoncer", "je vais te botter les fesses",
            "je vais te mettre à terre", "la claque de ta vie",
            "tu vas mourir", "crève", "tuer", "mort", "pas fini avec toi",
            "tu va voir", "tu vas voir ta gueule", "je vais te faire",
            "frapper", "casser", "détruire", "brûler",
            "table basse renversée", "violence", "égorger",
            "arme", "couteau", "pistolet",
        ],
        "description": "Menaces de violences physiques directes ou indirectes",
        "severity_weight": 5,
    },
    "Contrainte Domestique & Contrôle Coercitif": {
        "keywords": [
            "sous mon toit", "volige sous mon toit", "je dicte ma loi",
            "cagibi", "chambre", "argent", "chantage", "remboursement",
            "mon droit", "tu fais pas ce que tu veux", "illégal",
            "mon frère", "faire venir", "propriétaire",
        ],
        "description": "Contrôle coercitif du domicile, chantage financier, intimidation par tiers",
        "severity_weight": 4,
    },
    "Obstruction de Preuve (Art. 434-4)": {
        "keywords": [
            "enregistre", "je me moque que tu m'enregistres", "preuve",
            "avocat", "police", "tribunal", "justice", "plainte",
            "juge", "procès", "gendarmerie", "commissariat",
        ],
        "description": "Intimidation relative à la collecte de preuves ou contact judiciaire",
        "severity_weight": 2,
    },
}


def classify_legal_tags(text: str) -> list[dict]:
    """Classify a transcript against legal categories. Returns matched tags with details."""
    if not text:
        return []

    text_lower = text.lower()
    matches = []

    for category, rules in LEGAL_CATEGORIES.items():
        matched_keywords = []
        for kw in rules["keywords"]:
            if kw.lower() in text_lower:
                matched_keywords.append(kw)

        if matched_keywords:
            matches.append({
                "category": category,
                "description": rules["description"],
                "matched_keywords": matched_keywords,
                "keyword_count": len(matched_keywords),
                "severity_weight": rules["severity_weight"],
            })

    return matches


def compute_intensity_rating(
    legal_tags: list[dict],
    verbatim_stats: dict,
    duration_seconds: float,
    speech_count: int,
) -> int:
    """Compute intensity rating (1-10) based on legal tags and verbatim analysis."""
    score = 0.0

    # Base score from legal tag severity weights
    for tag in legal_tags:
        score += tag["severity_weight"] * min(tag["keyword_count"], 5) * 0.3

    # Verbatim category bonuses
    count_lethal = verbatim_stats.get("count_lethal", 0)
    count_menaces = verbatim_stats.get("count_menaces", 0)
    count_insultes = verbatim_stats.get("count_insultes", 0)
    count_legal = verbatim_stats.get("count_legal", 0)

    score += count_lethal * 2.0  # Lethal references are most severe
    score += count_menaces * 1.5
    score += count_insultes * 0.8
    score += count_legal * 0.3

    # Density bonus: more speech segments = sustained harassment
    if speech_count > 20:
        score += 1.0
    if speech_count > 50:
        score += 1.0

    # Duration penalty for very short clips (context may be thin)
    if duration_seconds < 30:
        score *= 0.7

    # Clamp to 1-10
    rating = max(1, min(10, round(score)))
    return rating


def parse_date(date_str: str | None) -> datetime | None:
    """Try to parse various date formats."""
    if not date_str:
        return None
    for fmt in ["%Y-%m-%dT%H:%M:%S+00:00", "%Y-%m-%dT%H:%M:%S.%f+00:00",
                "%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%S.%f%z",
                "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"]:
        try:
            return datetime.strptime(date_str, fmt)
        except ValueError:
            continue
    # Try with dateutil as fallback
    try:
        from dateutil.parser import parse as dateutil_parse
        return dateutil_parse(date_str)
    except Exception:
        return None


def generate_timeline_markdown(timeline_entries: list[dict]) -> str:
    """Generate a Markdown report from timeline entries."""
    md = []
    md.append("# 🚨 AiVoiceTagger — Legal Evidence Chronological Timeline")
    md.append("")
    md.append(f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}  ")
    md.append(f"**Total Evidence Records:** {len(timeline_entries)}  ")
    md.append(f"**Legal Framework:** Code Pénal français (Art. 222-33-2-1, 222-14-3, 434-4)  ")
    md.append("")
    md.append("---")
    md.append("")

    # Group by year-month
    by_month = defaultdict(list)
    undated = []
    for entry in timeline_entries:
        if entry.get("date_parsed"):
            key = entry["date_parsed"].strftime("%Y-%m")
            by_month[key].append(entry)
        else:
            undated.append(entry)

    # Escalation summary
    md.append("## 📈 Escalation Summary")
    md.append("")
    md.append("| Period | Incidents | Avg Intensity | Max Intensity | Legal Categories |")
    md.append("| :--- | :---: | :---: | :---: | :--- |")

    for month_key in sorted(by_month.keys()):
        entries = by_month[month_key]
        intensities = [e["intensity_rating"] for e in entries]
        all_cats = set()
        for e in entries:
            for t in e.get("legal_tags_parsed", []):
                all_cats.add(t["category"].split("(")[0].strip())
        avg_int = sum(intensities) / len(intensities) if intensities else 0
        max_int = max(intensities) if intensities else 0
        cats_str = ", ".join(sorted(all_cats)) if all_cats else "—"
        md.append(f"| **{month_key}** | {len(entries)} | {avg_int:.1f} | {max_int} | {cats_str} |")

    if undated:
        md.append(f"| *(undated)* | {len(undated)} | — | — | — |")

    md.append("")
    md.append("---")
    md.append("")

    # Detailed entries
    md.append("## 📋 Detailed Evidence Record Inventory")
    md.append("")

    for month_key in sorted(by_month.keys()):
        entries = by_month[month_key]
        md.append(f"### 📅 {month_key}")
        md.append("")

        for entry in sorted(entries, key=lambda e: e.get("date_parsed") or datetime.min):
            intensity_bar = "🔴" * min(entry["intensity_rating"], 10)
            date_str = entry.get("date_parsed", "").strftime("%Y-%m-%d %H:%M") if entry.get("date_parsed") else "Unknown"

            md.append(f"#### `{entry['name']}`")
            md.append(f"- **Date:** {date_str}  ")
            md.append(f"- **Directory:** `{entry['directory']}`  ")
            md.append(f"- **Duration:** {entry['duration_seconds']:.0f}s  ")
            md.append(f"- **Intensity:** {entry['intensity_rating']}/10 {intensity_bar}  ")
            md.append(f"- **Pattern Match Score:** {entry.get('pattern_match_score', 0.0):.2f}  ")

            if entry.get("legal_tags_parsed"):
                md.append("- **Legal Qualifications:**")
                for tag in entry["legal_tags_parsed"]:
                    kw_str = ", ".join(tag["matched_keywords"][:5])
                    md.append(f"  - ⚖️ **{tag['category']}** — matched: *{kw_str}*")

            # Transcript preview
            story = entry.get("story", "") or entry.get("triage_summary", "")
            if story:
                preview = story[:200].replace("\n", " ")
                if len(story) > 200:
                    preview += "..."
                md.append(f"- **Transcript Preview:** _{preview}_")

            md.append("")

    md.append("---")
    md.append("*Report generated by AiVoiceTagger Legal Evidence Scorer.*")

    return "\n".join(md)


def main():
    print("=" * 70)
    print("⚖️  AiVoiceTagger — Legal Evidence Scorer & Timeline Builder")
    print(f"   Database: {DB_PATH}")
    print(f"   Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 70)

    if not DB_PATH.exists():
        print("❌ Database not found.")
        return

    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # Ensure columns exist
    for col_sql in [
        "ALTER TABLE records ADD COLUMN legal_tags TEXT",
        "ALTER TABLE records ADD COLUMN intensity_rating INTEGER DEFAULT 0",
        "ALTER TABLE records ADD COLUMN pattern_match_score REAL DEFAULT 0.0",
    ]:
        try:
            cursor.execute(col_sql)
        except Exception:
            pass
    conn.commit()

    # ─────────────────────────────────────────────────────────────────
    # Load all records with text content
    # ─────────────────────────────────────────────────────────────────
    print("\n📋 Loading records with text content...")

    cursor.execute("""
        SELECT record_id, name, directory, story, triage_summary,
               triage_keywords_json, stats_verbatim_json,
               duration_seconds, speech_count, state,
               date_record_day, date_last_write,
               pattern_match_score, priority
        FROM records
        WHERE (story IS NOT NULL AND story != '')
           OR (triage_summary IS NOT NULL AND triage_summary != '')
           OR state IN ('TriagedHighInterest', 'Done', 'NlpDone', 'Transcribed')
    """)
    records = cursor.fetchall()
    print(f"  Found {len(records)} records to evaluate.")

    # ─────────────────────────────────────────────────────────────────
    # Score each record
    # ─────────────────────────────────────────────────────────────────
    print("\n⚖️  Scoring records against legal framework...")

    timeline_entries = []
    category_counts = Counter()
    now_iso = datetime.now(timezone.utc).isoformat()

    for rec in records:
        text = (rec["story"] or "") + " " + (rec["triage_summary"] or "")

        # Parse verbatim stats
        verbatim_stats = {}
        if rec["stats_verbatim_json"]:
            try:
                verbatim_stats = json.loads(rec["stats_verbatim_json"])
            except Exception:
                pass

        # Classify legal tags
        legal_tags = classify_legal_tags(text)

        # Compute intensity
        intensity = compute_intensity_rating(
            legal_tags,
            verbatim_stats,
            rec["duration_seconds"] or 0.0,
            rec["speech_count"] or 0,
        )

        # Build legal tags JSON
        legal_tags_json = json.dumps(
            [{"category": t["category"], "keywords": t["matched_keywords"]} for t in legal_tags],
            ensure_ascii=False
        )

        # Update DB
        cursor.execute("""
            UPDATE records
            SET legal_tags = ?, intensity_rating = ?, updated_at = ?
            WHERE record_id = ?
        """, (legal_tags_json, intensity, now_iso, rec["record_id"]))

        # Count categories
        for tag in legal_tags:
            category_counts[tag["category"]] += 1

        # Parse date for timeline
        date_parsed = parse_date(rec["date_record_day"]) or parse_date(rec["date_last_write"])

        timeline_entries.append({
            "record_id": rec["record_id"],
            "name": rec["name"],
            "directory": rec["directory"],
            "date_record_day": rec["date_record_day"],
            "date_last_write": rec["date_last_write"],
            "date_parsed": date_parsed,
            "duration_seconds": rec["duration_seconds"] or 0.0,
            "speech_count": rec["speech_count"] or 0,
            "state": rec["state"],
            "story": rec["story"],
            "triage_summary": rec["triage_summary"],
            "legal_tags_parsed": legal_tags,
            "legal_tags_json": legal_tags_json,
            "intensity_rating": intensity,
            "pattern_match_score": rec["pattern_match_score"] or 0.0,
            "priority": rec["priority"] or 0,
        })

    conn.commit()

    # ─────────────────────────────────────────────────────────────────
    # Print summary
    # ─────────────────────────────────────────────────────────────────
    print(f"\n  ✅ Scored {len(timeline_entries)} records.")
    print(f"\n  📊 Legal Category Distribution:")
    for cat, cnt in category_counts.most_common():
        print(f"     {cnt:>5}x  ⚖️  {cat}")

    intensity_dist = Counter(e["intensity_rating"] for e in timeline_entries)
    print(f"\n  📊 Intensity Distribution:")
    for rating in sorted(intensity_dist.keys(), reverse=True):
        bar = "█" * intensity_dist[rating]
        print(f"     Rating {rating:>2}/10: {intensity_dist[rating]:>4} records  {bar}")

    # ─────────────────────────────────────────────────────────────────
    # Export timeline JSON
    # ─────────────────────────────────────────────────────────────────
    print("\n📤 Exporting timeline files...")

    # JSON export (strip non-serializable datetime objects)
    json_entries = []
    for e in timeline_entries:
        entry_copy = dict(e)
        entry_copy["date_parsed"] = entry_copy["date_parsed"].isoformat() if entry_copy.get("date_parsed") else None
        entry_copy["legal_tags_parsed"] = [
            {"category": t["category"], "keywords": t["matched_keywords"], "severity": t["severity_weight"]}
            for t in entry_copy.get("legal_tags_parsed", [])
        ]
        json_entries.append(entry_copy)

    timeline_json_path = EXPORT_DIR / "LegalEvidenceTimeline.json"
    with open(timeline_json_path, "w", encoding="utf-8") as f:
        json.dump(json_entries, f, indent=2, ensure_ascii=False)
    print(f"  ✅ {timeline_json_path}")

    # Markdown report
    md_content = generate_timeline_markdown(timeline_entries)
    timeline_md_path = EXPORT_DIR / "LegalEvidenceTimeline.md"
    with open(timeline_md_path, "w", encoding="utf-8") as f:
        f.write(md_content)
    print(f"  ✅ {timeline_md_path}")

    print(f"\n{'=' * 70}")
    print(f"🎉 Legal evidence scoring complete!")
    print(f"   Timeline: {timeline_md_path}")
    print(f"   JSON Data: {timeline_json_path}")
    print(f"{'=' * 70}")

    conn.close()


if __name__ == "__main__":
    main()
