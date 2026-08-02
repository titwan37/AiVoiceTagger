# AiVoiceTagger 🎙️⚡

**AiVoiceTagger** is a high-performance, CPU-optimized hybrid **Rust + Python** engine for resilient batch audio scanning, Whisper transcription, Voice Activity Detection (VAD), French watchlist verbatim matching, and analytical NLP tagging.

It modernizes and replaces legacy .NET Core audio tagging consoles with a modern decoupled architecture.

---

## 🏗️ Architecture & Features

```
[ Audio Files ] ──► [ Rust File Scanner & Prober ]
                             │
                             ▼
                    [ SQLite State Store (WAL) ]
                             │
              ┌──────────────┴──────────────┐
              ▼                             ▼
   [ Symphonia Audio Decoder ]     [ Whisper STT Worker Pool ]
   (16 kHz mono PCM downmixing)    (whisper-rs CPU bound)
              │                             │
              └──────────────┬──────────────┘
                             ▼
              [ NDJSON IPC Process Channel ]
                             │
                             ▼
               [ Python NLP Sidecar Worker ]
               ├─ Verbatim Watchlist Matching
               ├─ spaCy French Entity / NLP
               └─ Polars Multi-Format Exporter
                             │
                             ▼
           [ Parquet / CSV / JSON Analytics Reports ]
```

* **⚡ Rust Edge Core**: Multi-threaded scanner, Symphonia audio probing/decoding, SQLite WAL transaction state engine, and Whisper-rs STT worker pool.
* **🐍 Python Sidecar**: Isolated NDJSON IPC process handling spaCy NLP pipelines, French verbatim watchlist matching (`fatal`, `legal`, `menace`, `insultant`), and Polars data frame exports.
* **🔄 Resilient Resume**: State machine (`DISCOVERED` → `QUEUED` → `DECODED` → `TRANSCRIBED` → `NLP_DONE` → `EXPORTED` → `DONE`). If interrupted, re-running automatically resumes exactly from the last saved state without re-transcribing completed files.
* **🛡️ Fault Tolerant**: Dead-letter queuing for corrupt audio files with exponential retry policies.

---

## 🛠️ Prerequisites

1. **Rust Toolchain**: `rustc` & `cargo` (1.75+)
2. **Python**: Python 3.10+
3. **LLVM / Clang** (for `whisper-rs-sys` C++ bindings on Windows):
   ```powershell
   winget install LLVM.LLVM
   ```

---

## 🚀 Quick Start

### 1. Build the Rust Engine
```powershell
cargo build --release
```

### 2. Set Up Python Sidecar Dependencies
```powershell
cd sidecar
pip install -r pyproject.toml
# Or using uv:
# uv pip install -e .
```

### 3. Download a Whisper Model
Place a quantized GGML Whisper model in the `models/` directory:
- [ggml-small-q5_0.bin](https://huggingface.co/ggerganov/whisper.cpp/tree/main)

### 4. Run Pipeline
```powershell
cargo run -- --config config.yaml
```

---

## ⚙️ Configuration (`config.yaml`)

```yaml
scanner:
  input_directory: "C:\\Records\\"
  excluded_extensions: [".xlsx", ".csv", ".json", ".tmp", ".bak"]
  recursive: true
  min_file_size_bytes: 1024

state_store:
  db_path: "aivoicetagger_state.db"
  busy_timeout_ms: 5000

stt:
  enabled: true
  model_path: "models/ggml-small-q5_0.bin"
  language: "fr"
  workers: 4
  threads_per_worker: 3

python_sidecar:
  enabled: true
  executable: "python"
  script: "sidecar/main.py"
```

---

## 📄 License

MIT License.
