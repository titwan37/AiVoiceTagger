import sqlite3

db_path = r"c:\Dev\AiVoiceTagger\aivoicetagger_state.db"
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

target_ids = [
    "rec_0641a5f442d0dd96dcd6e561b58c7c9fae4543f8", # KTA_MenaceViolenceEnReunion
    "rec_8e6e631d5dd1a1f3b8a0ca4587df5d78a2441b3c", # KT_AccusationFortuite
    "rec_241122161833_expropriation", # record expropriation
    "rec_2510291652_action_justice",
]

print("=== DETAILED SPEECH EXTRACTS ===")
cursor.execute("""
    SELECT r.name, r.directory, s.time_frame, s.script, s.confidence
    FROM speeches s
    JOIN records r ON s.record_id = r.record_id
    WHERE LOWER(s.script) LIKE '%dégage%'
       OR LOWER(s.script) LIKE '%expropriation%'
       OR LOWER(s.script) LIKE '%dormir dehors%'
       OR LOWER(s.script) LIKE '%quitter%'
       OR LOWER(s.script) LIKE '%menace%'
       OR LOWER(s.script) LIKE '%mon toit%'
    ORDER BY r.name, s.offset_ms
""")

rows = cursor.fetchall()
for name, directory, time_frame, script, conf in rows:
    print(f"\nFILE: {name}")
    print(f"PATH: {directory}\\{name}")
    print(f"TIME: [{time_frame}] (Confidence: {conf:.2f})")
    print(f"TEXT: {script}")
