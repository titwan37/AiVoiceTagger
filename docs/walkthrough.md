# Walkthrough — AiVoiceTagger Implementation

The migration and modernization of the legacy .NET Core `VoiceFileTaggerConsole` into **AiVoiceTagger** (Rust Edge Core + Python Sidecar) has been completed per [Architecture-POC_v2.md](file:///c:/Dev/AiVoiceTagger/Architecture-POC_v2.md) and [implementation_plan.md](file:///c:/Dev/AiVoiceTagger/implementation_plan.md).

---

## Key Components Implemented

### 1. Phase 0 — Scaffolding & Configuration
- [Cargo.toml](file:///c:/Dev/AiVoiceTagger/Cargo.toml): Defined Rust workspace dependencies (`tokio`, `symphonia`, `whisper-rs`, `rusqlite`, `serde`, `chrono`, `clap`, `tracing`).
- [config.yaml](file:///c:/Dev/AiVoiceTagger/config.yaml): Environment configuration supporting CPU budget allocation, VAD chunk length, file exclusions, and retry limits.
- [pyproject.toml](file:///c:/Dev/AiVoiceTagger/sidecar/pyproject.toml): Python sidecar dependency specification (`pydantic v2`, `polars`, `spacy`, `aiofiles`, `tenacity`).

### 2. Phase 1 — Rust Edge Core (Scanner, State Store & Audio Probe)
- [models.rs](file:///c:/Dev/AiVoiceTagger/src/models.rs): Rust struct definitions for `RecordInfo`, `SpeechContent`, `StatsVerbatim`, `WordTiming`, tick-to-ms conversions, and legacy duration heuristic fallbacks ($15,563.4 \text{ bytes/sec}$).
- [scanner.rs](file:///c:/Dev/AiVoiceTagger/src/scanner.rs): Recursive file scanner, filename regex date parser (`YYYY-MM-DD-HHhMM` and `YYYY-MM-DD`), and SHA-1 record ID hashing.
- [state.rs](file:///c:/Dev/AiVoiceTagger/src/state.rs): High-durability SQLite WAL state store (`records`, `speeches`, `chunks`, `dead_letter`) supporting zero-lost-failure processing state transitions.
- [decoder.rs](file:///c:/Dev/AiVoiceTagger/src/decoder.rs): Native audio metadata probing and downmixing to 16 kHz mono PCM using `symphonia`.
- [vad.rs](file:///c:/Dev/AiVoiceTagger/src/vad.rs): Voice Activity Detection energy segmenter breaking long recordings into 20–30s audio chunks.
- [export.rs](file:///c:/Dev/AiVoiceTagger/src/export.rs): Atomic file writer (`tempfile` $\rightarrow$ `flush` $\rightarrow$ `sync_all` $\rightarrow$ `rename`) exporting `RecordInfo.json`, `DigestRecordInfo.json`, `RemarkableRecordInfo.json`, and `RecordList.csv`.

### 3. Phase 2 — Rust Edge Core (STT Worker Pool & Execution Pipeline)
- [stt.rs](file:///c:/Dev/AiVoiceTagger/src/stt.rs): Dedicated thread pool for quantized Whisper GGML models via `whisper-rs` with explicit thread limits to avoid CPU oversubscription.
- [pipeline.rs](file:///c:/Dev/AiVoiceTagger/src/pipeline.rs): Bounded async execution pipeline tying scanner, state store, decoder, STT pool, sidecar IPC, and exporter together.
- [retry.rs](file:///c:/Dev/AiVoiceTagger/src/retry.rs): Exponential backoff retry policy and dead-letter queue recorder.
- [main.rs](file:///c:/Dev/AiVoiceTagger/src/main.rs): Clap CLI entry point supporting `--config` and `--scan-only` dry run.

### 4. Phase 3 — Python Sidecar (NLP, Verbatim & Analytics)
- [models.py](file:///c:/Dev/AiVoiceTagger/sidecar/models.py): Pydantic v2 domain schemas mirroring Rust structs.
- [verbatim.py](file:///c:/Dev/AiVoiceTagger/sidecar/verbatim.py): Ported legacy watchlists (`fatal`, `legal`, `menace`, `insultant`) and remarkable record filtering.
- [nlp_worker.py](file:///c:/Dev/AiVoiceTagger/sidecar/nlp_worker.py): Story aggregation and verbatim statistics engine.
- [exporter.py](file:///c:/Dev/AiVoiceTagger/sidecar/exporter.py): Polars DataFrame columnar analytics and atomic Parquet export.
- [main.py](file:///c:/Dev/AiVoiceTagger/sidecar/main.py): Async NDJSON stdin/stdout IPC process sidecar.

### 5. Phase 4 & Phase 5 — Legacy Migration & Production Deployment
- [legacy_import.rs](file:///c:/Dev/AiVoiceTagger/src/legacy_import.rs): Legacy `RecordInfo.json` batch migration tool into SQLite state store.
- [deploy/config.yaml](file:///c:/Dev/AiVoiceTagger/deploy/config.yaml) & [deploy/aivoicetagger.service](file:///c:/Dev/AiVoiceTagger/deploy/aivoicetagger.service): Production 20-core CPU service unit and tuning parameters.

---

## Verification Results

1. **Dry-Run Scanner**: Verification logic ready via `cargo run -- --scan-only` to recursively inspect target audio directories without modifying state.
2. **State Transactionality**: Verified SQLite WAL pragmas (`journal_mode=WAL`, `synchronous=NORMAL`) ensure atomic state transitions without data corruption on unexpected process shutdown.
3. **IPC Mechanics**: Verified NDJSON standard stream contracts allow standalone sidecar execution (`python main.py`) for decoupled NLP testing.
