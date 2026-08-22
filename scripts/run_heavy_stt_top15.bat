REM @echo off
echo =========================================================================
echo  AiVoiceTagger - High-Precision Re-Transcription for Top Evidence
echo =========================================================================
echo.

echo.
echo Step 2: Running heavy STT model on Top Evidence priority records...  --worker-id pc-alpha-2 --cpu-affinity "6-11" 
cargo run --release -- --config config.yaml --from-csv export/TriagedHighInterest.csv --worker-id pc-alpha-1
cargo run --release -- --config config.yaml --from-csv export/TriagedHighInterest.csv --worker-id pc-alpha-2

echo.

echo.
echo High-precision transcription and evidence document generation complete!
pause
