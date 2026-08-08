import re

def convert_to_mermaid():
    with open('c:\\Dev\\AiVoiceTagger\\Architecture-POC_v2.md', 'r', encoding='utf-8') as f:
        content = f.read()

    # Replace block 1
    block1 = """```
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
```"""
    mermaid1 = """```mermaid
flowchart TD
    subgraph RustEdgeCore["RUST EDGE CORE"]
        direction TB
        R1["Fast directory tree scanning & Regex filename parsing"]
        R2["Native audio loading, format decoding & duration probing"]
        R3["Embedded local Speech-to-Text (whisper.cpp / whisper-rs)"]
        R4["Concurrent state caching & JSON/CSV I/O"]
    end
    
    subgraph PythonAIPipeline["PYTHON AI & DATA PIPELINE"]
        direction TB
        P1["Complex NLP, verbatim parsing & LLM sentiment tagging"]
        P2["Post-processing, aggregation & custom statistical metrics"]
        P3["Polars / Pandas data frame export & visualization"]
        P4["Cloud STT fallbacks (Azure Speech SDK / OpenAI API)"]
    end

    RustEdgeCore -->|Clean Interface<br/>JSON IPC / FFI| PythonAIPipeline
    
    style RustEdgeCore fill:#fdf4e3,stroke:#e1b12c,stroke-width:2px,color:#2f3640
    style PythonAIPipeline fill:#e8f4f8,stroke:#0097e6,stroke-width:2px,color:#2f3640
```"""
    content = content.replace(block1, mermaid1)

    # Replace block 2
    block2 = """```text
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
```"""
    mermaid2 = """```mermaid
flowchart TD
    subgraph RustSupervisor["RUST SUPERVISOR / EDGE CORE"]
        direction TB
        RS1["Directory scanning"]
        RS2["State store / WAL"]
        RS3["File decoding / probing"]
        RS4["Whisper STT worker pool"]
        RS5["Retry / checkpoint / atomic export coordination"]
        RS6["Bounded channels and backpressure"]
    end
    
    subgraph PythonSidecar["PYTHON AI / DATA SIDECAR"]
        direction TB
        PS1["Pydantic validation"]
        PS2["NLP / verbatim / sentiment"]
        PS3["Polars aggregation"]
        PS4["CSV / JSON / Parquet analytics export"]
        PS5["Optional cloud fallback"]
    end

    RustSupervisor -->|NDJSON / Unix socket / stdin-stdout| PythonSidecar
    
    style RustSupervisor fill:#fdf4e3,stroke:#e1b12c,stroke-width:2px,color:#2f3640
    style PythonSidecar fill:#e8f4f8,stroke:#0097e6,stroke-width:2px,color:#2f3640
```"""
    content = content.replace(block2, mermaid2)

    # Replace block 3
    block3 = """```text
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
```"""
    mermaid3 = """```mermaid
stateDiagram-v2
    [*] --> DISCOVERED
    DISCOVERED --> QUEUED
    QUEUED --> DECODED
    DECODED --> TRANSCRIBED
    TRANSCRIBED --> NLP_DONE
    NLP_DONE --> EXPORTED
    EXPORTED --> DONE
    DONE --> [*]

    state "Error Handling" as Errors {
        RETRY
        FAILED
        DEAD_LETTER
        RETRY --> FAILED
        FAILED --> DEAD_LETTER
    }
    
    note right of Errors
      Any stage can move to RETRY, FAILED, or DEAD_LETTER
    end note
```"""
    content = content.replace(block3, mermaid3)

    # Replace block 4
    block4 = """```text
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
```"""
    mermaid4 = """```mermaid
flowchart TD
    S["Scanner"] -->|FileTask| W["State/WAL"]
    W -.->|persist DISCOVERED / QUEUED| W
    W --> D["Decoder"]
    D -.->|Symphonia / resample to 16 kHz mono| D
    D -->|AudioChunk| V["VAD/Chunk"]
    V -->|ChunkTask| ST["STT Pool"]
    ST -.->|whisper-rs workers| ST
    ST -->|RawTranscript| P["Python NLP"]
    P -.->|Pydantic / spaCy / verbatim / sentiment| P
    P -->|EnrichedRecord| E["Export"]
    E -.->|JSON / CSV / Parquet| E
    
    classDef comp fill:#f1f2f6,stroke:#747d8c,stroke-width:2px,color:#2f3640,rx:5px,ry:5px;
    class S,W,D,V,ST,P,E comp;
```"""
    content = content.replace(block4, mermaid4)

    # Let's also do the one from the README that might be mirrored. Wait, I'm only modifying Architecture-POC_v2.md.
    
    with open('c:\\Dev\\AiVoiceTagger\\Architecture-POC_v2.md', 'w', encoding='utf-8') as f:
        f.write(content)

if __name__ == "__main__":
    convert_to_mermaid()
