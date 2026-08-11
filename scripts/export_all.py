import sqlite3
import json
import csv
from pathlib import Path
from datetime import datetime

base_dir = Path(__file__).resolve().parent.parent
db_path = base_dir / "aivoicetagger_state.db"
export_dir = base_dir / "export"
export_dir.mkdir(parents=True, exist_ok=True)

if not db_path.exists():
    print(f"❌ Error: Database file not found at {db_path}")
    exit(1)

conn = sqlite3.connect(db_path)
conn.row_factory = sqlite3.Row
cursor = conn.cursor()

now_dt = datetime.now()
now_iso = now_dt.strftime("%Y-%m-%d %H:%M:%S")
timestamp_prefix = now_dt.strftime("%Y%m%d_%H%M%S")

print(f"Connecting to state DB: {db_path}")

# Fetch all records
cursor.execute("""
    SELECT record_id, name, directory, date_record_day, date_last_write,
           length_bytes, duration_seconds, speech_count, story,
           stats_verbatim_json, state, is_degraded, triage_keywords_json, triage_summary,
           legal_tags, intensity_rating, pattern_match_score, priority, updated_at
    FROM records
""")
records_rows = cursor.fetchall()
print(f"Total cataloged records found: {len(records_rows)}")

# Fetch dead letters
cursor.execute("""
    SELECT id, record_id, chunk_id, stage, error, context_json, created_at
    FROM dead_letter
    ORDER BY id DESC
""")
dead_letter_rows = cursor.fetchall()
print(f"Total dead letter failures found: {len(dead_letter_rows)}")

record_info_list = []
digest_list = []
remarkable_list = []
triaged_high_list = []
recordstrike_list = []
dead_letters_list = []

for r in records_rows:
    record_id = r["record_id"]
    state = r["state"] or ""
    
    # Parse stats_verbatim
    stats_verbatim = {}
    if r["stats_verbatim_json"]:
        try:
            stats_verbatim = json.loads(r["stats_verbatim_json"])
        except Exception:
            pass

    # Parse triage keywords
    triage_keywords = []
    if r["triage_keywords_json"]:
        try:
            triage_keywords = json.loads(r["triage_keywords_json"])
        except Exception:
            pass
            
    # Fetch speeches for this record
    cursor.execute("""
        SELECT time_frame, script, confidence, word_count, offset_ms, duration_ms, words_json
        FROM speeches
        WHERE record_id = ?
        ORDER BY offset_ms ASC
    """, (record_id,))
    speeches_rows = cursor.fetchall()
    
    speeches_list = []
    for s in speeches_rows:
        words = []
        if s["words_json"]:
            try:
                words = json.loads(s["words_json"])
            except Exception:
                pass
        speeches_list.append({
            "time_frame": s["time_frame"],
            "script": s["script"],
            "confidence": s["confidence"],
            "word_count": s["word_count"],
            "offset_ms": s["offset_ms"],
            "duration_ms": s["duration_ms"],
            "words": words
        })

    is_remarkable = False
    if stats_verbatim:
        is_remarkable = bool(
            stats_verbatim.get("count_lethal", 0) > 0 or
            stats_verbatim.get("count_legal", 0) > 0 or
            stats_verbatim.get("count_menaces", 0) > 0 or
            stats_verbatim.get("count_insultes", 0) > 0 or
            stats_verbatim.get("is_remarkable", False)
        )
    if state == "TriagedHighInterest" or len(triage_keywords) > 0:
        is_remarkable = True

    # Parse legal tags
    legal_tags = []
    legal_tags_raw = r["legal_tags"] if "legal_tags" in r.keys() else None
    if legal_tags_raw:
        try:
            legal_tags = json.loads(legal_tags_raw)
        except Exception:
            pass

    rec_obj = {
        "record_id": r["record_id"],
        "name": r["name"],
        "directory": r["directory"],
        "date_record_day": r["date_record_day"],
        "date_last_write": r["date_last_write"],
        "length_bytes": r["length_bytes"],
        "duration_seconds": r["duration_seconds"],
        "speech_count": r["speech_count"],
        "story": r["story"] or r["triage_summary"] or "",
        "triage_summary": r["triage_summary"] or "",
        "triage_keywords": triage_keywords,
        "stats_verbatim": stats_verbatim,
        "speeches": speeches_list,
        "state": state,
        "is_degraded": bool(r["is_degraded"]),
        "legal_tags": legal_tags,
        "intensity_rating": r["intensity_rating"] if "intensity_rating" in r.keys() else 0,
        "pattern_match_score": r["pattern_match_score"] if "pattern_match_score" in r.keys() else 0.0,
        "priority": r["priority"] if "priority" in r.keys() else 0,
        "updated_at": r["updated_at"]
    }

    # Add to Triaged High list
    if state == "TriagedHighInterest" or len(triage_keywords) > 0 or "High" in state:
        triaged_high_list.append(rec_obj)

    # Add to RecordStrike list
    if any(d.lower() in (r["directory"] or "").lower() for d in ["RecordStrike", "Select_Sort"]):
        recordstrike_list.append(rec_obj)
    
    # Include in main exports if processed, triaged, dead letter, or has speech data
    if state in ("Done", "TriagedHighInterest", "TriagedLowInterest", "Transcribed", "NlpDone", "DeadLetter", "Failed") or r["speech_count"] > 0 or r["triage_summary"]:
        record_info_list.append(rec_obj)
        
        # Digest object (speech list cleared for lightweight telemetry)
        rec_digest = dict(rec_obj)
        rec_digest["speeches"] = []
        digest_list.append(rec_digest)
        
        if is_remarkable:
            remarkable_list.append(rec_obj)

# Write RecordInfo.json
record_info_path = export_dir / "RecordInfo.json"
with open(record_info_path, "w", encoding="utf-8") as f:
    json.dump(record_info_list, f, indent=2, ensure_ascii=False)
print(f"✅ Exported {len(record_info_list)} records to {record_info_path}")

# Write DigestRecordInfo.json
digest_path = export_dir / "DigestRecordInfo.json"
with open(digest_path, "w", encoding="utf-8") as f:
    json.dump(digest_list, f, indent=2, ensure_ascii=False)
print(f"✅ Exported {len(digest_list)} digest items to {digest_path}")

# Write RemarkableRecordInfo.json
remarkable_path = export_dir / "RemarkableRecordInfo.json"
with open(remarkable_path, "w", encoding="utf-8") as f:
    json.dump(remarkable_list, f, indent=2, ensure_ascii=False)
print(f"✅ Exported {len(remarkable_list)} remarkable items to {remarkable_path}")

# Write TriagedHighInterest.json
triaged_json_path = export_dir / "TriagedHighInterest.json"
with open(triaged_json_path, "w", encoding="utf-8") as f:
    json.dump(triaged_high_list, f, indent=2, ensure_ascii=False)
print(f"🚨 Exported {len(triaged_high_list)} Triaged HIGH Interest records to {triaged_json_path}")

# Write TriagedHighInterest.csv
triaged_csv_path = export_dir / "TriagedHighInterest.csv"
with open(triaged_csv_path, "w", newline="", encoding="utf-8") as f:
    writer = csv.writer(f)
    writer.writerow([
        "RecordID", "Name", "Directory", "DateLastWrite", "DurationSeconds",
        "State", "MatchedKeywords", "TriageSummary"
    ])
    for r in triaged_high_list:
        writer.writerow([
            r["record_id"], r["name"], r["directory"], r["date_last_write"],
            r["duration_seconds"], r["state"], ", ".join(r["triage_keywords"]),
            r["triage_summary"]
        ])
print(f"🚨 Exported {len(triaged_high_list)} Triaged HIGH Interest records to {triaged_csv_path}")

# Write Live_RecordList.csv & timestamped CSV
latest_csv_path = export_dir / "Live_RecordList.csv"
timestamped_csv_path = export_dir / f"{timestamp_prefix}_Live_RecordList.csv"
record_list_csv_path = export_dir / "RecordList.csv"

def write_csv_live(target_path):
    with open(target_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([
            "RecordID", "Name", "Directory", "DateRecordDay", "DateLastWrite",
            "DurationSeconds", "SpeechCount", "IsDegraded", "State", "UpdatedAt",
            "ReportGeneratedAt", "Transcript"
        ])
        for r in records_rows:
            writer.writerow([
                r["record_id"], r["name"], r["directory"], r["date_record_day"],
                r["date_last_write"], r["duration_seconds"], r["speech_count"],
                bool(r["is_degraded"]), r["state"], r["updated_at"],
                now_iso, r["story"] or r["triage_summary"] or ""
            ])

write_csv_live(latest_csv_path)
write_csv_live(timestamped_csv_path)
print(f"✅ Exported {len(records_rows)} records to {latest_csv_path} and {timestamped_csv_path}")

# Generate TriagedHighInterest_Report.md
md_path = export_dir / "TriagedHighInterest_Report.md"
md = []
md.append("# 🚨 AiVoiceTagger — Fast Triage & Legal Evidence Report")
md.append(f"**Generated on:** {now_iso}  ")
md.append(f"**Fast Triage Engine:** `ggml-tiny-q8_0.bin` | **Watchlist File:** `watchlist.txt`  ")
md.append(f"**Total High-Interest Flags:** **{len(triaged_high_list)} records**  ")
md.append("")
md.append("---")
md.append("")
md.append("## 🏷️ 6 Consolidated Watch Categories")
md.append("")
md.append("| Category | Scope & Legal Qualification | Key Term Stems |")
md.append("| :--- | :--- | :--- |")
md.append("| 🔴 **`WATCH_LETHAL`** | Death threats, weapon references, severe harm (Art. 221-1 / 222-14-3) | *tuer, mort, meurtre, suicide, arme, couteau, pistolet, fusil, crever, égorger, assasiner* |")
md.append("| 🟠 **`WATCH_PHYSICAL_THREATS`** | Intimidation, physical battery & assault intent | *frapper, casser, défoncer, détruire, bousiller, faire payer, pas fini avec toi, tu vas voir* |")
md.append("| 🟡 **`WATCH_VERBAL_ABUSE`** | Moral harassment, insults & verbal degradation (Art. 222-33-2-1) | *con, connard, salop, salope, pute, enculé, putain, merde, bâtard, abruti, gros nase, ta gueule* |")
md.append("| 🟣 **`WATCH_DOMESTIC_COERCION`** | Domicile infringement, financial coercion & isolation | *cagibi, chambre, chantage, argent, harcèlement, mon frère* |")
md.append("| 🔵 **`WATCH_LEGAL_PROCEDURAL`** | Judicial reporting, police, court & rights statements | *avocat, police, tribunal, plainte, juge, procès, prison, gendarmerie, justice, huissier* |")
md.append("| 🟢 **`WATCH_EVIDENCE_INTEGRITY`** | Recording interference, proof & illegality references | *illégal, preuve, enregistre, micro* |")
md.append("")
md.append("---")
md.append("")
md.append("## 🚨 Top Triaged High-Interest Records Inventory")
md.append("")
md.append("| Record ID | File Name | Directory | Duration | Intensity | Pattern Score | Matched Keywords | Legal Tags | Summary Preview |")
md.append("| :--- | :--- | :--- | :--- | :---: | :---: | :--- | :--- | :--- |")
for r in triaged_high_list[:50]:
    kw_str = ", ".join(r["triage_keywords"]) if r["triage_keywords"] else "High-Interest Flagged"
    summary_clean = (r["triage_summary"] or r["story"] or "").replace("|", "\\|").replace("\n", " ")
    if len(summary_clean) > 80:
        summary_clean = summary_clean[:77] + "..."
    name_clean = r["name"].replace("|", "\\|")
    dir_clean = r["directory"].replace("|", "\\|")
    intensity = r.get("intensity_rating", 0)
    score = r.get("pattern_match_score", 0.0)
    tags_list = [t.get("category", "").split("(")[0].strip() for t in r.get("legal_tags", [])]
    tags_str = ", ".join(tags_list) if tags_list else "—"
    md.append(f"| `{r['record_id'][:12]}...` | `{name_clean}` | `{dir_clean}` | {r['duration_seconds']:.1f}s | **{intensity}/10** | `{score:.2f}` | **`{kw_str}`** | `{tags_str}` | {summary_clean} |")

# Add Dead Letters section to Markdown report
if dead_letter_rows:
    md.append("")
    md.append("---")
    md.append("")
    md.append(f"## ⚠️ Dead Letters & Pipeline Failures Inventory ({len(dead_letter_rows)} Records)")
    md.append("")
    md.append("| ID | Record ID | Stage | Error | Created At |")
    md.append("| :--- | :--- | :--- | :--- | :--- |")
    for dl in dead_letter_rows[:50]:
        rec_id_str = f"`{dl['record_id'][:12]}...`" if dl['record_id'] else "N/A"
        err_clean = (dl["error"] or "").replace("|", "\\|").replace("\n", " ")
        if len(err_clean) > 80:
            err_clean = err_clean[:77] + "..."
        md.append(f"| {dl['id']} | {rec_id_str} | `{dl['stage']}` | {err_clean} | {dl['created_at']} |")

md.append("")
md.append("---")
md.append("*Report generated from `ggml-tiny-q8_0.bin` triage pass in `aivoicetagger_state.db`.*")

with open(md_path, "w", encoding="utf-8") as f:
    f.write("\n".join(md))

print(f"🚨 Created Markdown report: {md_path}")

# Write RecordStrike_Transcripts.json
recordstrike_path = export_dir / "RecordStrike_Transcripts.json"
with open(recordstrike_path, "w", encoding="utf-8") as f:
    json.dump(recordstrike_list, f, indent=2, ensure_ascii=False)
print(f"🎯 Exported {len(recordstrike_list)} RecordStrike baseline records to {recordstrike_path}")

# Write DeadLetters.json & DeadLetters.csv
dead_letters_list = []
for dl in dead_letter_rows:
    dead_letters_list.append({
        "id": dl["id"],
        "record_id": dl["record_id"],
        "chunk_id": dl["chunk_id"],
        "stage": dl["stage"],
        "error": dl["error"],
        "context_json": dl["context_json"],
        "created_at": dl["created_at"]
    })

dead_letters_json_path = export_dir / "DeadLetters.json"
with open(dead_letters_json_path, "w", encoding="utf-8") as f:
    json.dump(dead_letters_list, f, indent=2, ensure_ascii=False)
print(f"⚠️ Exported {len(dead_letters_list)} dead letter records to {dead_letters_json_path}")

dead_letters_csv_path = export_dir / "DeadLetters.csv"
with open(dead_letters_csv_path, "w", newline="", encoding="utf-8") as f:
    writer = csv.writer(f)
    writer.writerow(["ID", "RecordID", "ChunkID", "Stage", "Error", "CreatedAt"])
    for dl in dead_letter_rows:
        writer.writerow([
            dl["id"], dl["record_id"], dl["chunk_id"], dl["stage"], dl["error"], dl["created_at"]
        ])
print(f"⚠️ Exported {len(dead_letter_rows)} dead letter records to {dead_letters_csv_path}")

conn.close()
print(f"\n🎉 All AiVoiceTagger export files successfully refreshed at {now_iso}!")
