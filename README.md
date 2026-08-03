# AiVoiceTagger 🎙️⚡

**AiVoiceTagger** is a high-performance, CPU-optimized hybrid **Rust + Python** engine designed for resilient batch audio scanning, Whisper transcription, Voice Activity Detection (VAD), French watchlist verbatim matching, and analytical NLP tagging.

It replaces legacy .NET Core audio tagging solutions with a decoupled, thread-safe, multi-core architecture capable of scaling across local storage and heavy network shares (`\\SyNAS\Records`).

---

## 🏗️ Architecture Blueprint

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                                 RUST EDGE CORE                                  │
│  • Fast directory tree scanning & Regex date/filename metadata parsing          │
│  • Native audio loading & Symphonia 16 kHz mono PCM downmixing                  │
│  • Shared Arc<WhisperContext> Singleton & Persistent per-worker WhisperState    │
│  • Audio Quality Index (AQI): Good, Degraded, Unusable tagging                  │
│  • Multi-worker local Whisper STT pool (whisper.cpp / whisper-rs)               │
│  • SQLite WAL State Machine & Atomic Multi-Instance Lock-Free Task Leases       │
└────────────────────────────────────────┬────────────────────────────────────────┘
                                         │ Clean IPC Channel (NDJSON / Stdin-Stdout)
┌────────────────────────────────────────▼────────────────────────────────────────┐
│                            PYTHON AI & DATA SIDECAR                             │
│  • Verbatim Watchlist Matching (fatal, legal, menace, insultant)                │
│  • spaCy French NLP Entity Recognition & Story Enrichment                       │
│  • High-performance Polars multi-format export (JSON, CSV, Parquet)              │
└─────────────────────────────────────────────────────────────────────────────────┘
```

### Key Technical Highlights

* **⚡ Rust Edge Core**: Ultra-fast file probing, Symphonia decoding, and dedicated OS worker threads for Whisper STT.
* **🐍 Python Sidecar**: Isolated subprocess for spaCy NLP enrichment and Polars analytics.
* **🔄 Adaptive Double-Pass STT**: Dynamically escalates noisy, loud (battle scene), or low-confidence audio to heavier models.
* **🧠 Shared Model Singleton & Persistent Worker State**: Loads `WhisperContext` once into RAM (`Arc<WhisperContext>`) and reuses a single `WhisperState` per worker thread, eliminating buffer re-allocation churn (~330 MB per chunk) and saving 4x RAM.
* **🎯 Audio Quality Index (AQI)**: Evaluates speech presence, average confidence, and signal energy to grade output as `GOOD`, `DEGRADED`, or `UNUSABLE`.
* **⏱️ Real-Time Callbacks & Heartbeats**: Native `set_progress_callback_safe` logs chunk completion percentage (25%, 50%, 75%, 100%), while top-level 30-second pipeline heartbeats ensure zero hangs.
* **🏷️ High-Performance WordTiming**: Pre-allocated vector capacity (`Vec::with_capacity`), `token_eot` control token filtering, and UTF-8 space-glue cleanup (`\u{2581}`).
* **🔄 Adaptive Double-Pass STT**: Dynamically escalates noisy, loud (battle scene), or low-confidence audio to heavier models (`large-v3`).
* **📂 Manifest-Based Network Ingestion**: Prevents re-walking deep UNC network directories (`\\SyNAS\Records`) by generating and operating off a CSV manifest.
* **💻 Parallel Multi-Instance Core Pinning**: Run multiple process instances concurrently on distinct CPU kernel groups without thread thrashing.
* **🛡️ Zero-Data-Loss State Store**: SQLite WAL transaction supervisor with automatic lease recovery and dead-letter queuing.

---

## 🛠️ Prerequisites & Setup

### 1. System Requirements

- **Rust Toolchain**: `rustc` & `cargo` (1.75+)
* **Python**: Python 3.10+
* **LLVM / Clang** (Required on Windows for `whisper-rs-sys` C++ bindgen):

  ```powershell
  winget install Kitware.CMake
  ```

### 2. Build the Rust Engine

```powershell
cargo build --release
```

### 3. Launching via Batch Wrapper (`bootstart.bat`)

```cmd
.\bootstart.bat
```

---

## 📦 Whisper Model Downloads

Download GGML models into the `models/` directory using PowerShell:

```powershell
# 1. Fast Primary Model (ggml-small-q8_0.bin ~ 264 MB)
Invoke-WebRequest -Uri "https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-small-q8_0.bin" -OutFile "models\ggml-small-q8_0.bin" -UseBasicParsing

# 2. Heavy Fallback Model for Battle/Noisy Audio (ggml-large-v3-q5_0.bin ~ 1.08 GB)
Invoke-WebRequest -Uri "https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-large-v3-q5_0.bin" -OutFile "models\ggml-large-v3-q5_0.bin" -UseBasicParsing

# 3. Medium Multilingual Model (ggml-medium-q8_0.bin ~ 823 MB)
Invoke-WebRequest -Uri "https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-medium-q8_0.bin" -OutFile "models\ggml-medium-q8_0.bin" -UseBasicParsing
```

---

## ⚙️ Configuration (`config.yaml`)

```yaml
scanner:
  input_directory: "\\\\SyNAS\\Records"
  excluded_extensions: [".xlsx", ".csv", ".json", ".tmp", ".bak"]
  recursive: true
  min_file_size_bytes: 1024

state_store:
  db_path: "aivoicetagger_state.db"
  busy_timeout_ms: 5000
  journal_mode: "WAL"
  synchronous: "NORMAL"

decoder:
  worker_threads: 3
  target_sample_rate: 16000
  channels: 1

stt:
  enabled: true
  model_path: "models/ggml-small-q8_0.bin"
  language: "fr"
  workers: 4
  threads_per_worker: 3
  beam_size: 1
  enable_timestamps: true
  chunk_length_seconds: 30
  adaptive_multipass: true
  heavy_model_path: "models/ggml-large-v3-q5_0.bin"
  confidence_threshold: 0.80
  intensity_threshold_rms: 0.15

sidecar:
  enabled: true
  python_executable: "python"
  script_path: "sidecar/main.py"
  worker_threads: 3
  timeout_seconds: 60

exporter:
  output_directory: "export"
  export_json: true
  export_csv: true
  export_parquet: false
```

---

## 🚀 Advanced Usage Manual

### 1. Noisy Audio Parameter Tuning & AQI Grading

`AiVoiceTagger` incorporates tuned Whisper decoding parameters:
* `logprob_thold = -1.50`: Prevents unnecessary temperature fallback re-decode passes on short clear phrases (e.g. `"C'est super."`).
* `no_context = true`: Disables previous segment context to prevent ambient background noise from triggering continuous token repetition loops.
* `suppress_blank = true`: Suppresses blank tokens during decoding.
* `temperature_inc = 0.0`: Prevents multi-pass temperature escalation on noisy background samples.

Every output record includes an **Audio Quality Index (AQI)** tag:
* **`GOOD`**: Clear speech transcript with high confidence ($> 0.80$).
* **`DEGRADED`**: High ambient background noise or low confidence ($< 0.80$).
* **`UNUSABLE`**: Silent or purely non-speech background audio.

---

### 2. Manifest-Based Scanning for Network Shares (`\\SyNAS\Records`)

Scanning large network shares over SMB/UNC paths can be slow or subject to network drops. Use the 2-step manifest workflow:

#### Step 1: Scan Network Share & Export CSV Manifest

```powershell
cargo run -- --config config.yaml --scan-only --export-manifest inventory_nas.csv
```

*Outputs `inventory_nas.csv` containing all discovered files and parsed date metadata without running heavy audio processing.*

#### Step 2: Batch Process directly from CSV Manifest

```powershell
cargo run -- --config config.yaml --from-csv inventory_nas.csv
```

*(You can edit/filter `inventory_nas.csv` in Excel or Python before launching Step 2 to target specific files!)*

---

### 3. Parallel Multi-Instance Processing & CPU Kernel Affinity

On high-core machines (e.g. 20-core systems), you can launch multiple parallel instances of `AiVoiceTagger` bound to specific CPU kernel groups.

SQLite WAL task leasing guarantees that worker instances never collide or re-process the same file:

#### Terminal 1 (Pinned to CPU Cores 0 to 5)

```powershell
cargo run -- --config config.yaml --worker-id node-1 --cpu-affinity 0-5
```

#### Terminal 2 (Pinned to CPU Cores 6 to 11)

```powershell
cargo run -- --config config.yaml --worker-id node-2 --cpu-affinity 6-11
```

#### Terminal 3 (Pinned to CPU Cores 12 to 17)

```powershell
cargo run -- --config config.yaml --worker-id node-3 --cpu-affinity 12-17
```

---

### 4. Dynamic Model Override

To run the engine with a specific model on demand without modifying `config.yaml`:

```powershell
cargo run -- --config config.yaml --model models/ggml-medium-q8_0.bin
```

---

## 💻 Command-Line Interface (CLI) Reference

| CLI Option | Description | Example |
| :--- | :--- | :--- |
| `-c, --config <PATH>` | Path to YAML configuration file. | `--config config.yaml` |
| `-m, --model <PATH>` | Override Whisper STT model path. | `--model models/ggml-medium-q8_0.bin` |
| `--scan-only` | Perform dry-run discovery scan and exit. | `--scan-only` |
| `--export-manifest <PATH>` | Save discovered records inventory to CSV file. | `--export-manifest inventory.csv` |
| `--from-csv <PATH>` | Read file inventory directly from CSV manifest. | `--from-csv inventory.csv` |
| `--worker-id <ID>` | Custom worker instance identifier. | `--worker-id node-1` |
| `--cpu-affinity <CORES>` | Pin process execution to CPU cores. | `--cpu-affinity 0-5` |

---

## 🛡️ State Machine & Resilience

`AiVoiceTagger` tracks every record in `aivoicetagger_state.db` across 10 deterministic states:

```
[ DISCOVERED ] ──► [ QUEUED ] ──► [ DECODED ] ──► [ TRANSCRIBED ] ──► [ NLP_DONE ] ──► [ EXPORTED ] ──► [ DONE ]
                        │              │                 │
                        └──────────────┴─────────────────┴──► [ DEAD_LETTER / FAILED ]
```

* **Atomic Leases**: Claims carry a 5-minute lease expiry. If an instance crashes mid-transcription, its assigned files are automatically reclaimed by another active worker.
* **Dead-Letter Recovery**: Corrupt audio files or repeated failures land in the `dead_letter` table for audit without stopping the pipeline.

---

## 📄 License

MIT License.
