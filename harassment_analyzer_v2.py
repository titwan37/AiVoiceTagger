# ! pip install faster-whisper pandas matplotlib tqdm

import os
import re
from pathlib import Path
from datetime import datetime
import pandas as pd
import matplotlib.pyplot as plt
from faster_whisper import WhisperModel
from tqdm import tqdm
import ollama

# Set default Ollama environment variables
os.environ["OLLAMA_KEEP_ALIVE"] = "0s"
os.environ["OLLAMA_NUM_PARALLEL"] = "1"

# ==========================================
# CONFIGURATION
# ==========================================
AUDIO_DIR = r"\\SyNAS\Records"

# Audio extensions to look for
AUDIO_EXTENSIONS = [".wav", ".mp3", ".m4a", ".aac", ".flac", ".ogg", ".m4r"]

# French targets to monitor (regex patterns)
KEY_TERMS = {
    "Dégage": r"\bdégage[sz]?\b",
    "Ferme ta gueule": r"\bferme\s+(ta|votre)\s+gueule\b",
    "Connard / Conne": r"\bconnard[s]?\b|\bconne[s]?\b|\bcon\b",
    "Salope / Salaud": r"\bsalope[s]?\b|\bsalaud[s]?\b",
    "Fous le camp": r"\bfous\s+le\s+camp\b",
    "Ta gueule": r"\bta\s+gueule\b",
    "Ferme-la": r"\bferme[- ]la\b"
}

# Whisper Model Configuration
MODEL_SIZE = "medium"  # "small", "medium", or "large-v3"
DEVICE = "cpu"        # Change to "cuda" if using NVIDIA GPU

# Ollama LLM Configuration
USE_LLM_VERIFICATION = True
OLLAMA_MODEL = "llama3.2:1b"  # Alternative: "mistral" or "gemma2"

# Output Files
OUTPUT_CSV = "harassment_evidence_report.csv"
OUTPUT_EXCEL = "harassment_summary_report.xlsx"
OUTPUT_CHART = "incidents_over_time.png"

# ==========================================
# FILENAME TIMESTAMP PARSER
# ==========================================
DATE_PATTERNS = [
    # YYYY-MM-DD_HHMMSS or YYYY-MM-DD_HH-MM-SS
    (r"(\d{4}[-_]\d{2}[-_]\d{2})[-_](\d{2}[-_]?\d{2}[-_]?\d{2})", "%Y-%m-%d_%H%M%S"),
    # YYYYMMDD_HHMMSS
    (r"(\d{8})_(\d{6})", "%Y%m%d_%H%M%S"),
    # YYYY-MM-DD
    (r"(\d{4}-\d{2}-\d{2})", "%Y-%m-%d"),
    # YYYYMMDD
    (r"(\d{8})", "%Y%m%d")
]

def extract_file_date(file_path: Path) -> datetime:
    """
    Parses date and time from filename using known regex patterns.
    Falls back to file modification time if no match is found.
    """
    filename = file_path.name

    # Try matching common date/time patterns in filename
    for pattern, date_fmt in DATE_PATTERNS:
        match = re.search(pattern, filename)
        if match:
            clean_str = "_".join(match.groups()).replace("-", "").replace("_", "")
            # Normalize target format for strptime
            if len(clean_str) == 14:  # YYYYMMDDHHMMSS
                try:
                    return datetime.strptime(clean_str, "%Y%m%d%H%M%S")
                except ValueError:
                    pass
            elif len(clean_str) == 8:  # YYYYMMDD
                try:
                    return datetime.strptime(clean_str, "%Y%m%d")
                except ValueError:
                    pass

    # Fallback: File system modification time
    try:
        mtime = os.path.getmtime(file_path)
        return datetime.fromtimestamp(mtime)
    except Exception:
        return datetime.now()

# ==========================================
# LLM CONTEXT VERIFIER (OLLAMA)
# ==========================================
def verify_harassment_with_llm(excerpt: str, term: str) -> dict:
    """
    Queries local Ollama LLM to assess if the transcript segment constitutes genuine hostility/harassment.
    Returns structured assessment: Is_Harassment (bool) and Explanation.
    """
    prompt = f"""Vous êtes un expert juridique d'analyse de données d'incidents.
Analyse cet extrait de transcription audio où le mot/expression suspect "{term}" a été détecté.

Extrait: "{excerpt}"

Réponds STRICTEMENT au format suivant (sans texte superflu) :
HARASSMENT: [OUI/NON]
CONFIDENCE: [ELEVE/MOYEN/FAIBLE]
REASON: [Explication synthétique en 1 phrase en français]
"""

    try:
        response = ollama.chat(
            model=OLLAMA_MODEL,
            messages=[{"role": "user", "content": prompt}],
            options={
                "num_thread": 2,       # Restrict Ollama to 2 CPU threads (prevents 100% CPU lock)
                "num_ctx": 1024,       # Limit context window to 1024 tokens (slashes RAM usage)
                "temperature": 0.1
            },
            keep_alive="0s"            # Unload model from RAM immediately after generating response
        )
        reply = response["message"]["content"].strip()

        is_harassment = "HARASSMENT: OUI" in reply.upper()
        
        reason_match = re.search(r"REASON:\s*(.*)", reply, re.IGNORECASE)
        reason = reason_match.group(1).strip() if reason_match else reply

        return {
            "Verified": is_harassment,
            "LLM_Assessment": "Agressif / Hostile" if is_harassment else "Non-hostile / Faux positif",
            "LLM_Reason": reason
        }

    except Exception as e:
        return {
            "Verified": True,
            "LLM_Assessment": "Erreur LLM",
            "LLM_Reason": f"Ollama indisponible: {str(e)}"
        }

# ==========================================
# TRANSCRIPT MATCHING
# ==========================================
def analyze_transcript(text: str) -> dict:
    """Counts occurrences of monitored key terms in text using regex."""
    counts = {}
    text_lower = text.lower()
    for label, pattern in KEY_TERMS.items():
        matches = re.findall(pattern, text_lower)
        if matches:
            counts[label] = len(matches)
    return counts

# ==========================================
# MAIN ENGINE
# ==========================================
def main():
    print(f"[*] Initialisation du modèle Whisper ({MODEL_SIZE}) sur {DEVICE}...")
    model = WhisperModel(MODEL_SIZE, device=DEVICE, compute_type="int8")

    records_path = Path(AUDIO_DIR)
    if not records_path.exists():
        print(f"[!] Erreur: Le chemin '{AUDIO_DIR}' est inaccessible. Vérifiez la connexion réseau.")
        return

    # Find audio files
    audio_files = []
    for ext in AUDIO_EXTENSIONS:
        audio_files.extend(records_path.rglob(f"*{ext}"))
        audio_files.extend(records_path.rglob(f"*{ext.upper()}"))

    print(f"[*] {len(audio_files)} fichiers audio trouvés dans {AUDIO_DIR}")

    findings = []

    for file in tqdm(audio_files, desc="Analyse des fichiers audio"):
        file_date = extract_file_date(file)
        
        try:
            segments, _ = model.transcribe(str(file), language="fr", beam_size=5)
            
            for segment in segments:
                text = segment.text.strip()
                seg_counts = analyze_transcript(text)
                
                if seg_counts:
                    timestamp_start = f"{int(segment.start // 60):02d}:{int(segment.start % 60):02d}"
                    timestamp_end = f"{int(segment.end // 60):02d}:{int(segment.end % 60):02d}"
                    
                    for term, count in seg_counts.items():
                        # Optional LLM verification step
                        if USE_LLM_VERIFICATION:
                            llm_res = verify_harassment_with_llm(text, term)
                        else:
                            llm_res = {"Verified": True, "LLM_Assessment": "N/A", "LLM_Reason": "LLM Désactivé"}

                        findings.append({
                            "Date": file_date.strftime("%Y-%m-%d"),
                            "Year_Week": file_date.strftime("%Y-W%W"),
                            "Time": file_date.strftime("%H:%M:%S"),
                            "File_Name": file.name,
                            "File_Path": str(file),
                            "Timestamp_In_Audio": f"{timestamp_start} - {timestamp_end}",
                            "Detected_Term": term,
                            "Count": count,
                            "Transcript_Excerpt": text,
                            "LLM_Verified": llm_res["Verified"],
                            "LLM_Assessment": llm_res["LLM_Assessment"],
                            "LLM_Explanation": llm_res["LLM_Reason"]
                        })

        except Exception as e:
            print(f"\n[!] Erreur lors du traitement de {file.name}: {e}")

    # ==========================================
    # REPORTING & AGGREGATION
    # ==========================================
    if not findings:
        print("[*] Scan terminé. Aucune insulte ou expression ciblée n'a été détectée.")
        return

    df = pd.DataFrame(findings)
    df.to_csv(OUTPUT_CSV, index=False, encoding="utf-8-sig")
    print(f"\n[+] Rapport détaillé sauvegardé : {OUTPUT_CSV}")

    # Filter for verified incidents if LLM is active
    verified_df = df[df["LLM_Verified"] == True] if USE_LLM_VERIFICATION else df

    daily_summary = verified_df.groupby(["Date", "Detected_Term"])["Count"].sum().unstack(fill_value=0)
    weekly_summary = verified_df.groupby(["Year_Week", "Detected_Term"])["Count"].sum().unstack(fill_value=0)

    print("\n=== INCIDENTS AVÉRÉS PAR JOUR ===")
    print(daily_summary)

    print("\n=== INCIDENTS AVÉRÉS PAR SEMAINE ===")
    print(weekly_summary)

    # Export Excel multi-tab report
    with pd.ExcelWriter(OUTPUT_EXCEL) as writer:
        df.to_excel(writer, sheet_name="Tous les Incidents", index=False)
        verified_df.to_excel(writer, sheet_name="Incidents Confirmés LLM", index=False)
        daily_summary.to_excel(writer, sheet_name="Synthese Quotidienne")
        weekly_summary.to_excel(writer, sheet_name="Synthese Hebdomadaire")
        
    print(f"[+] Rapport Excel multi-onglets créé : {OUTPUT_EXCEL}")

    # Plot trend timeline
    plot_timeline(verified_df)

def plot_timeline(df: pd.DataFrame):
    """Plots daily verified incident counts."""
    if df.empty:
        return
    daily_total = df.groupby("Date")["Count"].sum()
    
    plt.figure(figsize=(10, 5))
    daily_total.plot(kind="bar", color="#d9534f")
    plt.title("Évolution du Nombre d'Incidents Confirmés par Jour")
    plt.xlabel("Date")
    plt.ylabel("Nombre d'Occurrences")
    plt.xticks(rotation=45)
    plt.tight_layout()
    plt.savefig(OUTPUT_CHART)
    print(f"[+] Graphique synthétique généré : {OUTPUT_CHART}")

if __name__ == "__main__":
    main()