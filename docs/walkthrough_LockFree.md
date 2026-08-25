# Walkthrough — Defense-in-Depth Concurrency Control

The implementation of **Defense-in-Depth Concurrency Control** for **AiVoiceTagger** is complete. Multiple worker machines (`pc-alpha`, `pc-beta`, etc.) can now safely process audio files on shared network storage (`\\SyNAS\Records`) without duplicating work or encountering database locks.

---

## 🛠️ Changes Implemented

### 1. Layer 1 — Shared SQLite WAL Engine & Automatic Worker Identification
- **[config.yaml](file:///c:/Dev/AiVoiceTagger/config.yaml)**: Enforced `busy_timeout_ms: 10000` (10 seconds), `journal_mode: "WAL"`, and `synchronous: "NORMAL"`.
- **[src/main.rs](file:///c:/Dev/AiVoiceTagger/src/main.rs#L118-L123)**: Configured `--worker-id` CLI flag to automatically fallback to the system hostname (`COMPUTERNAME` or `HOSTNAME` environment variables) if omitted.
- **[src/state.rs](file:///c:/Dev/AiVoiceTagger/src/state.rs#L17-L24)**: Enforced atomic WAL and busy timeout pragmas upon SQLite connection initialization, paired with atomic `lease_owner` lock-free ticket assignment.

### 2. Layer 2 — Network Sidecar Lockfiles (`.lock`) & RAII Cleanup Guard
- **[src/pipeline.rs](file:///c:/Dev/AiVoiceTagger/src/pipeline.rs#L120-L133)**: Before probing/decoding any audio file `path/to/audio.wav`:
  - Checks if `path/to/audio.wav.lock` exists.
  - If `.lock` exists and is **younger than 30 minutes (1800s)**, skips the file immediately.
  - If `.lock` exists but is **older than 30 minutes**, overwrites/re-claims the stale lock.
  - Creates lockfile containing `Worker: <worker_id> | Timestamp: <ISO-8601>`.
- **[FileLockGuard RAII Struct](file:///c:/Dev/AiVoiceTagger/src/pipeline.rs#L277-L330)**: Automatically deletes the `.lock` file from the network drive when dropped (upon normal completion, panic, or error return).

### 3. Layer 3 — Manifest Partitioning & Utility Scripts
- **[scripts/split_manifest.ps1](file:///c:/Dev/AiVoiceTagger/scripts/split_manifest.ps1)**: Standalone PowerShell script that takes an `inventory_manifest.csv` and splits it into $N$ equal worker partitions (`inventory_pc1.csv`, `inventory_pc2.csv`, etc.) using round-robin distribution.
- **[scripts/merge_dbs.py](file:///c:/Dev/AiVoiceTagger/scripts/merge_dbs.py)**: Standalone Python script that merges isolated SQLite databases into a central state store (`\\SyNAS\Records\aivoicetagger_state.db`) with:
  - Atomic database backup creation (`destination.db.bak`).
  - Explicit transaction management (`BEGIN TRANSACTION`).
  - Record deduplication and state conflict resolution (preferring completed states and latest timestamps).

---

## 🚀 How to Run Multi-Node Parallel Execution

### Option A: Shared SQLite Database on `\\SyNAS`

1. Update `config.yaml` on both machines:
   ```yaml
   state_store:
     db_path: "\\\\SyNAS\\Records\\aivoicetagger_state.db"
   ```
2. Launch Computer A:
   ```powershell
   cargo run --release -- --config config.yaml --worker-id pc-alpha
   ```
3. Launch Computer B:
   ```powershell
   cargo run --release -- --config config.yaml --worker-id pc-beta
   ```

### Option B: Partitioned CSV Ingestion

1. Generate inventory manifest & partition into 2 files:
   ```powershell
   cargo run --release -- --scan-only --export-manifest inventory_all.csv
   .\scripts\split_manifest.ps1 -ManifestPath inventory_all.csv -NumWorkers 2
   ```
2. Run Computer A:
   ```powershell
   cargo run --release -- --from-csv inventory_pc1.csv
   ```
3. Run Computer B:
   ```powershell
   cargo run --release -- --from-csv inventory_pc2.csv
   ```

### Merging Existing Isolated Databases

If you have legacy isolated databases (`aivoicetagger_state_pc1.db` and `aivoicetagger_state_pc2.db`), merge them into a single database using:

```powershell
python scripts/merge_dbs.py --dest "\\SyNAS\Records\aivoicetagger_state.db" --sources "aivoicetagger_state_pc1.db" "aivoicetagger_state_pc2.db"
```
