# AiVoiceTagger: Modern Hybrid Architecture & Migration Specification

This document presents a comprehensive, high-performance hybrid architecture for **AiVoiceTagger** (migrating and modernizing the legacy `.NET Core` `VoiceFileTagger` solution).

By decoupling low-overhead edge audio/file operations (**Rust**) from high-level NLP, data analytics, and AI modeling (**Python**), the architecture delivers maximum execution speed, low memory overhead, and rapid AI feature iteration.

---

## 1. System Scope & Core Objective

**AiVoiceTagger** automates batch audio processing across local and network file storage. Its core responsibilities include:

* **Directory Scanning & State Management**: Recursively traversing record directories, maintaining incremental state (`RecordInfo.json`), and avoiding duplicate work.
* **Metadata & Probing**: Extracting timestamps from filenames via regex and probing audio stream metadata (duration, sample rate, bit depth).
* **Transcription & STT**: Performing Speech-to-Text via local Whisper models (`whisper.cpp`/`whisper-rs`) or cloud engines (Azure Speech API).
* **Verbatim & NLP Tagging**: Extracting word-level timing metrics, key phrase statistics, and AI/LLM-driven sentiment & verbatim insights.
* **Persistence & Analytics**: Exporting aggregated reports to JSON, CSV, and high-performance columnar formats (Polars/Parquet).

---

## 2. Architecture Blueprint: The Decoupled Core

The system separates heavy CPU/IO edge tasks from dynamic data orchestration:

```
┌─────────────────────────────────────────────────────────────────┐
│                       RUST EDGE CORE                            │
│  • Fast directory tree scanning & Regex filename parsing        │
│  • Native audio loading, format decoding & duration probing     │
│  • Embedded local Speech-to-Text (whisper.cpp / whisper-rs)     │
│  • Concurrent state caching & JSON/CSV I/O                      │
└────────────────────────────────┬────────────────────────────────┘
                                 │ Clean Interface (JSON IPC / FFI)
┌────────────────────────────────▼────────────────────────────────┐
│                    PYTHON AI & DATA PIPELINE                    │
│  • Complex NLP, verbatim parsing & LLM sentiment tagging        │
│  • Post-processing, aggregation & custom statistical metrics    │
│  • Polars / Pandas data frame export & visualization            │
│  • Cloud STT fallbacks (Azure Speech SDK / OpenAI API)          │
└─────────────────────────────────────────────────────────────────┘
```

---

## 3. Integration Strategies

Depending on deployment requirements, two integration patterns are supported:

### Strategy A: Polyglot CLI (Rust CLI + Python Sidecar)

* **Mechanism**: The main executable is compiled in Rust. For heavy NLP or custom python scripts, Rust streams structured JSON over standard input/output (`stdin`/`stdout`) IPC or invokes python via standard subprocess.
* **Pros**: Single zero-dependency binary for basic edge tagging; python dependency is optional and isolated.
* **Best for**: Headless servers, edge devices, and lightweight local scanning.

### Strategy B: Native Python C-Extension (`pyo3` / `maturin`)

* **Mechanism**: Rust core is compiled as a shared library (`.so`/`.pyd`) via **PyO3** and **Maturin**. Python imports `import voice_tagger_core` and invokes native Rust functions directly.
* **Pros**: Entire top-level orchestration remains in Python for rapid developer iteration, while performance bottlenecks execute at full native hardware speed.
* **Best for**: Data science environments, Jupyter notebooks, and advanced AI workflow pipelines.

---

## 4. Domain & Data Model Mapping

The legacy C# domain model (`RecordInfo`, `RecordInfoBag`, `SpeechContent`) maps cleanly across both layers:

```
+-----------------------------------------------------------------------------------+
| C# Legacy Model      | Rust Edge Model (`serde`)   | Python Model (`Pydantic v2`) |
+----------------------+-----------------------------+------------------------------+
| RecordInfo           | struct RecordInfo           | class RecordInfo(BaseModel)  |
| RecordInfoBag        | Vec<RecordInfo> / Mutex     | List[RecordInfo] / Polars DF |
| SpeechContent        | struct SpeechContent        | class SpeechContent(BaseModel)|
| StatsVerbatim        | struct StatsVerbatim        | class StatsVerbatim(BaseModel)|
+-----------------------------------------------------------------------------------+
```

### Key Field Mappings

* **`DateRecordDay` / `DateLastWrite`**: Mapped from C# `DateTime` to Rust `chrono::DateTime<Utc>` and Python `datetime.datetime`.
* **`Duration` / `TimeSpan`**: Converted from C# `TimeSpan.Ticks` (100ns units) to Rust `std::time::Duration` / `chrono::Duration` and Python `datetime.timedelta`.
* **`cSpeeches` / `Speeches`**: Managed as an ordered list of transcribed segments containing script text, confidence scores, offsets, and word-level timestamps.

---

## 5. Pipeline & Feature Allocation

| Pipeline Stage | Layer | Technology Stack | Description & Responsibilities |
| :--- | :--- | :--- | :--- |
| **1. File System Scan** | Rust Edge | `walkdir`, `regex` | Recursively scans directories, excluding `.xlsx`, `.csv`, `.json`. Parses date patterns (e.g., `YYYY-MM-DD-HHhMM`) from filenames. |
| **2. Audio Decoding & Probing** | Rust Edge | `symphonia` / `rodio` | Extracts precise audio durations, sample rates, and audio channel info natively without external dependencies. |
| **3. Speech Recognition (STT)** | Rust / Python | `whisper-rs` OR `azure-cognitiveservices-speech` | Local STT via quantized Whisper C++ bindings in Rust, OR asynchronous cloud transcription via Python Azure Speech SDK. |
| **4. Story & Verbatim Generation** | Python AI | `pydantic`, `re`, `spaCy` | Cleans up speech output, structures continuous stories, extracts verbatim keyword frequency, and performs LLM sentiment tagging. |
| **5. Aggregation & Export** | Python Data | `polars`, `aiofiles` | Fast columnar processing, digest/remarkable record filtering, and thread-safe export to `RecordInfo.json` and `RecordList.csv`. |

---

## 6. Legacy Edge Cases & Technical Lessons Learned

When migrating logic from the C# `VoiceFileTaggerConsole` implementation, the following edge cases must be strictly handled:

1. **Tick Conversions**:
    * C# `TimeSpan.Ticks` represents 100-nanosecond units ($1\text{ ms} = 10,000\text{ ticks}$).
    * Python/Rust implementations must explicitly convert ticks: $\text{milliseconds} = \text{ticks} / 10,000$.
2. **Audio Duration Heuristic Fallback**:
    * Legacy C# used an empirical file-size formula when shell media duration failed: $\text{seconds} = \text{round}(\text{file\_size\_bytes} / 15563.4)$.
    * Modern solution: Primary probing via Rust `symphonia`; fallback formula retained only for corrupt or unrecognized header files.
3. **Filename Regex Fallback**:
    * Legacy C# regex parsed filenames with optional time parts (`YYYY-MM-DD` or `YYYY-MM-DD-HH-MM-SS`). If regex matching failed completely, dates defaulted to `1888-12-01` to prevent `NullReferenceException`.
    * Modern solution: Optional datetime fields in Pydantic/Rust with fallback to `LastWriteTime` from filesystem metadata.
4. **Unicode & Escaping**:
    * Legacy JSON serialization configured `JavaScriptEncoder.UnsafeRelaxedJsonEscaping` to preserve French characters (e.g., `é`, `è`, `à`).
    * Python's `json.dump(..., ensure_ascii=False)` and Rust's `serde_json` natively output non-escaped UTF-8.
5. **Thread Safety & Retries**:
    * Legacy C# used `lock (RecordInfoBag.Locks)` and `Thread.Sleep(1000)` retry loops during file writes.
    * Modern solution: Asynchronous non-blocking atomic file writes (`aiofiles` + temporary file renaming) or `tenacity` retry decorators.

---

## 7. Technology Stack Mapping Matrix

| Legacy C# (.NET Core 3.1) | Modern Rust Edge Core | Modern Python AI Core |
| :--- | :--- | :--- |
| **`Program.cs` / TPL** | `tokio` async runtime | `asyncio` / `ThreadPoolExecutor` |
| **`Microsoft.CognitiveServices.Speech`** | `whisper-rs` (Local) | `azure-cognitiveservices-speech` (Cloud) |
| **`NAudio` / Shell API** | `symphonia` / `rodio` | `mutagen` / `pydub` |
| **`RecordInfo` / Classes** | `struct` + `serde` | `pydantic.BaseModel` |
| **`ConcurrentBag<T>`** | `Arc<Mutex<Vec<T>>>` / channels | `asyncio.Queue` / `list` + lock |
| **`System.Text.Json`** | `serde_json` | `pydantic` / `json` |
| **`System.Text.RegularExpressions`** | `regex` crate | `re` module |
| **CSV Custom Builder** | `csv` crate | `polars` / `pandas` |
| **`Thread.Sleep` Retries** | Exponential delay | `tenacity` |

## 7.1 Other project Repositories of note

* [VoiceFileTaggerConsole](C:\Users\titwa\OneDrive\Dokumente\Documents\VS Code\VoiceFileTagger)
* [AiVoiceBiomarker](L:\My Drive\Work\Code\AiVoiceBiomarker)

---

## 8. **20-core CPU-only production optimization blueprint**

The architecture should follow the **Rust Edge Core + Python AI/Data Pipeline** model from the POC, with **Rust as the durable supervisor** and Python as an optional isolated sidecar for NLP/analytics.

Below is a production-oriented optimization blueprint for **AiVoiceTagger** on a **20-core CPU-only machine**, targeting:

* **Low cost**: local-first processing, no mandatory cloud/GPU spend.
* **High efficiency**: maximum useful CPU utilization without oversubscription.
* **Multi-threading + asynchronous results**: pipeline parallelism, bounded queues, out-of-order completion.
* **Zero lost failures**: no silent loss of files, chunks, transcripts, or errors.
* **Resilience**: crash recovery, retries, dead-lettering, atomic persistence.
* **Long-lasting robust audio processing**: resumable, memory-bounded, observable, supervisor-friendly.

# 1. Recommended Deployment Pattern

## Use Strategy A as the default: Rust CLI + Python Sidecar

From the architecture document:

> Strategy A: Polyglot CLI — Rust CLI + Python Sidecar  
> Rust streams structured JSON over stdin/stdout IPC or invokes Python via subprocess.

For a long-running, resilient batch audio system, this is the safest default:

```text
┌──────────────────────────────────────────────────────────────┐
│                    RUST SUPERVISOR / EDGE CORE               │
│                                                              │
│  • Directory scanning                                        │
│  • State store / WAL                                         │
│  • File decoding / probing                                   │
│  • Whisper STT worker pool                                   │
│  • Retry / checkpoint / atomic export coordination           │
│  • Bounded channels and backpressure                         │
└───────────────────────────┬──────────────────────────────────┘
                            │ NDJSON / Unix socket / stdin-stdout
┌───────────────────────────▼──────────────────────────────────┐
│                 PYTHON AI / DATA SIDECAR                     │
│                                                              │
│  • Pydantic validation                                       │
│  • NLP / verbatim / sentiment                                │
│  • Polars aggregation                                        │
│  • CSV / JSON / Parquet analytics export                     │
│  • Optional cloud fallback                                   │
└──────────────────────────────────────────────────────────────┘
```

### Why Strategy A?

* A Python crash does not bring down the Rust core.
* Rust can restart the Python sidecar and replay unacknowledged messages.
* Rust owns CPU-heavy audio and STT work.
* Python remains isolated for NLP, analytics, and optional cloud calls.
* The system can run with Python disabled for basic local tagging.

Use **Strategy B**, PyO3/Maturin, only when the top-level orchestration must live inside Python, such as notebooks or data-science pipelines. For production robustness, Strategy A is preferable.

---

# 2. Core Design Principle: “No Silent Loss”

You cannot guarantee zero failures in real-world audio processing. Corrupt files, network drops, disk-full events, invalid UTF-8, bad headers, and cloud timeouts will happen.

The correct target is:

> **Zero lost failures.**  
> Every file, chunk, transcript, error, retry, and final result must be durably accounted for.

That means the system should be:

* **At-least-once** in processing.
* **Idempotent** in result application.
* **Exactly-once in effect** from the user’s perspective.

To achieve this, add a durable internal state store in front of the final `RecordInfo.json`, `RecordList.csv`, and Parquet exports.

Recommended internal state store:

* SQLite in WAL mode, or
* redb / sled embedded DB, or
* append-only JSONL write-ahead log with periodic snapshots.

SQLite WAL is a good default because it is simple, robust, transactional, and low cost.

Example internal state machine:

```text
DISCOVERED
  -> QUEUED
  -> DECODED
  -> TRANSCRIBED
  -> NLP_DONE
  -> EXPORTED
  -> DONE

Any stage can move to:
  -> RETRY
  -> FAILED
  -> DEAD_LETTER
```

A record is not considered complete until it reaches `EXPORTED` or `DONE`.

---

# 3. 20-Core CPU Concurrency Model

The main bottleneck will be **Whisper STT**, followed by audio decoding/resampling and possibly Python NLP.

Do not run all work on the Tokio async runtime. Use dedicated thread pools:

* **Async I/O / orchestration**: Tokio.
* **CPU-bound STT**: dedicated OS threads or a dedicated Rayon pool.
* **Audio decoding/resampling**: dedicated blocking threads.
* **Python NLP**: separate processes or Python `ProcessPoolExecutor`.
* **Export**: limited writer concurrency to avoid disk contention.

## Suggested starting CPU budget

Assume 20 physical cores.

| Component | Concurrency | CPU budget | Notes |
| --- | ---: | ---: | --- |
| OS / supervisor / health / metrics | reserved | 1–2 cores | Prevent starvation |
| Directory scan / state ingestion | 1 async task | small | I/O bound |
| SQLite/WAL writer | 1 task | small | serialized durable commits |
| Audio decode / probe / resample | 2–3 threads | 2–3 cores | Symphonia / rodio-style work |
| Whisper STT workers | 3–4 workers | 12–16 cores | whisper-rs / whisper.cpp |
| Python NLP / verbatim / sentiment | 2–3 workers | 2–3 cores | isolated sidecar/processes |
| Export / aggregation | 1–2 tasks | 1 core | Polars / CSV / JSON / Parquet |

A safe initial configuration:

```text
Reserved OS / supervisor:      2 cores
Decode / resample workers:     3 threads
STT workers:                   4 workers
STT threads per worker:        3 threads
Python NLP workers:            3 workers
Export writer:                 1 task
```

That gives:

```text
STT:     4 × 3 = 12 cores
Decode:        3 cores
NLP:           3 cores
Export/IO:     ~1 core
Reserved:      1 core
Total:        ~20 cores
```

If STT is still the bottleneck and NLP is light, move to:

```text
STT workers:              4
STT threads per worker:   4
Decode workers:           2
Python NLP workers:       1–2
Export:                   1
Reserved:                 1–2
```

Then benchmark.

---

# 4. Avoid Thread Oversubscription

This is critical on CPU-only machines.

Whisper.cpp, BLAS libraries, Polars, Python thread pools, and Tokio can all create threads. If each subsystem assumes it owns the whole machine, performance collapses due to context switching.

Set explicit limits:

```bash
# Example environment controls
OMP_NUM_THREADS=1
OPENBLAS_NUM_THREADS=1
MKL_NUM_THREADS=1
TOKENIZERS_PARALLELISM=false
POLARS_MAX_THREADS=3
RAYON_NUM_THREADS=12
```

For Whisper specifically:

* Do not let Whisper use all 20 cores per job.
* Run multiple Whisper workers, each with a fixed thread count.
* Disable or constrain BLAS thread pools.
* Prefer explicit `n_threads` in `whisper-rs`/`whisper.cpp`.

Example:

```text
4 Whisper workers × 4 threads = 16 STT threads
```

Not:

```text
4 Whisper workers × 20 threads = 80 threads
```

The second configuration will be slower and less stable.

---

# 5. Local Whisper Optimization for CPU-Only, Low-Cost Processing

Use local Whisper through the Rust Edge Core:

> From the POC:  
> Speech Recognition via local Whisper models using `whisper.cpp` / `whisper-rs`.

For CPU-only, use quantized GGML models.

## Recommended model strategy

| Scenario | Model | Reason |
| --- | --- | --- |
| Maximum throughput, low-value audio | `tiny-q8_0` or `base-q8_0` | Fast, cheap, acceptable for simple content |
| Default production balance | `small-q5_0` or `small-q8_0` | Good French/English quality, still CPU-feasible |
| High-value or difficult audio | `small`/`medium` quantized, or cloud fallback | Higher accuracy, higher CPU cost |
| Very large models | Avoid by default | Too expensive on CPU-only unless volume is low |

For French audio, explicitly set the language:

```text
language = "fr"
```

Avoid automatic language detection unless the corpus is truly multilingual. Detection costs time and can introduce errors.

## Whisper CPU tuning

Use:

* Quantized models: `q5_0`, `q8_0`.
* Fixed language.
* No translation unless required.
* Minimal beam size.
* Token timestamps only when verbatim timing is required.
* Voice Activity Detection to skip silence.
* Chunked processing for long files.

Example Whisper settings:

```text
model: ggml-small-q5_0.bin
language: fr
translate: false
n_threads: 3 or 4
beam_size: 1 or small
token_timestamps: only if required
vad: enabled
chunk_length: 20–30 seconds
```

If word-level timing is required for `StatsVerbatim` and `SpeechContent`, enable timestamps selectively. Timestamp extraction increases CPU cost, so do not enable it for every pass unless needed.

---

# 6. Add Voice Activity Detection and Chunking

For long-running robust audio processing, do not feed entire long recordings into Whisper as one monolithic job.

Instead:

```text
Audio file
  -> decode to 16 kHz mono PCM
  -> VAD segmentation
  -> 20–30 second chunks
  -> Whisper per chunk
  -> merge results by offset
```

Benefits:

* Lower peak memory.
* Better crash recovery.
* Easier retries.
* Better async progress reporting.
* Less wasted work if one chunk fails.
* Natural checkpointing.

Use chunk IDs:

```text
record_id = stable_hash(path + size + mtime)
chunk_id  = record_id + "#" + start_ms + "-" + end_ms
```

Persist each chunk result independently.

Example:

```text
record_123#0-30000       DONE
record_123#30000-60000   DONE
record_123#60000-90000   RETRY
```

If the process crashes, only the incomplete chunks need reprocessing.

---

# 7. Pipeline Architecture with Bounded Queues

Use a staged pipeline with backpressure.

```text
┌────────────┐
│  Scanner   │
└─────┬──────┘
      │ FileTask
      ▼
┌────────────┐
│ State/WAL  │  persist DISCOVERED / QUEUED
└─────┬──────┘
      │
      ▼
┌────────────┐
│ Decoder    │  Symphonia / resample to 16 kHz mono
└─────┬──────┘
      │ AudioChunk
      ▼
┌────────────┐
│ VAD/Chunk  │
└─────┬──────┘
      │ ChunkTask
      ▼
┌────────────┐
│ STT Pool   │  whisper-rs workers
└─────┬──────┘
      │ RawTranscript
      ▼
┌────────────┐
│ Python NLP │  Pydantic / spaCy / verbatim / sentiment
└─────┬──────┘
      │ EnrichedRecord
      ▼
┌────────────┐
│ Export     │  JSON / CSV / Parquet
└────────────┘
```

Use bounded channels everywhere.

In Rust:

```rust
tokio::sync::mpsc::channel(capacity)
```

In Python:

```python
asyncio.Queue(maxsize=...)
```

Do not use unbounded channels. Unbounded channels eventually cause memory exhaustion on long-running jobs.

## Recommended backpressure rules

* If STT queue is full, decoder pauses.
* If decoder queue is full, scanner pauses.
* If NLP queue is full, STT result emission pauses.
* If export queue is full, NLP pauses.
* If memory limit is reached, ingestion stops.

Track an inflight budget:

```text
MAX_INFLIGHT_AUDIO_MB = 1024 or 2048
MAX_INFLIGHT_CHUNKS = 100–500
```

This keeps the process stable over multi-day runs.

---

# 8. Zero-Lost-Failure State Design

Every file should have a durable record before heavy processing begins.

## Minimal state schema

```sql
CREATE TABLE records (
    record_id TEXT PRIMARY KEY,
    path TEXT NOT NULL,
    file_size INTEGER,
    last_write_time TEXT,
    state TEXT NOT NULL,
    attempts INTEGER DEFAULT 0,
    last_error TEXT,
    lease_owner TEXT,
    lease_expires_at INTEGER,
    created_at TEXT,
    updated_at TEXT
);

CREATE TABLE chunks (
    record_id TEXT NOT NULL,
    chunk_id TEXT NOT NULL,
    start_ms INTEGER,
    end_ms INTEGER,
    state TEXT NOT NULL,
    attempts INTEGER DEFAULT 0,
    last_error TEXT,
    transcript_json TEXT,
    updated_at TEXT,
    PRIMARY KEY (record_id, chunk_id)
);

CREATE TABLE dead_letter (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    record_id TEXT,
    chunk_id TEXT,
    stage TEXT,
    error TEXT,
    context_json TEXT,
    created_at TEXT
);
```

Use SQLite pragmas:

```sql
PRAGMA journal_mode = WAL;
PRAGMA synchronous = NORMAL;
PRAGMA busy_timeout = 5000;
```

For maximum durability:

```sql
PRAGMA synchronous = FULL;
```

For high throughput with acceptable crash-window risk:

```sql
PRAGMA synchronous = NORMAL;
```

If “zero lost failure” is strict, prefer `FULL` for state transitions or use group commits carefully.

---

# 9. Idempotency and Deduplication

Use stable record IDs.

Good default:

```text
record_id = SHA-1(relative_path + file_size + last_write_time)
```

Stronger:

```text
record_id = SHA-1(relative_path + file_size + last_write_time + content_hash_prefix)
```

For network storage, content hashing may be expensive. Use it only when needed.

Idempotency rules:

* If the same `record_id` is rediscovered, skip it if already `DONE`.
* If the file changed, create a new version or reset the record state.
* If a chunk is reprocessed, overwrite the previous chunk result.
* If export is repeated, final export should replace previous output atomically.

This gives you safe retries.

---

# 10. Atomic File Writes

The legacy C# system used locks and retry loops. The modern replacement should use atomic writes.

From the POC:

> Modern solution: asynchronous non-blocking atomic file writes using `aiofiles` + temporary file renaming or `tenacity` retry decorators.

Use this pattern everywhere:

```text
write to temporary file
flush
fsync file
rename temporary file to final name
fsync directory, if required
```

In Rust, use:

* `tempfile`
* `std::fs::rename`
* `File::sync_all`

In Python, use:

* `aiofiles`
* `os.replace`
* `os.fsync`

Example final outputs:

```text
RecordInfo.json.tmp -> RecordInfo.json
RecordList.csv.tmp  -> RecordList.csv
report.parquet.tmp  -> report.parquet
```

Never write directly to the final file.

---

# 11. Retry, Timeout, and Dead-Letter Strategy

Use retries for transient errors only.

Transient errors:

* Network share temporarily unavailable.
* File locked briefly.
* Cloud API timeout.
* Temporary decode failure.
* Temporary disk I/O error.

Permanent errors:

* Corrupt audio beyond recovery.
* Invalid file format.
* Schema validation failure.
* Unsupported codec.
* Repeated Whisper failure.

## Retry policy

Use exponential backoff:

```text
attempt 1: immediate
attempt 2: 1 second
attempt 3: 5 seconds
attempt 4: 30 seconds
attempt 5: 2 minutes
```

In Python, use `tenacity`.

In Rust, use exponential delay with jitter.

Example:

```text
max_attempts = 5
backoff = exponential with jitter
max_delay = 120 seconds
```

After max attempts:

```text
state = DEAD_LETTER
```

Store:

* record ID
* chunk ID
* stage
* error message
* stack/context
* timestamp
* file path
* file metadata

A job is not “lost” if it lands in dead-letter. It is visible, queryable, and recoverable.

---

# 12. Lease-Based Worker Recovery

For long-running systems, workers can hang or crash.

Use leases:

```text
worker claims record/chunk
lease_owner = worker_id
lease_expires_at = now + 60 seconds
worker sends heartbeat every 20 seconds
```

If the lease expires, another worker can reclaim the task.

This prevents:

* stuck tasks,
* duplicate infinite processing,
* silent worker death,
* lost in-flight work.

For single-machine deployments, leases can be simple. For distributed deployments, they become essential.

---

# 13. Asynchronous Results Without Blocking

Results should be emitted as soon as they are ready. Do not wait for the entire batch to finish.

Use asynchronous result streams:

```text
Rust STT worker completes chunk
  -> writes raw transcript chunk to state store
  -> sends NDJSON message to Python sidecar
  -> Python enriches record
  -> Python sends ack/result
  -> Rust marks stage complete
  -> exporter writes final output incrementally
```

Use NDJSON, not one giant JSON document.

Example message:

```json
{
  "message_id": "0193f6c8-2a1b-7c3d-9e44-2f8b6e7d1a23",
  "record_id": "rec_9f8e7d",
  "chunk_id": "rec_9f8e7d#30000-60000",
  "stage": "TRANSCRIBED",
  "payload": {
    "text": "Bonjour, ceci est un exemple.",
    "language": "fr",
    "start_ms": 30000,
    "end_ms": 60000,
    "confidence": 0.82
  }
}
```

Python acknowledges:

```json
{
  "message_id": "0193f6c8-2a1b-7c3d-9e44-2f8b6e7d1a23",
  "record_id": "rec_9f8e7d",
  "chunk_id": "rec_9f8e7d#30000-60000",
  "status": "ACK"
}
```

If no ack arrives before timeout, Rust replays the message.

This gives asynchronous processing with durable delivery.

---

# 14. Rust Implementation Guidance

Use the technology mapping from the architecture document:

| Concern | Recommended Rust stack |
| --- | --- |
| Async runtime | `tokio` |
| Directory traversal | `walkdir`, optionally `ignore` for parallel traversal |
| Regex filename parsing | `regex` |
| Audio decoding/probing | `symphonia`, optionally `rodio` |
| Local STT | `whisper-rs` |
| Serialization | `serde`, `serde_json` |
| CSV | `csv` |
| Concurrency | channels, `Arc<Mutex<...>>` only where needed |
| Retries | exponential backoff with jitter |
| Atomic files | `tempfile` + rename |

## Important Rust rule

Do not run Whisper directly inside normal Tokio async tasks if it blocks the thread.

Use:

```rust
tokio::task::spawn_blocking
```

or a dedicated thread pool.

Example conceptual structure:

```rust
let (scan_tx, scan_rx) = tokio::sync::mpsc::channel(1000);
let (decode_tx, decode_rx) = tokio::sync::mpsc::channel(200);
let (stt_tx, stt_rx) = tokio::sync::mpsc::channel(500);
let (nlp_tx, nlp_rx) = tokio::sync::mpsc::channel(500);
let (export_tx, export_rx) = tokio::sync::mpsc::channel(200);
```

Keep capacities bounded.

---

# 15. Python Sidecar Guidance

Python should handle:

* Pydantic validation.
* NLP cleanup.
* Verbatim statistics.
* Sentiment or LLM tagging, if enabled.
* Polars aggregation.
* CSV/JSON/Parquet export.
* Optional Azure/OpenAI cloud fallback.

Use:

```text
asyncio          -> orchestration and I/O
ProcessPoolExecutor -> CPU-bound NLP if needed
Polars           -> fast aggregation
aiofiles         -> async file writes
tenacity         -> retries
Pydantic v2      -> schema validation
```

For CPU-bound NLP, do not rely only on asyncio. Python’s GIL can limit CPU parallelism. Use separate processes:

```python
from concurrent.futures import ProcessPoolExecutor
```

Or run multiple Python sidecar processes.

Limit Polars threads:

```bash
POLARS_MAX_THREADS=3
```

Otherwise Polars may try to use all 20 cores and fight Whisper.

---

# 16. NLP and LLM Cost Control

The POC includes:

> Complex NLP, verbatim parsing, LLM sentiment tagging.

On a CPU-only low-cost system, be careful with LLMs.

Recommended hierarchy:

1. **Rule-based verbatim and keyword statistics first.**
   * Fast.
   * Cheap.
   * Deterministic.
   * Good for `StatsVerbatim`.

2. **spaCy or lightweight local NLP second.**
   * Good for phrases, entities, sentence segmentation.
   * CPU-feasible if bounded.

3. **Local small quantized LLM only if needed.**
   * Expensive on CPU.
   * Use only for high-value records.
   * Batch prompts.
   * Cache results.

4. **Cloud LLM/Azure only as fallback.**
   * Use budget caps.
   * Use circuit breaker.
   * Cache aggressively.
   * Retry with exponential backoff.

For low-cost production, default LLM sentiment should be optional, not mandatory.

---

# 17. Audio Decoding and Probing Robustness

Use Rust native decoding as primary:

> From POC:  
> Audio decoding and probing via `symphonia` / `rodio`.

Normalize all audio for Whisper:

```text
sample rate: 16000 Hz
channels: mono
sample format: f32 or i16
```

Processing steps:

```text
open audio
  -> probe duration, sample rate, channels
  -> decode
  -> downmix to mono
  -> resample to 16 kHz
  -> optional peak normalization
  -> VAD segmentation
  -> send chunks to STT
```

## Corrupt header fallback

Preserve the legacy heuristic only as fallback:

> Legacy C# used:  
> seconds = round(file_size_bytes / 15563.4)

Modern rule:

```text
primary: Symphonia probe
fallback: file_size_bytes / 15563.4
```

Mark fallback records as degraded:

```json
{
  "duration_source": "filesystem_heuristic",
  "degraded": true
}
```

Do not let one corrupt file stop the batch.

---

# 18. Filename Date Parsing and Legacy Edge Cases

The POC notes legacy behavior:

> Legacy regex parsed filenames with optional date/time. If regex failed, dates defaulted to `1888-12-01`.

Modern approach:

```text
1. Try filename regex.
2. If missing, use filesystem LastWriteTime.
3. If still missing, use optional/null date.
4. Avoid fake default dates unless explicitly required.
```

Use:

* Rust: `chrono::DateTime<Utc>`
* Python: `datetime.datetime`

For C# tick conversion:

```text
milliseconds = ticks / 10,000
microseconds = ticks / 10
```

In Rust:

```rust
Duration::milliseconds(ticks / 10_000)
```

In Python:

```python
timedelta(microseconds=ticks // 10)
```

This matters when importing legacy `RecordInfo` data.

---

# 19. Unicode and French Text Handling

The legacy system used relaxed JSON escaping to preserve French characters.

Modern behavior:

Rust:

```rust
serde_json
```

outputs UTF-8 naturally.

Python:

```python
json.dump(data, f, ensure_ascii=False)
```

Do not escape French characters unnecessarily.

Example:

```json
{
  "text": "réunion, élève, à, è, é"
}
```

Not:

```json
{
  "text": "r\u00e9union, \u00e9l\u00e8ve, \u00e0, \u00e8, \u00e9"
}
```

---

# 20. Export Strategy: JSON, CSV, Parquet

Use different formats for different purposes.

| Format | Purpose |
| --- | --- |
| `RecordInfo.json` | operational state / interchange |
| `RecordList.csv` | human review / spreadsheet |
| Parquet | analytics, reporting, large-scale aggregation |

For large exports, use streaming and columnar processing.

Use Polars lazily:

```python
import polars as pl

lf = pl.scan_parquet("chunks/*.parquet")
result = (
    lf.filter(pl.col("state") == "DONE")
      .group_by("record_id")
      .agg([
          pl.col("duration_ms").sum(),
          pl.col("text").str.concat("\n"),
      ])
)
result.sink_parquet("report.parquet.tmp")
```

Then atomically rename:

```text
report.parquet.tmp -> report.parquet
```

Use compression:

```text
Parquet + zstd
JSONL + zstd, if needed
```

This reduces storage cost and improves analytics speed.

---

# 21. Network Storage Hardening

If audio files are on network shares, assume they can fail unpredictably.

Recommendations:

* Open source files read-only.
* Use timeouts on reads.
* Retry transient I/O errors.
* Avoid scanning too many files simultaneously.
* Prefer sequential directory batches.
* Cache file metadata locally.
* Optionally copy unstable remote files to local SSD before decoding.
* Do not write state files to unreliable network locations if avoidable.
* Keep the durable state store on local disk.

For long files over network storage, streaming decode is preferable to loading the whole file into memory.

---

# 22. Memory Safety for Long-Running Jobs

To run for hours or days:

* Use bounded channels.
* Drop PCM buffers immediately after use.
* Process audio in chunks.
* Limit concurrent decoded audio.
* Avoid loading entire long recordings into memory.
* Use Rust’s ownership model to prevent leaks.
* Monitor RSS.
* Set service memory limits.
* Rotate logs.
* Compact or checkpoint SQLite periodically.

Example memory budget:

```text
MAX_INFLIGHT_AUDIO_MB = 2048
MAX_DECODE_BUFFER_MB = 256
MAX_QUEUE_MESSAGES = 1000
```

If memory exceeds threshold:

```text
stop scanner
drain decode queue
continue STT
resume scanning when memory drops
```

---

# 23. Observability

A resilient long-running system must be observable.

Track metrics:

```text
files_discovered_total
files_queued
files_completed_total
files_failed_total
chunks_completed_total
chunks_failed_total
stt_queue_depth
decode_queue_depth
nlp_queue_depth
export_queue_depth
stt_real_time_factor
audio_seconds_processed_total
cpu_usage_percent
rss_bytes
dead_letter_count
average_processing_seconds_per_file
retry_count_total
```

Use structured logs:

```json
{
  "timestamp": "2026-08-03T10:15:00Z",
  "level": "INFO",
  "record_id": "rec_123",
  "stage": "STT_DONE",
  "duration_ms": 4310,
  "worker_id": "stt-2"
}
```

Add:

* tracing spans per record,
* worker IDs,
* chunk IDs,
* error classification,
* versioned model name.

For production, expose Prometheus metrics or write periodic status JSON:

```text
status.json
metrics.prom
health.json
```

---

# 24. Supervision and Graceful Shutdown

Run the Rust core under a supervisor:

* systemd on Linux,
* Docker with restart policy,
* Kubernetes liveness/readiness probes,
* Windows Service if deployed on Windows.

Use graceful shutdown:

```text
SIGTERM received
  -> stop scanner
  -> stop accepting new files
  -> finish in-flight chunks or checkpoint them
  -> flush state store
  -> flush export temp files
  -> shut down Python sidecar
  -> exit
```

Use cancellation tokens in Rust:

```rust
tokio_util::sync::CancellationToken
```

Do not kill long-running STT jobs abruptly unless the supervisor timeout forces it.

For systemd:

```ini
[Service]
Restart=on-failure
RestartSec=5
WatchdogSec=60
MemoryMax=16G
CPUAccounting=true
IOAccounting=true
```

If the machine is dedicated, avoid artificial CPU quotas. If shared, use quotas to protect other services.

---

# 25. Suggested Production Configuration

Example configuration for a 20-core CPU-only node:

```yaml
runtime:
  reserved_cores: 2
  graceful_shutdown_timeout_secs: 120

scanner:
  workers: 1
  exclude_extensions:
    - .xlsx
    - .csv
    - .json
  state_store: ./state/aivoicetagger.sqlite

decoder:
  workers: 3
  target_sample_rate: 16000
  target_channels: 1
  max_inflight_audio_mb: 2048

vad:
  enabled: true
  chunk_length_ms: 30000
  min_speech_ms: 250
  min_silence_ms: 500

stt:
  engine: whisper-rs
  model: models/ggml-small-q5_0.bin
  language: fr
  translate: false
  workers: 4
  threads_per_worker: 3
  beam_size: 1
  token_timestamps: false
  max_attempts: 5

nlp:
  sidecar: python
  workers: 3
  mode: async
  enable_llm: false
  enable_spacy: true
  enable_verbatim: true

export:
  json: ./out/RecordInfo.json
  csv: ./out/RecordList.csv
  parquet: ./out/report.parquet
  compression: zstd
  atomic_write: true

retry:
  max_attempts: 5
  initial_delay_ms: 1000
  max_delay_ms: 120000
  use_jitter: true

dead_letter:
  enabled: true
  store: ./state/dead_letter.sqlite
```

If STT is the dominant bottleneck, change:

```yaml
stt:
  workers: 4
  threads_per_worker: 4

decoder:
  workers: 2

nlp:
  workers: 2
```

Then benchmark.

---

# 26. Recommended Processing Rules

For each file:

```text
1. Discover file.
2. Compute record_id.
3. If record_id already DONE and unchanged, skip.
4. Persist DISCOVERED.
5. Parse filename date with regex.
6. If date missing, use LastWriteTime.
7. Probe audio duration with Symphonia.
8. If probe fails, use legacy size heuristic and mark degraded.
9. Decode to 16 kHz mono.
10. Run VAD.
11. Split into chunks.
12. Persist chunk tasks.
13. Send chunks to STT pool.
14. Persist raw transcript chunks.
15. Send to Python NLP.
16. Validate with Pydantic.
17. Aggregate verbatim/stats.
18. Export atomically.
19. Mark DONE.
20. On repeated failure, move to DEAD_LETTER.
```

---

# 27. Failure Matrix

| Failure | Detection | Response |
| --- | --- | --- |
| File missing | I/O error | retry, then dead-letter |
| Network timeout | read timeout | exponential retry |
| Corrupt audio | decode/probe error | fallback duration, mark degraded, dead-letter if unrecoverable |
| Unsupported codec | decoder error | optional FFmpeg fallback, then dead-letter |
| Whisper crash | worker panic/process exit | restart worker, requeue chunk |
| Python sidecar crash | IPC timeout | restart sidecar, replay unacked messages |
| Invalid NLP output | Pydantic validation error | dead-letter with payload |
| Disk full | write error | stop ingestion, alert, preserve state |
| Export failure | write/rename error | retry, atomic temp cleanup |
| Cloud API failure | HTTP/SDK error | circuit breaker, fallback to local, dead-letter if policy says so |
| Stuck worker | lease expiry | reclaim task |
| Duplicate file | same record_id | skip or idempotent overwrite |

---

# 28. Performance Tuning Checklist

Before optimizing further, measure.

Tune in this order:

1. **STT model**
   * `base-q8_0` fastest.
   * `small-q5_0` balanced.
   * Avoid large models unless necessary.

2. **STT worker count**
   * Start with 4 workers.
   * Try 3 threads per worker.
   * Then try 4 threads per worker.

3. **Decode concurrency**
   * Increase if decode queue is full and STT is idle.

4. **NLP concurrency**
   * Increase only if NLP queue is full and STT is waiting.

5. **Export batching**
   * Batch exports instead of writing per record.
   * Use Parquet for analytics.

6. **VAD**
   * Enable to reduce silence processing.

7. **Language fixed**
   * Set `fr` or `en` explicitly.

8. **Disable unnecessary timestamps**
   * Use only when verbatim timing is required.

9. **Control BLAS threads**
   * Prevent hidden thread explosion.

10. **Use native CPU flags**

* Compile with AVX2/FMA if the target machine supports them.

Example release build:

```bash
RUSTFLAGS="-C target-cpu=native" cargo build --release
```

For portable builds:

```bash
RUSTFLAGS="-C target-cpu=x86-64-v3" cargo build --release
```

Use `x86-64-v3` only if target CPUs support AVX2/FMA.

---

# 29. Robustness Tests

Before considering the system production-ready, test:

```text
kill -9 during scanning
kill -9 during decoding
kill -9 during Whisper
kill -9 during Python NLP
kill -9 during export
disk full
corrupt audio file
zero-byte audio file
network share disconnect
invalid UTF-8 metadata
very long audio file
thousands of tiny files
Python sidecar crash
Whisper worker panic
SQLite lock contention
restart after crash
```

Success criteria:

* No file is silently lost.
* No duplicate final record is produced.
* Temporary files are cleaned.
* State store remains consistent.
* Processing resumes from checkpoint.
* Dead-letter contains all permanent failures.
* Final JSON/CSV/Parquet exports are valid.

---

# 30. Final Recommended Architecture

For your constraints, the best design is:

```text
Rust supervisor
  + durable SQLite/WAL state
  + bounded async pipeline
  + dedicated decode threads
  + dedicated Whisper CPU worker pool
  + chunk-level checkpointing
  + atomic exports
  + isolated Python NLP sidecar
  + dead-letter queue
  + metrics and health checks
```

Recommended defaults:

```text
CPU-only local Whisper: enabled
Quantized model: small-q5_0 or base-q8_0
Language: fixed, e.g. fr
VAD: enabled
Chunking: 20–30 seconds
STT workers: 4
Threads per STT worker: 3 or 4
Decode workers: 2–3
Python NLP workers: 2–3
State store: SQLite WAL
Exports: atomic JSON/CSV/Parquet
Failures: retry + dead-letter
IPC: NDJSON with ack/replay
Cloud: optional fallback only
```

This gives you a low-cost, CPU-efficient, resilient system that can run for long periods on a 20-core machine while preserving the Rust/Python separation described in the AiVoiceTagger architecture.
