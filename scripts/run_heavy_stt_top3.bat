REM @echo off
echo =========================================================================
echo  AiVoiceTagger - High-Precision Re-Transcription for Top Evidence
echo =========================================================================
echo.
echo Step 1: Identifying top 3 All-Red-Flags-Up candidate records...
python scripts/generate_top_evidence_docs.py

echo.
echo Step 2: Running heavy STT model on Top 3 priority records...
cargo run --release -- --config config.yaml --from-csv export/Top3_Priority_Records.csv

echo.
echo Step 3: Re-generating beautified court-ready evidence documents...
python scripts/generate_top_evidence_docs.py

echo.
echo High-precision transcription and evidence document generation complete!
pause
