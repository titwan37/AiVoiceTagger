# Feature: Graceful Shutdown & Mid-File Resume

AiVoiceTagger supports intercepting terminal interrupts (`Ctrl+C`) to gracefully exit the transcription loops without losing progress or corrupting file locks.

## How it works

### 1. Signal Interception (`src/main.rs`)
A dedicated background `tokio` task listens for `tokio::signal::ctrl_c()`. When the user triggers an interrupt, it flips the global atomic cancellation token: `crate::main::SHUTDOWN_FLAG`.

### 2. State Polling & Loop Breaking (`src/pipeline.rs`)
During the heavy, time-consuming Voice Activity Detection (VAD) and STT transcription chunk loops (which can take hours for large files), the pipeline checks `SHUTDOWN_FLAG.load()` after processing each 30-second chunk.
If an interrupt is detected, the engine:
- Warns the user via standard tracing logs.
- Breaks out of the chunk iteration loop.
- Commits the currently collected `speeches` vector to SQLite.
- Exits the function, triggering Rust's `Drop` implementation on `FileLockGuard` to safely delete the `.lock` sidecar file from the network drive.

### 3. Chunk-Level Progress Tracking (`src/state.rs` / `src/models.rs`)
AiVoiceTagger's SQLite schema (`records` table) includes a `processed_chunks` column. 
When the system shuts down early, this column stores the exact index of the last successful chunk.

### 4. Smart Resuming
When the engine is restarted via `cargo run`, the standard lease-claim query pulls the interrupted record.
The state store loads both the `processed_chunks` count and all pre-existing `speeches` for the record from the database.
In `pipeline.rs`, the `chunks` vector is explicitly sliced:
```rust
chunks = chunks.into_iter().skip(record.processed_chunks as usize).collect();
```
The STT engine bypasses the completed chunks and appends newly generated speeches natively.

## Adaptive Multipass Behavior
To maintain highest data integrity, Graceful Resume is strictly applied to **Pass 1** and the **Direct Heavy Fast-Path**.
If the system is interrupted during the optional **Pass 2** (Adaptive Multipass), it will safely discard the partial Pass 2 data and automatically restart Pass 2 from chunk 0 on the next launch.
