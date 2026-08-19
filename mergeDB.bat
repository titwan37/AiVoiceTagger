@echo off
echo ==================================================
echo  🔄 AiVoiceTagger Database Merger ^& Report Sync
echo ==================================================

set /p user_input="Do you want to merge the databases? (y/n): "
if /i "%user_input%"=="y" (
    python scripts/merge_dbs.py --dest "C:\Dev\AiVoiceTagger\aivoicetagger_state.db" --sources "\\SyNAS\Records\PC-unit2\aivoicetagger_state.db"
) else (
    echo ℹ️ Database merge skipped by user.
)

echo.
echo 📊 Refreshing all export report files...
python scripts/export_all.py
echo ⚖️ Generating forensic legal evidence ^& analytics suite...
python scripts/generate_forensic_report.py
