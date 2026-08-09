# AiVoiceTagger: Modern Hybrid Architecture & Migration Specification

This document presents a comprehensive, high-performance hybrid architecture for **AiVoiceTagger** (migrating and modernizing the legacy `.NET Core` `VoiceFileTagger` solution). 

By decoupling low-overhead edge audio/file operations (**Rust**) from high-level NLP, data analytics, and AI modeling (**Python**), the architecture delivers maximum execution speed, low memory overhead, and rapid AI feature iteration.

---

## 1. System Scope & Core Objective

**AiVoiceTagger** automates batch audio processing across local and network file storage. Its core responsibilities include:
*   **Directory Scanning & State Management**: Recursively traversing record directories, maintaining incremental state (`RecordInfo.json`), and avoiding duplicate work.
*   **Metadata & Probing**: Extracting timestamps from filenames via regex and probing audio stream metadata (duration, sample rate, bit depth).
*   **Transcription & STT**: Performing Speech-to-Text via local Whisper models (`whisper.cpp`/`whisper-rs`) or cloud engines (Azure Speech API).
*   **Verbatim & NLP Tagging**: Extracting word-level timing metrics, key phrase statistics, and AI/LLM-driven sentiment & verbatim insights.
*   **Persistence & Analytics**: Exporting aggregated reports to JSON, CSV, and high-performance columnar formats (Polars/Parquet).

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
*   **Mechanism**: The main executable is compiled in Rust. For heavy NLP or custom python scripts, Rust streams structured JSON over standard input/output (`stdin`/`stdout`) IPC or invokes python via standard subprocess.
*   **Pros**: Single zero-dependency binary for basic edge tagging; python dependency is optional and isolated.
*   **Best for**: Headless servers, edge devices, and lightweight local scanning.

### Strategy B: Native Python C-Extension (`pyo3` / `maturin`)
*   **Mechanism**: Rust core is compiled as a shared library (`.so`/`.pyd`) via **PyO3** and **Maturin**. Python imports `import voice_tagger_core` and invokes native Rust functions directly.
*   **Pros**: Entire top-level orchestration remains in Python for rapid developer iteration, while performance bottlenecks execute at full native hardware speed.
*   **Best for**: Data science environments, Jupyter notebooks, and advanced AI workflow pipelines.

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

### Key Field Mappings:
*   **`DateRecordDay` / `DateLastWrite`**: Mapped from C# `DateTime` to Rust `chrono::DateTime<Utc>` and Python `datetime.datetime`.
*   **`Duration` / `TimeSpan`**: Converted from C# `TimeSpan.Ticks` (100ns units) to Rust `std::time::Duration` / `chrono::Duration` and Python `datetime.timedelta`.
*   **`cSpeeches` / `Speeches`**: Managed as an ordered list of transcribed segments containing script text, confidence scores, offsets, and word-level timestamps.

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

1.  **Tick Conversions**: 
    *   C# `TimeSpan.Ticks` represents 100-nanosecond units ($1\text{ ms} = 10,000\text{ ticks}$).
    *   Python/Rust implementations must explicitly convert ticks: $\text{milliseconds} = \text{ticks} / 10,000$.
2.  **Audio Duration Heuristic Fallback**:
    *   Legacy C# used an empirical file-size formula when shell media duration failed: $\text{seconds} = \text{round}(\text{file\_size\_bytes} / 15563.4)$.
    *   Modern solution: Primary probing via Rust `symphonia`; fallback formula retained only for corrupt or unrecognized header files.
3.  **Filename Regex Fallback**:
    *   Legacy C# regex parsed filenames with optional time parts (`YYYY-MM-DD` or `YYYY-MM-DD-HH-MM-SS`). If regex matching failed completely, dates defaulted to `1888-12-01` to prevent `NullReferenceException`.
    *   Modern solution: Optional datetime fields in Pydantic/Rust with fallback to `LastWriteTime` from filesystem metadata.
4.  **Unicode & Escaping**:
    *   Legacy JSON serialization configured `JavaScriptEncoder.UnsafeRelaxedJsonEscaping` to preserve French characters (e.g., `é`, `è`, `à`).
    *   Python's `json.dump(..., ensure_ascii=False)` and Rust's `serde_json` natively output non-escaped UTF-8.
5.  **Thread Safety & Retries**:
    *   Legacy C# used `lock (RecordInfoBag.Locks)` and `Thread.Sleep(1000)` retry loops during file writes.
    *   Modern solution: Asynchronous non-blocking atomic file writes (`aiofiles` + temporary file renaming) or `tenacity` retry decorators.

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

