# AiVoiceTagger — Implementation Plan

Migrate and modernize the legacy **VoiceFileTaggerConsole** (.NET Core 3.1) into **AiVoiceTagger**, a hybrid Rust + Python system for resilient, CPU-optimized batch audio transcription and NLP tagging, as specified in [Architecture-POC_v2.md](file:///l:/My%20Drive/Work/Code/AiVoiceTagger/Architecture-POC_v2.md).

## Source Material Analyzed

| Repository | Path | Role |
|---|---|---|
| **VoiceFileTaggerConsole** | [C:\Users\titwa\OneDrive\...\VoiceFileTagger](file:///C:/Users/titwa/OneDrive/Dokumente/Documents/VS%20Code/VoiceFileTagger/VoiceFileTaggerConsole) | Legacy C# codebase being replaced |
| **AiVoiceBiomarker** | [L:\My Drive\Work\Code\AiVoiceBiomarker](file:///l:/My%20Drive/Work/Code/AiVoiceBiomarker) | Python NLP/audio analysis prototypes to reuse |
| **Architecture-POC_v2** | [Architecture-POC_v2.md](file:///l:/My%20Drive/Work/Code/AiVoiceTagger/Architecture-POC_v2.md) | Target architecture (30 sections) |

---

## User Review Required

> [!IMPORTANT]
> **Deployment Strategy**: The plan assumes **Strategy A** (Rust CLI + Python Sidecar) as the default, per section 8.1 of the architecture doc. Confirm this is the desired path over Strategy B (PyO3/Maturin native extension).

> [!IMPORTANT]
> **Primary STT Engine**: The plan defaults to local **Whisper via whisper-rs** (CPU-only, quantized). Azure Speech SDK becomes an optional Python-side cloud fallback. The legacy Azure keys found in [AzureSpeechRec.cs](file:///C:/Users/titwa/OneDrive/Dokumente/Documents/VS%20Code/VoiceFileTagger/VoiceFileTaggerConsole/Audio/AzureSpeechRec.cs) are hardcoded and should be rotated/revoked.

> [!WARNING]
> **Exposed Azure API Keys**: The legacy `AzureSpeechRec.cs` contains 6 hardcoded Azure Cognitive Services API keys (lines 24-39). These should be **rotated immediately** regardless of migration status.

## Open Questions

1. **Target audio directory**: The legacy system targeted `C:\Records\2024_Records\`. Will AiVoiceTagger target the same path, or should it be configurable via CLI/YAML?
2. **Legacy data import**: Do you want AiVoiceTagger to read and migrate existing `RecordInfo.json` files (4-10 MB each found in the legacy project) into the new SQLite state store on first run?
3. **Speaker diarization**: The [AiVoiceBiomarker](file:///l:/My%20Drive/Work/Code/AiVoiceBiomarker/InterviewAnalyzer.py) project uses `pyannote/speaker-diarization-3.1` for speaker separation. Should this be included in Phase 3 NLP, or is it out of scope for now?
4. **Verbatim watchlists**: The legacy [watchVerbatim.cs](file:///C:/Users/titwa/OneDrive/Dokumente/Documents/VS%20Code/VoiceFileTagger/VoiceFileTaggerConsole/Verbatim/watchVerbatim.cs) contains French-language watchlists for `fatal`, `legal`, `menace`, and `insultant` categories. Should these be ported as-is, or extended?

---

## Proposed Changes

The implementation is structured into **5 phases**, each delivering a testable, incrementally valuable milestone. Each phase maps directly to sections of the Architecture-POC_v2.

---

### Phase 0 — Project Scaffolding & Configuration

> Sections covered: §1, §7, §25

#### [NEW] `l:\My Drive\Work\Code\AiVoiceTagger\Cargo.toml`
Initialize the Rust project with `cargo init`. Core dependencies:
```toml
[dependencies]
tokio = { version = "1", features = ["full"] }
walkdir = "2"
regex = "1"
symphonia = { version = "0.5", features = ["all"] }
whisper-rs = "0.12"
serde = { version = "1", features = ["derive"] }
serde_json = "1"
csv = "1"
rusqlite = { version = "0.31", features = ["bundled"] }
chrono = { version = "0.4", features = ["serde"] }
tempfile = "3"
sha1 = "0.10"
tracing = "0.1"
tracing-subscriber = "0.3"
tokio-util = "0.7"
clap = { version = "4", features = ["derive"] }
```

#### [NEW] `l:\My Drive\Work\Code\AiVoiceTagger\config.yaml`
Production-ready YAML config derived from §25, with all tunables:
- scanner paths, exclusion extensions
- decoder workers, sample rate targets
- STT model path, language, worker count, threads-per-worker
- NLP sidecar toggle, worker count
- export paths (JSON, CSV, Parquet)
- retry policy, dead-letter settings

#### [NEW] `l:\My Drive\Work\Code\AiVoiceTagger\sidecar/pyproject.toml`
Python sidecar project with dependencies:
```
pydantic>=2.0
polars>=1.0
aiofiles>=24.0
tenacity>=8.0
spacy>=3.7
```

#### [NEW] `l:\My Drive\Work\Code\AiVoiceTagger\models/` (directory)
Location for Whisper GGML model files (`ggml-small-q5_0.bin`).

---

### Phase 1 — Rust Edge Core: Scanner + State Store + Audio Probing

> Sections covered: §2, §4, §5.1–5.2, §6, §8 (state design), §9, §10, §17, §18, §19

This phase delivers a Rust binary that can scan directories, parse filenames, probe audio metadata, and persist state — without any STT or NLP yet.

#### [NEW] `src/config.rs`
YAML config loader via `serde` + `serde_yaml`. Maps to the `config.yaml` schema.

#### [NEW] `src/models.rs`
Domain models ported from legacy C#:

| Legacy C# | New Rust Struct | Key Fields |
|---|---|---|
| [RecordInfo.cs](file:///C:/Users/titwa/OneDrive/Dokumente/Documents/VS%20Code/VoiceFileTagger/VoiceFileTaggerConsole/File/RecordInfo.cs) | `RecordInfo` | `record_id`, `name`, `directory`, `date_record_day: Option<DateTime<Utc>>`, `date_last_write`, `length`, `size_human`, `duration`, `speech_count`, `story`, `stats_verbatim`, `state` |
| [SpeechContent.cs](file:///C:/Users/titwa/OneDrive/Dokumente/Documents/VS%20Code/VoiceFileTagger/VoiceFileTaggerConsole/Audio/SpeechContent.cs) | `SpeechContent` | `time_frame`, `script`, `confidence`, `word_count`, `offset_ms`, `duration_ms`, `words: Option<Vec<WordTiming>>` |
| [watchVerbatim.cs](file:///C:/Users/titwa/OneDrive/Dokumente/Documents/VS%20Code/VoiceFileTagger/VoiceFileTaggerConsole/Verbatim/watchVerbatim.cs) | `StatsVerbatim` | `count_lethal`, `count_legal`, `count_menaces`, `count_insultes`, `occurrences: Vec<String>` |

**Critical legacy edge cases to handle** (from §6):
- Filename regex with fallback `1888-12-01` sentinel date → use `Option<DateTime>` + `LastWriteTime` fallback
- Duration heuristic: `seconds = round(file_size / 15563.4)` as fallback when `symphonia` probe fails
- Tick conversions: `milliseconds = ticks / 10_000`
- UTF-8 French output: `serde_json` handles this natively

#### [NEW] `src/scanner.rs`
Port of [Scanner.cs](file:///C:/Users/titwa/OneDrive/Dokumente/Documents/VS%20Code/VoiceFileTagger/VoiceFileTaggerConsole/File/Scanner.cs):
- Recursive directory walk via `walkdir`
- Extension exclusion filter (`.xlsx`, `.csv`, `.json`)
- Filename date regex parsing (port the two-tier regex from [RecordInfo.cs L101-163](file:///C:/Users/titwa/OneDrive/Dokumente/Documents/VS%20Code/VoiceFileTagger/VoiceFileTaggerConsole/File/RecordInfo.cs#L101-L163))
- Stable `record_id` generation: `SHA-1(relative_path + file_size + last_write_time)`

#### [NEW] `src/state.rs`
SQLite WAL state store (from §8):
- `records` table, `chunks` table, `dead_letter` table
- State machine: `DISCOVERED → QUEUED → DECODED → TRANSCRIBED → NLP_DONE → EXPORTED → DONE`
- Pragmas: `journal_mode=WAL`, `synchronous=NORMAL`, `busy_timeout=5000`
- Idempotency checks (§9): skip records already `DONE`

#### [NEW] `src/decoder.rs`
Audio probing and decoding via `symphonia`:
- Probe duration, sample rate, channels
- Decode → downmix to mono → resample to 16 kHz
- Fallback heuristic for corrupt headers
- Mark fallback records as `degraded`

#### [NEW] `src/vad.rs`
Voice Activity Detection and chunking (§6):
- Energy-based VAD segmentation
- 20–30 second chunk splitting
- Chunk ID scheme: `record_id#start_ms-end_ms`

#### [NEW] `src/export.rs`
Atomic file writing (§10):
- `tempfile` → write → `sync_all` → `rename`
- JSON export with `ensure_ascii=false` equivalent (serde_json default)
- CSV export via `csv` crate

---

### Phase 2 — Rust Edge Core: Whisper STT Worker Pool

> Sections covered: §3, §5.3, §7 (pipeline), §11, §12, §14, §4 (thread control)

#### [NEW] `src/stt.rs`
Whisper STT integration:
- `whisper-rs` bindings to `whisper.cpp`
- Dedicated blocking thread pool (NOT on Tokio async runtime)
- Configurable: `workers`, `threads_per_worker`, `model_path`, `language`
- Quantized model support: `q5_0`, `q8_0`
- Fixed language (`fr`) to avoid detection overhead
- Token timestamps only when `StatsVerbatim` requires word-level timing

#### [NEW] `src/pipeline.rs`
Bounded channel pipeline (§7):
```
Scanner → State/WAL → Decoder → VAD/Chunk → STT Pool → [NLP Sidecar] → Export
```
- `tokio::sync::mpsc::channel(capacity)` for all stages
- Backpressure rules: STT full → decoder pauses → scanner pauses
- `MAX_INFLIGHT_AUDIO_MB` and `MAX_INFLIGHT_CHUNKS` budgets
- `CancellationToken` for graceful shutdown (§24)

#### [NEW] `src/retry.rs`
Retry + dead-letter logic (§11):
- Exponential backoff with jitter
- Max 5 attempts: immediate → 1s → 5s → 30s → 2min
- Transient vs. permanent error classification
- Dead-letter storage with full context

#### [MODIFY] `src/main.rs`
Wire everything together:
- `clap` CLI argument parsing
- Config loading
- Pipeline orchestration
- Graceful shutdown on `Ctrl+C` / `SIGTERM`
- Environment variable overrides: `OMP_NUM_THREADS=1`, `OPENBLAS_NUM_THREADS=1`

---

### Phase 3 — Python Sidecar: NLP, Verbatim & Analytics

> Sections covered: §5.4–5.5, §13, §15, §16, §20

#### [NEW] `sidecar/models.py`
Pydantic v2 models mirroring Rust structs:
- `RecordInfo(BaseModel)`
- `SpeechContent(BaseModel)`
- `StatsVerbatim(BaseModel)`
- NDJSON message schemas (§13): `NlpRequest`, `NlpResponse`

#### [NEW] `sidecar/verbatim.py`
Port of [watchVerbatim.cs](file:///C:/Users/titwa/OneDrive/Dokumente/Documents/VS%20Code/VoiceFileTagger/VoiceFileTaggerConsole/Verbatim/watchVerbatim.cs):
- French watchlists: `fatal_verbatim`, `legal_verbatim`, `menace_verbatim`, `insultant_verbatim`
- Case-insensitive matching
- `StatsVerbatim.calculate()` method
- `is_remarkable()` filter for digest/remarkable record extraction

#### [NEW] `sidecar/nlp_worker.py`
NLP enrichment pipeline (§16 hierarchy):
1. Rule-based verbatim/keyword statistics (default, always on)
2. Optional spaCy sentence segmentation and entity extraction
3. Optional local LLM sentiment via Ollama (disabled by default)
4. Optional cloud fallback (Azure Speech SDK, budget-capped)

#### [NEW] `sidecar/main.py`
NDJSON stdin/stdout IPC sidecar:
- Reads `NlpRequest` messages from stdin
- Runs NLP pipeline
- Writes `NlpResponse` with ACK to stdout
- `asyncio` event loop + `ProcessPoolExecutor` for CPU-bound NLP
- `tenacity` retries for transient errors

#### [NEW] `sidecar/exporter.py`
Analytics export (§20):
- `RecordInfo.json` — full operational state
- `DigestRecordInfo.json` — speeches stripped (legacy `Leanify()`)
- `RemarkableRecordInfo.json` — only records where `is_remarkable() == true`
- `RecordList.csv` — human-readable spreadsheet
- `report.parquet` — Polars columnar analytics (optional)
- All writes atomic: `temp file → os.replace()`

---

### Phase 4 — Integration, Observability & Hardening

> Sections covered: §21, §22, §23, §24, §26, §27, §28, §29

#### [MODIFY] `src/pipeline.rs`
- Add lease-based worker recovery (§12)
- Network storage hardening: read-only opens, read timeouts, sequential batching (§21)
- Memory budget enforcement: stop scanner when `MAX_INFLIGHT_AUDIO_MB` exceeded (§22)

#### [NEW] `src/metrics.rs`
Observability (§23):
- Structured JSON logging via `tracing`
- Metrics: `files_discovered_total`, `chunks_completed_total`, `stt_queue_depth`, `stt_real_time_factor`, `dead_letter_count`, etc.
- Periodic `status.json` and `health.json` writes

#### [NEW] `src/supervisor.rs`
Supervision (§24):
- Graceful shutdown sequence: stop scanner → drain queues → flush state → shutdown sidecar
- Python sidecar lifecycle management: spawn, health-check, restart on crash
- Unacknowledged message replay after sidecar restart

---

### Phase 5 — Legacy Migration & Production Deployment

> Sections covered: §6 (edge cases), §25, §30

#### [NEW] `src/legacy_import.rs`
Legacy `RecordInfo.json` importer:
- Read existing JSON files (4-10 MB) from `C:\Records\`
- Map legacy fields to new `RecordInfo` struct
- Convert `TimeSpan.Ticks` → `Duration`
- Import speeches and stories into SQLite state store
- Mark imported records as `DONE` to avoid re-processing

#### [NEW] `deploy/config.yaml`
Production configuration for 20-core CPU node (§25):
```yaml
stt:
  workers: 4
  threads_per_worker: 3
  model: models/ggml-small-q5_0.bin
  language: fr
decoder:
  workers: 3
nlp:
  workers: 3
  enable_llm: false
```

#### [NEW] `deploy/aivoicetagger.service` (or Windows Service wrapper)
Systemd/Windows service definition with restart policies, memory limits, and watchdog.

---

## Project Structure Summary

```
l:\My Drive\Work\Code\AiVoiceTagger\
├── Cargo.toml
├── config.yaml
├── src/
│   ├── main.rs
│   ├── config.rs
│   ├── models.rs
│   ├── scanner.rs
│   ├── state.rs
│   ├── decoder.rs
│   ├── vad.rs
│   ├── stt.rs
│   ├── pipeline.rs
│   ├── retry.rs
│   ├── export.rs
│   ├── metrics.rs
│   ├── supervisor.rs
│   └── legacy_import.rs
├── sidecar/
│   ├── pyproject.toml
│   ├── main.py
│   ├── models.py
│   ├── verbatim.py
│   ├── nlp_worker.py
│   └── exporter.py
├── models/
│   └── ggml-small-q5_0.bin
├── deploy/
│   ├── config.yaml
│   └── aivoicetagger.service
├── Architecture-POC.md
└── Architecture-POC_v2.md
```

---

## Verification Plan

### Automated Tests

Each phase includes targeted tests:

```bash
# Phase 1: Scanner + State Store
cargo test --lib scanner -- --nocapture
cargo test --lib state -- --nocapture

# Phase 2: Full pipeline with test audio
cargo test --lib pipeline -- --nocapture
cargo run -- --config test_config.yaml --scan-only  # dry run

# Phase 3: Python sidecar
cd sidecar && python -m pytest tests/ -v

# Phase 4: Robustness (§29)
# Kill-9 during each pipeline stage
# Corrupt audio files, zero-byte files
# Network share disconnect simulation
# Restart-after-crash verification
```

### Manual Verification

1. **Phase 1**: Run scanner against `C:\Records\2024_Records\` — verify all audio files are discovered and SQLite state is populated correctly.
2. **Phase 2**: Process 10 test audio files end-to-end — verify transcripts match expected French text.
3. **Phase 3**: Verify `StatsVerbatim` output matches legacy C# output for the same input files.
4. **Phase 5**: Import legacy `RecordInfo.json` — verify record counts and speech data are preserved.

### Success Criteria (§29)

- No file is silently lost
- No duplicate final record is produced
- Temporary files are cleaned
- State store remains consistent after crash
- Dead-letter contains all permanent failures
- Final JSON/CSV/Parquet exports are valid UTF-8
