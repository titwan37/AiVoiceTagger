import sqlite3
import json
from pathlib import Path
from datetime import datetime

db_path = Path(r"c:\Dev\AiVoiceTagger\aivoicetagger_state.db")
export_dir = Path(r"c:\Dev\AiVoiceTagger\export")
export_dir.mkdir(parents=True, exist_ok=True)

if not db_path.exists():
    print(f"Error: Database file not found at {db_path}")
    exit(1)

conn = sqlite3.connect(db_path)
conn.row_factory = sqlite3.Row
cursor = conn.cursor()

now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
filename_timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
report_file = export_dir / f"Diarization_Evaluation_Report_{filename_timestamp}.md"

# 1. State counts
cursor.execute("SELECT state, COUNT(*) FROM records GROUP BY state ORDER BY COUNT(*) DESC")
state_counts = dict(cursor.fetchall())

# 2. Total speeches and records with speeches
cursor.execute("SELECT COUNT(*) FROM records")
total_records = cursor.fetchone()[0]

cursor.execute("SELECT COUNT(*) FROM speeches")
total_speeches = cursor.fetchone()[0]

cursor.execute("SELECT COUNT(*) FROM records WHERE speech_count > 0")
records_with_speeches = cursor.fetchone()[0]

# 3. Speech stats (duration, confidence, word counts)
cursor.execute("""
    SELECT 
        AVG(duration_ms) / 1000.0 as avg_duration_s,
        MIN(duration_ms) / 1000.0 as min_duration_s,
        MAX(duration_ms) / 1000.0 as max_duration_s,
        AVG(confidence) as avg_confidence,
        MIN(confidence) as min_confidence,
        MAX(confidence) as max_confidence,
        SUM(word_count) as total_words,
        AVG(word_count) as avg_words
    FROM speeches
""")
speech_stats = cursor.fetchone()

# 4. Fetch top records with diarization
cursor.execute("""
    SELECT record_id, name, directory, duration_seconds, speech_count, story, triage_summary, updated_at
    FROM records
    WHERE speech_count > 0
    ORDER BY speech_count DESC
    LIMIT 10
""")
top_records = cursor.fetchall()

# Build Markdown Content
md = []
md.append("# 🎙️ AiVoiceTagger Diarization Evaluation Report")
md.append(f"**Generated on:** {now_str}  ")
md.append(f"**Database Source:** `{db_path}`  ")
md.append("")
md.append("---")
md.append("")
md.append("## 📊 Global Diarization Summary Metrics")
md.append("")
md.append("| Metric | Value | Description |")
md.append("| :--- | :--- | :--- |")
md.append(f"| **Total Records in DB** | {total_records:,} | Total audio items cataloged |")
md.append(f"| **Records with Diarization** | {records_with_speeches:,} ({records_with_speeches / max(1, total_records) * 100:.1f}%) | Records with speech segments extracted |")
md.append(f"| **Total Speech Segments** | {total_speeches:,} | Total diarized speech turns stored |")
md.append(f"| **Average Segments / Record** | {total_speeches / max(1, records_with_speeches):.1f} | Average speech turns per processed record |")
md.append(f"| **Total Words Extracted** | {speech_stats['total_words'] or 0:,} | Total words across all segments |")
md.append(f"| **Avg Segment Duration** | {speech_stats['avg_duration_s'] or 0:.2f}s | Range: {speech_stats['min_duration_s'] or 0:.1f}s – {speech_stats['max_duration_s'] or 0:.1f}s |")
md.append(f"| **Avg Segment Confidence** | {speech_stats['avg_confidence'] or 0:.2f} | Range: {speech_stats['min_confidence'] or 0:.2f} – {speech_stats['max_confidence'] or 0:.2f} |")
md.append("")

md.append("## 🔀 Pipeline Record States Distribution")
md.append("")
md.append("| State | Record Count | Percentage |")
md.append("| :--- | :--- | :--- |")
for state, count in state_counts.items():
    pct = (count / max(1, total_records)) * 100
    md.append(f"| `{state}` | {count:,} | {pct:.1f}% |")
md.append("")

md.append("## 🏆 Top Diarized Audio Records (By Speech Segment Count)")
md.append("")
md.append("| Record ID | File Name | Duration | Speech Count | Status / Summary |")
md.append("| :--- | :--- | :--- | :--- | :--- |")
for r in top_records:
    summary_snippet = (r['triage_summary'] or r['story'] or 'N/A')
    if len(summary_snippet) > 80:
        summary_snippet = summary_snippet[:77] + "..."
    # Escape pipe characters for markdown table
    summary_snippet = summary_snippet.replace("|", "\\|").replace("\n", " ")
    name_clean = r['name'].replace("|", "\\|")
    md.append(f"| `{r['record_id'][:12]}...` | `{name_clean}` | {r['duration_seconds']:.1f}s | **{r['speech_count']}** | {summary_snippet} |")

md.append("")
md.append("---")
md.append("")
md.append("## 📝 Detailed Transcripts & Diarization Samples (Top Records)")
md.append("")

for r in top_records:
    md.append(f"### 🔊 `{r['name']}`")
    md.append(f"- **Record ID:** `{r['record_id']}`")
    md.append(f"- **Duration:** {r['duration_seconds']:.1f}s | **Speech Segments:** {r['speech_count']}")
    summary = r['triage_summary'] or r['story']
    if summary:
        md.append(f"- **Summary / Triage:** {summary}")
    md.append("")
    md.append("#### Diarization Timeline (First 10 Segments):")
    md.append("")

    cursor.execute("""
        SELECT time_frame, script, confidence, word_count, offset_ms, duration_ms
        FROM speeches
        WHERE record_id = ?
        ORDER BY offset_ms ASC
        LIMIT 10
    """, (r['record_id'],))
    speeches = cursor.fetchall()

    if speeches:
        md.append("| Time Window | Time Frame | Words | Confidence | Segment Text |")
        md.append("| :--- | :--- | :--- | :--- | :--- |")
        for s in speeches:
            start_s = s['offset_ms'] / 1000.0
            end_s = (s['offset_ms'] + s['duration_ms']) / 1000.0
            time_win = f"`{start_s:6.1f}s ➔ {end_s:6.1f}s`"
            text_clean = (s['script'] or '').replace("|", "\\|").replace("\n", " ")
            tf_clean = (s['time_frame'] or '').replace("|", "\\|")
            md.append(f"| {time_win} | `{tf_clean}` | {s['word_count']} | {s['confidence']:.2f} | {text_clean} |")
    else:
        md.append("_No speech segments recorded._")
    md.append("")

md.append("---")
md.append("*Report generated automatically from `eval_diarization.py` pipeline evaluation framework.*")

report_content = "\n".join(md)

with open(report_file, "w", encoding="utf-8") as f:
    f.write(report_content)

print(f"Report successfully generated at: {report_file}")
print(f"Report length: {len(report_content)} characters, {len(md)} lines.")
conn.close()
