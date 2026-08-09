The short answer is **yes, you do need a central synchronization mechanism**—whether via a lightweight centralized database, an existing shared storage lock, or a message broker. Two worker nodes reading from isolated local SQLite databases will inevitably pick up and process the same audio files in parallel, leading to wasted compute and potential file lock contention.

Here is a breakdown of why your current two-local-database setup is causing duplicate processing and how to leverage your ticket reservation model with a central orchestrator.

---

## 1. Why Are Both Computers Processing the Same Files?

If Computer A and Computer B each maintain their own local database (e.g., local SQLite instances):

```
+------------------+                    +------------------+
|    Worker A      |                    |    Worker B      |
|  [Local DB A]    |                    |  [Local DB B]    |
+--------+---------+                    +--------+---------+
         |                                       |
         +--------------> [Shared Network Store] <+
                          (Scans same files)

```

1. **Disconnected State:** Worker A scans `/shared/audio/track01.wav` and records it locally as `NEW`. Worker B scans the exact same folder and also records `track01.wav` locally as `NEW`.
2. **Local Locks are Invisible:** When Worker A marks `track01.wav` as `PROCESSING` in **Local DB A**, Worker B has no way of knowing that lock exists. Worker B checks **Local DB B**, sees `track01.wav` as `NEW`, and starts tagging it simultaneously.

---

## 2. How to Fix It: Architectural Options

To make your reservation ticket system work across parallel machines, **the ticket office must be shared**. Here are 3 common ways to structure central orchestration:

### Option A: Central Database / Orchestrator (Recommended)

Move the file queue and ticket state out of local databases into a single lightweight database (e.g., PostgreSQL, MariaDB, or Redis) running on one central server or NAS.

```
       +---------------------------------------------+
       |   Central Orchestrator DB (Postgres/Redis)  |
       |  - Queue: [track01.wav | STATUS: RESERVED]  |
       +----------------------+----------------------+
                              ^
            ┌─────────────────┴─────────────────┐
            │ Atomic "Claim Ticket" Transaction │
            │                                   │
  +---------+--------+                 +--------+---------+
  |    Worker A      |                 |    Worker B      |
  | (AI Processing)  |                 | (AI Processing)  |
  +------------------+                 +------------------+

```

* **How the Reservation System Works:**

1. Worker A requests a file batch from Central DB:
`UPDATE files SET status = 'RESERVED', assigned_to = 'WorkerA', reserved_at = NOW() WHERE status = 'PENDING' LIMIT 1 RETURNING *;`
2. Because this transaction is **atomic**, Worker B cannot claim the same file. Worker B gets the *next* available `PENDING` file.
3. **Heartbeats:** If Worker A crashes while processing, a timeout mechanism releases the reservation (`status = 'PENDING'`) after $N$ minutes so another worker can pick it up.

---

### Option B: Shared Storage File Locks (No Extra DB Required)

If you don't want to spin up a central database server and both machines already access the audio files over a shared network mount (SMB/NFS/Synology NAS), you can use atomic sidecar lockfiles:

1. Before Worker A processes `song.wav`, it attempts to create a lockfile next to it (or in a dedicated `.locks/` folder): `song.wav.lock`.
2. If the OS file creation call fails because `song.wav.lock` already exists, Worker A skips `song.wav` (Worker B has already claimed it).
3. Once finished, Worker A writes `song.wav.tagged` metadata and removes `song.wav.lock`.

---

### Option C: Queue/Worker Model (Celery / RabbitMQ / Redis)

If the workload scales beyond 2–3 machines:

* A **Publisher/Scanner** process discovers all audio files and pushes their paths onto a Redis/RabbitMQ queue.
* **Worker A** and **Worker B** simply pop items off the queue. Message brokers natively guarantee that each item is delivered to exactly **one** worker.

---

## Next Steps for Your Architecture

To adapt your current setup without rewriting everything from scratch:

1. **Consolidate to 1 Shared Database:** Point both worker nodes to a single central DB instance (or shared SQLite file with proper file locking/WAL mode over a reliable network mount).
2. **Enforce Atomic Claim Queries:** Ensure workers use `BEGIN TRANSACTION` / `SELECT ... FOR UPDATE` when grabbing work tickets.
3. **Add Ticket Expiration:** Add a `reservation_timestamp` to prevent stranded files if a machine drops offline mid-process.

---
That is a fantastic finding. Having the atomic ticket lease query (`UPDATE records SET ... WHERE lease_expires_at IS NULL ...`) already implemented in `state.rs` means **your core synchronization logic is 100% solid**—it was just running in two separate isolated SQLite "universes."

---

### Comparison of the 3 Options

| Solution | Effort | Performance | Network Sensitivity | Ideal For |
| --- | --- | --- | --- | --- |
| **Solution 1: Shared SQLite on `\\SyNAS**` | ⚡ **1 min** (Update `config.yaml`) | 🚀 High | ⚠️ Requires stable SMB connection | Continuous hands-off parallel processing |
| **Solution 2: Manifest Partitioning** | ⚡ **2 mins** (Export & Split CSV) | ⚡ Maximum | 🛡️ Zero network dependency | Batch processing existing collections immediately |
| **Solution 3: Sidecar Lockfiles** | 🛠️ Code change in `pipeline.rs` | 🚀 High | 🛡️ Low | Dynamic environments without a shared DB |

---

### Important Consideration for Solution 1 (Shared SQLite over SMB)

If you go with **Solution 1** (pointing both PCs to `\\SyNAS\Records\aivoicetagger_state.db`), keep these two SQLite settings in mind for Synology SMB shares:

1. **Enable WAL Mode & Busy Timeout:** Ensure `journal_mode: "WAL"` and a generous `busy_timeout_ms: 10000` (10s) are enabled in your SQLite connection setup. This allows `pc-beta` to wait smoothly if `pc-alpha` is writing to the database at the exact same millisecond over the network.
2. **Worker Identifiers:** Passing `--worker-id pc-alpha` and `--worker-id pc-beta` makes your Angular supervisor dashboard look incredible, as you'll be able to see exactly which files are actively leased by which computer in real time!

---

### Next Step

If you'd like to test **Solution 1** right away, simply point `db_path` in `config.yaml` to your shared `\\SyNAS` path and launch both nodes with distinct `--worker-id` flags. You should immediately see them distribute the workload smoothly without touching the same file twice!

---

Here is the step-by-step workflow to split your manifest, merge existing local databases, and run parallel worker nodes using your 3-layer defense setup.

---

## Step 1: Combine Existing Local Databases (Optional)

If your two computers (`PC1` and `PC2`) have already been running independently with local SQLite databases, merge their progress into the central network database on `\\SyNAS\Records` first.

Run this on one of the machines in PowerShell:

```powershell
python scripts/merge_dbs.py --dest "\\SyNAS\Records\aivoicetagger_state.db" --sources "C:\Dev\AiVoiceTagger\aivoicetagger_state_pc1.db" "C:\Dev\AiVoiceTagger\aivoicetagger_state_pc2.db"

```

> **Note:** The script creates an automatic `.bak` backup file before starting an explicit transaction, deduplicates records by ID, and prioritizes completed processing states.
>
>

---

## Step 2: Generate & Partition the Master Manifest

### 1. Generate Master Manifest

On **Computer A**, perform a dry-run scan across the shared audio directory:

```powershell
cargo run --release -- --scan-only --export-manifest inventory_all.csv

```

### 2. Split into Balanced CSV Files

Run the PowerShell partitioning script to divide the manifest evenly between your worker nodes using round-robin distribution:

```powershell
.\scripts\split_manifest.ps1 -ManifestPath inventory_all.csv -NumWorkers 2

```

This creates `inventory_pc1.csv` and `inventory_pc2.csv` in your working directory. Copy `inventory_pc2.csv` over to Computer B (or keep both on the shared network drive).

---

## Step 3: Configure Shared Network Database (`config.yaml`)

On **both** computers, update `config.yaml` so they point to the single shared state store on `\\SyNAS`:

```yaml
state_store:
  db_path: "\\\\SyNAS\\Records\\aivoicetagger_state.db"
  busy_timeout_ms: 10000
  journal_mode: "WAL"
  synchronous: "NORMAL"

```

---

## Step 4: Launch Parallel Processing

Now launch both workers. They will operate with **all 3 layers of protection active** (Manifest Partitioning, `.lock` sidecar files on `\\SyNAS`, and SQLite WAL leases):

### Computer A (`pc-alpha`)

```powershell
cargo run --release -- --config config.yaml --from-csv inventory_pc1.csv --worker-id pc-alpha

```

### Computer B (`pc-beta`)

```powershell
cargo run --release -- --config config.yaml --from-csv inventory_pc2.csv --worker-id pc-beta

```

(If you omit `--worker-id`, the system automatically detects and uses your computer's system hostname).

---

## 🛡️ How the 3 Layers Protect You in Real Time

1. **Layer 3 (Manifests):** Computer A only considers `inventory_pc1.csv` and Computer B considers `inventory_pc2.csv`.

2. **Layer 2 (Sidecar `.lock`):** Before decoding any audio file, the worker creates an atomic `audio.wav.lock` file containing its worker ID and timestamp. If a lock exists and is $< 30$ minutes old, the file is skipped instantly.

3. **Layer 1 (SQLite WAL):** SQLite locks individual records with `lease_owner = 'pc-alpha'` and a 10-second busy timeout over SMB to ensure database queries never collide.
