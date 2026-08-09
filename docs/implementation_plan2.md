# AiVoiceTagger — Implementation Plan

Migrate and modernize the legacy **VoiceFileTaggerConsole** (.NET Core 3.1) into **AiVoiceTagger**, a hybrid Rust + Python system for resilient, CPU-optimized batch audio transcription and NLP tagging, as specified in [Architecture-POC_v2.md](file:///c:/Dev/AiVoiceTagger/Architecture-POC_v2.md).

## Source Material Analyzed

| Repository | Path | Role |
|---|---|---|
| **VoiceFileTaggerConsole** | `C:\Users\titwa\OneDrive\...\VoiceFileTagger\VoiceFileTaggerConsole` | Legacy C# codebase being replaced |
| **AiVoiceBiomarker** | `L:\My Drive\Work\Code\AiVoiceBiomarker` | Python NLP/audio analysis prototypes to reuse |
| **Architecture-POC_v2** | [Architecture-POC_v2.md](file:///c:/Dev/AiVoiceTagger/Architecture-POC_v2.md) | Target architecture (30 sections) |

---

## User Review Required

> [!IMPORTANT]
> **Deployment Strategy**: The plan assumes **Strategy A** (Rust CLI + Python Sidecar) as the default, per section 8.1 of the architecture doc. Confirm this is the desired path over Strategy B (PyO3/Maturin native extension).

> [!IMPORTANT]
> **Primary STT Engine**: The plan defaults to local **Whisper via whisper-rs** (CPU-only, quantized). Azure Speech SDK becomes an optional Python-side cloud fallback.

> [!WARNING]
> **Exposed Azure API Keys**: Legacy `AzureSpeechRec.cs` contains hardcoded Azure Cognitive Services API keys. These should be rotated immediately.

## Open Questions

1. **Target audio directory**: The legacy system targeted `C:\Records\2024_Records\`. Will AiVoiceTagger target the same path, or should it be configurable via CLI/YAML?
2. **Legacy data import**: Do you want AiVoiceTagger to read and migrate existing `RecordInfo.json` files into the new SQLite state store on first run?
3. **Speaker diarization**: The AiVoiceBiomarker project uses `pyannote/speaker-diarization-3.1` for speaker separation. Should this be included in Phase 3 NLP, or is it out of scope for now?
4. **Verbatim watchlists**: The legacy `watchVerbatim.cs` contains French-language watchlists for `fatal`, `legal`, `menace`, and `insultant` categories. Should these be ported as-is, or extended?

---

## Proposed Changes

The implementation is structured into **5 phases**, each delivering a testable, incrementally valuable milestone. Each phase maps directly to sections of `Architecture-POC_v2.md`.

---

### Phase 0 — Project Scaffolding & Configuration

> Sections covered: §1, §7, §25

#### [NEW] [Cargo.toml](file:///c:/Dev/AiVoiceTagger/Cargo.toml)
Initialize Rust binary project with Tokio, symphonia, whisper-rs, serde, rusqlite, chrono, tempfile, sha1, tracing, clap.

#### [NEW] [config.yaml](file:///c:/Dev/AiVoiceTagger/config.yaml)
Production-ready YAML configuration:
- Scanner paths and extension exclusions
- Audio decoder settings and sample rate targets (16 kHz mono PCM)
- STT settings: model path, language (`fr`), worker count, threads per worker
- Python NLP sidecar toggles and concurrency
- Export paths (JSON, CSV, Parquet)
- Retry policies and dead-letter settings

#### [NEW] [pyproject.toml](file:///c:/Dev/AiVoiceTagger/sidecar/pyproject.toml)
Python sidecar project setup with `pydantic>=2.0`, `polars>=1.0`, `aiofiles>=24.0`, `tenacity>=8.0`, `spacy>=3.7`.

#### [NEW] `c:\Dev\AiVoiceTagger\models\`
Directory for quantized Whisper GGML model files (e.g., `ggml-small-q5_0.bin`).

---

### Phase 1 — Rust Edge Core: Scanner + State Store + Audio Probing

> Sections covered: §2, §4, §5.1–5.2, §6, §8, §9, §10, §17, §18, §19

#### [NEW] `src/config.rs`
YAML configuration loader.

#### [NEW] `src/models.rs`
Domain models ported from legacy C# (`RecordInfo`, `SpeechContent`, `StatsVerbatim`).
Handles tick conversions ($1 \text{ ms} = 10,000 \text{ ticks}$), date fallbacks, and UTF-8 French string handling.

#### [NEW] `src/scanner.rs`
Recursive file tree scanner with extension filtering, regex filename date parsing, and SHA-1 record ID hashing.

#### [NEW] `src/state.rs`
SQLite WAL transactional state store (`records`, `chunks`, `dead_letter`) tracking state transitions `DISCOVERED → QUEUED → DECODED → TRANSCRIBED → NLP_DONE → EXPORTED → DONE`.

#### [NEW] `src/decoder.rs`
Native audio probing and downmixing to 16 kHz mono PCM via `symphonia` with fallback heuristic duration calculation for corrupt headers.

#### [NEW] `src/vad.rs`
Energy-based Voice Activity Detection & 20–30s audio chunk segmentation with chunk-level state persistence.

#### [NEW] `src/export.rs`
Atomic file writing pattern (`tempfile` → `flush` → `fsync` → atomic `rename`).

---

### Phase 2 — Rust Edge Core: Whisper STT Worker Pool

> Sections covered: §3, §5.3, §7, §11, §12, §14, §4 (thread control)

#### [NEW] `src/stt.rs`
Whisper STT worker pool bound to `whisper-rs` running on dedicated OS threads with strict thread bounds to prevent CPU oversubscription.

#### [NEW] `src/pipeline.rs`
Staged Bounded-Channel Pipeline using `tokio::sync::mpsc` with strict backpressure and memory budget bounds (`MAX_INFLIGHT_AUDIO_MB`).

#### [NEW] `src/retry.rs`
Exponential backoff retry policy and dead-letter log persistence for permanent failures.

#### [NEW] `src/main.rs`
CLI entry point (`clap`), config parsing, pipeline lifecycle management, and signal handling.

---

### Phase 3 — Python Sidecar: NLP, Verbatim & Analytics

> Sections covered: §5.4–5.5, §13, §15, §16, §20

#### [NEW] `sidecar/models.py`
Pydantic v2 domain schemas mirroring Rust structs.

#### [NEW] `sidecar/verbatim.py`
Port of French watchlist verbatim analytics (`fatal`, `legal`, `menace`, `insultant`) and remarkable record filtering.

#### [NEW] `sidecar/nlp_worker.py`
Modular NLP processing pipeline (Rule-based verbatim → spaCy NLP → optional LLM sentiment / Cloud STT).

#### [NEW] `sidecar/main.py`
NDJSON stdin/stdout IPC worker handling requests asynchronously with thread/process pools.

#### [NEW] `sidecar/exporter.py`
Analytics exporter writing `RecordInfo.json`, `DigestRecordInfo.json`, `RemarkableRecordInfo.json`, `RecordList.csv`, and `report.parquet`.

---

### Phase 4 — Integration, Observability & Hardening

> Sections covered: §21, §22, §23, §24, §26, §27, §28, §29

- Add lease-based worker recovery for crashed/stuck tasks.
- Enforce memory limit safeguards during heavy batch runs.
- Add structured JSON logging and metrics reporting (`tracing`).
- Implement sidecar supervisor with auto-restart and unacknowledged message replay.

---

### Phase 5 — Legacy Migration & Production Deployment

> Sections covered: §6, §25, §30

#### [NEW] `src/legacy_import.rs`
Migration utility to ingest legacy `RecordInfo.json` data into the SQLite state store.

#### [NEW] `deploy/config.yaml` & `deploy/aivoicetagger.service`
Production configuration pre-tuned for a 20-core CPU system (4 STT workers × 3 threads, 3 decode workers, 3 NLP sidecar workers).

---

## Verification Plan

### Automated Tests
- `cargo test` for Rust scanner, state store, models, and pipeline backpressure.
- `pytest` for Python sidecar models, verbatim matching, and NDJSON IPC.

### Manual Verification
- Dry-run directory scanner on test audio.
- Validate transcript quality and verbatim match counts.
- Test crash recovery by terminating processes during pipeline execution and verifying zero lost tasks on restart.
