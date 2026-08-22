#!/usr/bin/env python3
"""
scripts/run_heavy_stt_top3.py — High-Precision Re-Transcription Runner for Top Evidence

Allows executing the pipeline directly via Python:
python .\scripts\run_heavy_stt_top3.py
"""

import subprocess
import sys

def main():
    print("=========================================================================")
    print(" AiVoiceTagger - High-Precision Re-Transcription for Top Evidence")
    print("=========================================================================\n")

    print("Step 1: Identifying top 3 All-Red-Flags-Up candidate records...")
    subprocess.run([sys.executable, "scripts/generate_top_evidence_docs.py"], check=True)

    print("\nStep 2: Running heavy STT model on Top 3 priority records...")
    subprocess.run(["cargo", "run", "--release", "--", "--config", "config.yaml", "--from-csv", "export/Top3_Priority_Records.csv"], check=True)

    print("\nStep 3: Re-generating beautified court-ready evidence documents...")
    subprocess.run([sys.executable, "scripts/generate_top_evidence_docs.py"], check=True)

    print("\n✅ High-precision transcription & evidence document generation complete!")

if __name__ == "__main__":
    main()
