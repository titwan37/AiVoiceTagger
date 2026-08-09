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

* **Rust Toolchain**: `rustc` & `cargo` (1.75+)

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

### 3. Multi-Machine Parallel Processing & 3-Layer Defense-in-Depth

When running `AiVoiceTagger` across multiple worker machines (`pc-alpha`, `pc-beta`, etc.) processing audio files on a shared network drive (`\\SyNAS\Records`), follow this step-by-step workflow to ensure 100% collision-free parallel processing.

#### Step 1: Combine Existing Local Databases (Optional)

If your worker machines (`PC1` and `PC2`) have already been running independently with local SQLite databases, merge their progress into the central network database on `\\SyNAS\Records` first:

```powershell
python scripts/merge_dbs.py --dest "\\SyNAS\Records\aivoicetagger_state.db" --sources "C:\Dev\AiVoiceTagger\aivoicetagger_state_pc1.db" "C:\Dev\AiVoiceTagger\aivoicetagger_state_pc2.db"
```

> **Note:** The script creates an automatic `.bak` backup file before starting an explicit transaction, deduplicates records by ID, and prioritizes completed processing states.

---

#### Step 2: Generate & Partition the Master Manifest

##### 1. Generate Master Manifest

On **Computer A**, perform a dry-run scan across the shared audio directory:

```powershell
cargo run --release -- --scan-only --export-manifest inventory_all.csv
```

##### 2. Split into Balanced CSV Files

Run the PowerShell partitioning script to divide the manifest evenly between your worker nodes using round-robin distribution:

```powershell
.\scripts\split_manifest.ps1 -ManifestPath inventory_all.csv -NumWorkers 2
```

This creates `inventory_pc1.csv` and `inventory_pc2.csv` in your working directory. Copy `inventory_pc2.csv` over to Computer B (or keep both on the shared network drive).

---

#### Step 3: Configure Shared Network Database (`config.yaml`)

On **both** computers, update `config.yaml` so they point to the single shared state store on `\\SyNAS`:

```yaml
state_store:
  db_path: "\\\\SyNAS\\Records\\aivoicetagger_state.db"
  busy_timeout_ms: 10000
  journal_mode: "WAL"
  synchronous: "NORMAL"
```

---

#### Step 4: Launch Parallel Processing

Now launch both workers. They will operate with **all 3 layers of protection active** (Manifest Partitioning, `.lock` sidecar files on `\\SyNAS`, and SQLite WAL leases):

##### Computer A (`pc-alpha`)

```powershell
cargo run --release -- --config config.yaml --from-csv inventory_pc1.csv --worker-id pc-alpha
```

##### Computer B (`pc-beta`)

```powershell
cargo run --release -- --config config.yaml --from-csv inventory_pc2.csv --worker-id pc-beta
```

*(If you omit `--worker-id`, the system automatically detects and uses your computer's system hostname).*

---

#### 🛡️ How the 3 Layers Protect You in Real Time

1. **Layer 3 (Manifests):** Computer A only considers `inventory_pc1.csv` and Computer B considers `inventory_pc2.csv`.
2. **Layer 2 (Sidecar `.lock`):** Before decoding any audio file, the worker creates an atomic `audio.wav.lock` file containing its worker ID and timestamp. If a lock exists and is $< 30$ minutes old, the file is skipped instantly.
3. **Layer 1 (SQLite WAL):** SQLite locks individual records with `lease_owner = 'pc-alpha'` and a 10-second busy timeout over SMB to ensure database queries never collide.

---

### 4. Single-Machine Kernel Affinity Pinning

On high-core single machines (e.g. 20-core systems), you can also launch multiple local worker instances bound to specific CPU kernel groups:

#### Terminal 1 (Pinned to CPU Cores 0 to 5)

```powershell
cargo run --release -- --config config.yaml --worker-id node-1 --cpu-affinity 0-5
```

#### Terminal 2 (Pinned to CPU Cores 6 to 11)

```powershell
cargo run --release -- --config config.yaml --worker-id node-2 --cpu-affinity 6-11
```

---

### 4. Dynamic Model Override

To run the engine with a specific model on demand without modifying `config.yaml`:

```powershell
cargo run -- --config config.yaml --model models/ggml-medium-q8_0.bin
```

---

### 5. Running Multiple Parallel Workers on a Single Machine (Multi-threaded Race Condition Avoidance)

You can run multiple parallel processing instances on **`pc-alpha`**. The system is built with **SQLite WAL lease locks** and **`.lock` sidecar files**, making multi-process execution safe.

However, to get maximum performance and avoid CPU thread contention, you must observe **two rules**:

#### ⚠️ Two Essential Rules for Parallel Instances

1. **Use Unique Worker IDs**:
   * Do **not** use `--worker-id pc-alpha` for both instances. If you do, both processes will report under the same worker name and overwrite each other's database leases.
   * Use distinct names like `--worker-id pc-alpha-1` and `--worker-id pc-alpha-2`.

2. **Pin CPU Cores with `--cpu-affinity`**:
   * Whisper STT and PyTorch diarization attempt to use all available CPU cores by default. Running two instances without core pinning will cause thread thrashing and slow down both workers.
   * Core pinning isolates each process to its own dedicated set of CPU cores.

### 🚀 Recommended Commands to Launch 2 Parallel Workers on `pc-alpha`

#### Terminal / Window 1 (Worker 1 — Cores 0-5)

```powershell
cargo run --release -- --config config.yaml --from-csv inventory_pc1.csv --worker-id pc-alpha-1 --cpu-affinity "0-5"
```

#### Terminal / Window 2 (Worker 2 — Cores 6-11)

```powershell
cargo run --release -- --config config.yaml --from-csv inventory_pc1.csv --worker-id pc-alpha-2 --cpu-affinity "6-11"
```

*(Adjust `"0-5"` and `"6-11"` depending on your total CPU core count, e.g. `"0-7"` and `"8-15"` on a 16-core CPU).*

#### 💡 Partitioning Tip (Optional)

You can either:

* **Share the same CSV** (`inventory_pc1.csv`): Database lease locks will automatically prevent both workers from touching the same file (the second worker will automatically skip claimed files).
* **Split into separate manifests**: Run the helper script in PowerShell to split your queue evenly into `inventory_pc1.csv` and `inventory_pc2.csv`:

  ```powershell
  .\scripts\split_manifest.ps1 -ManifestPath inventory_manifest.csv -NumWorkers 2
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
