# Defense-in-Depth Concurrency Control Implementation Plan

Implement **3-Layer Defense-in-Depth Concurrency Control** for **AiVoiceTagger** to enable safe, high-throughput parallel execution across multiple worker machines (`pc-alpha`, `pc-beta`, etc.) processing audio on shared network storage (`\\SyNAS\Records`). Also provide offline database merge and manifest partitioning utility scripts.

---

## 🏗️ Architectural Blueprint

```
 ┌─────────────────────────────────────────────────────────────────────────────────────────┐
 │                                   WORKER NODE (e.g. pc-alpha)                           │
 │                                                                                         │
 │ ┌──────────────────────┐   ┌────────────────────────────────┐   ┌─────────────────────┐ │
 │ │  MANIFEST PARTITION  │   │  NETWORK SIDECAR LOCKFILES     │   │   SHARED SQLITE     │ │
 │ │  (--from-csv / CLI)  ├──►│  (audio.wav.lock guard)        ├──►│   WAL LEASE LOCK    │ │
 │ │  Round-Robin CSV     │   │  Atomic create & 30m stale check│   │   10s Busy Timeout  │ │
 │ └──────────────────────┘   └────────────────────────────────┘   └─────────────────────┘ │
 └─────────────────────────────────────────────────────────────────────────────────────────┘
```

---

## ─── Proposed Changes ───

### 1. Configuration & CLI Updates
#### [MODIFY] [config.yaml](file:///c:/Dev/AiVoiceTagger/config.yaml)
#### [MODIFY] [src/config.rs](file:///c:/Dev/AiVoiceTagger/src/config.rs)
#### [MODIFY] [src/main.rs](file:///c:/Dev/AiVoiceTagger/src/main.rs)

- **`config.yaml` & `src/config.rs`**:
  - Verify and enforce `busy_timeout_ms: 10000` (10s), `journal_mode: "WAL"`, and `synchronous: "NORMAL"` in `StateStoreConfig`.
  - Ensure `db_path` accepts network UNC paths (e.g. `\\SyNAS\Records\aivoicetagger_state.db`).
- **`src/main.rs`**:
  - Update `--worker-id` CLI argument logic: if not provided via `--worker-id`, automatically default to the system hostname (`COMPUTERNAME` / `HOSTNAME` environment variables, or fallback `worker_<pid>`).
  - Maintain support for `--scan-only --export-manifest <output.csv>` and `--from-csv <input.csv>`.

---

### 2. Layer 1: SQLite Connection & WAL Tuning
#### [MODIFY] [src/state.rs](file:///c:/Dev/AiVoiceTagger/src/state.rs)

- Apply pragmas upon SQLite connection initialization:
  - `PRAGMA journal_mode = WAL;`
  - `PRAGMA busy_timeout = 10000;` (10 seconds)
  - `PRAGMA synchronous = NORMAL;`
- In `claim_unprocessed_record(worker_id, lease_duration_secs)`:
  - Atomically claim `Discovered` / `Queued` records or expired leases (`lease_expires_at < now`).
  - Assign `lease_owner = worker_id` and set `lease_expires_at = NOW() + lease_duration_secs`.

---

### 3. Layer 2: Network Sidecar Lockfiles (`.lock`) & Cleanup Guard
#### [MODIFY] [src/pipeline.rs](file:///c:/Dev/AiVoiceTagger/src/pipeline.rs)

- **Locking Protocol**:
  - Target lock path: `path/to/audio.wav.lock`.
  - Check lock existence and creation time before decoding.
  - If `.lock` exists and is **younger than 30 minutes (1800s)**, skip file processing immediately (logged as active worker lease).
  - If `.lock` exists but is **older than 30 minutes**, treat as a stale crashed worker lock and overwrite/re-claim it.
  - Write worker ID and ISO-8601 timestamp inside the `.lock` file:
    `Worker: pc-alpha | Timestamp: 2026-08-05T00:37:27Z`
- **RAII Drop Guard (`FileLockGuard`)**:
  - Implement a Rust RAII struct `FileLockGuard` holding `PathBuf`.
  - Automatically deletes the `.lock` file when `FileLockGuard` goes out of scope (normal finish, panic, or error return).
  - Explicit `.disarm()` / `.release()` method for explicit cleanup.

---

### 4. Layer 3 & Utilities: Scripts
#### [NEW] [split_manifest.ps1](file:///c:/Dev/AiVoiceTagger/scripts/split_manifest.ps1)
#### [NEW] [merge_dbs.py](file:///c:/Dev/AiVoiceTagger/scripts/merge_dbs.py)

- **`scripts/split_manifest.ps1`**:
  - PowerShell script taking `-ManifestPath <csv>` and `-NumWorkers <int>` (default 2).
  - Splits input CSV lines using round-robin distribution into `inventory_pc1.csv`, `inventory_pc2.csv`, etc., preserving header.
- **`scripts/merge_dbs.py`**:
  - Python script taking `--dest <path>` and `--sources <path1> <path2> ...`.
  - Creates a backup copy (`destination.db.bak`) before starting an explicit `BEGIN TRANSACTION`.
  - Merges `records`, `speeches`, `chunks`, and `dead_letter` tables.
  - Deduplicates by `record_id`. Conflict resolution prefers higher state (`Done` / `Transcribed` / `NlpDone` > `Queued` / `Discovered`) and latest `updated_at`.
  - Outputs a summary report of merged records, resolved conflicts, and deduped tags.

---

## 🧪 Verification Plan

### Automated Verification
1. **Compilation Check**:
   - `cargo check` and `cargo build --release` to verify Rust code compiles without errors or warnings.
2. **Database & Lockfile Functional Test**:
   - Run a test run with `--worker-id test_node` to verify lockfile creation, content writing, and automatic deletion upon completion.
3. **Script Verification**:
   - Run `scripts/split_manifest.ps1` against a sample CSV and verify balanced split output files.
   - Run `scripts/merge_dbs.py` in `--help` or test mode to verify database backup creation, transaction safety, and deduplication logic.

---

## User Review Required

> [!NOTE]
> All lockfiles (`.lock`) will be automatically removed upon completion of each audio file. If a node crashes mid-process, lockfiles older than 30 minutes are automatically reclaimed by any active worker node.
