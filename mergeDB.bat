@echo off
echo ==================================================
echo  🔄 AiVoiceTagger Database Merger ^& Report Sync
echo ==================================================
python scripts/merge_dbs.py --dest "C:\Dev\AiVoiceTagger\aivoicetagger_state.db" --sources "\\SyNAS\Records\PC-unit2\aivoicetagger_state.db"

if %ERRORLEVEL% EQU 0 (
    echo.
    echo 📊 Refreshing all export report files...
    python scripts/export_all.py
) else (
    echo ❌ Database merge failed with error code %ERRORLEVEL%.
)
