# 🎙️ Voice Biometric Vault Profiles

Drop 1 to 5 clear audio samples (3 to 10 seconds, single speaker, `.wav`, `.mp3`, `.m4a`, `.flac`) into the respective actor directories:

```text
profiles/
├── Antoine/
│   ├── sample_call_01.wav
│   └── sample_meeting_02.wav
├── Catajou/
│   ├── sample_argument_01.wav
│   └── sample_discussion_02.wav
└── Alois/
    └── sample_reading_01.wav
```

### 🚀 Commands to Run Biometric Enrollment & Matching:

```powershell
# 1. Enroll voiceprints and match across all database records
python scripts/enroll_and_identify_speakers.py --db-path "aivoicetagger_state.db"

# 2. Dry-run without modifying database
python scripts/enroll_and_identify_speakers.py --db-path "aivoicetagger_state.db" --dry-run

# 3. Only enroll profiles into the SQLite cache
python scripts/enroll_and_identify_speakers.py --db-path "aivoicetagger_state.db" --enroll-only
```
