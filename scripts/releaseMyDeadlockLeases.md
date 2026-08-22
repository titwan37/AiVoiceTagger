## 🛠️ How to Reset Leases & Re-Enable Parallel Workers

To clear out these 601 stale locks from dead/crashed processes and let `pc-alpha-1` and `pc-alpha-2` resume processing `TriagedHighInterest` records, run this cleanup script:

### Step 1: Release All Stale Leases in `aivoicetagger_state.db`

Run this Python script directly from PowerShell:

```powershell
python -c "import sqlite3; conn = sqlite3.connect('aivoicetagger_state.db'); cursor = conn.cursor(); cursor.execute('UPDATE records SET lease_owner = NULL, lease_expires_at = NULL WHERE state != \"DONE\"'); conn.commit(); print(f'Successfully cleared {cursor.rowcount} stale leases!')"
```[cite: 3, 5, 8]

---

### Step 2: Remove Disk Sidecar Lockfiles (`.lock`)

Delete any temporary network lockfiles left behind on `\\SyNAS\Records`[cite: 3, 5, 8]:

```powershell
Get-ChildItem -Path "\\SyNAS\Records" -Filter "*.lock" -Recurse | Remove-Item -Force
```[cite: 3, 5]

---

### Step 3: Launch Both Worker Nodes

Now launch both worker processes in separate PowerShell terminals:

#### Terminal 1 (`pc-alpha-1` — Cores 0-5)
```powershell
cargo run --release -- --config config.yaml --from-csv inventory_pc1.csv --worker-id pc-alpha-1 --cpu-affinity "0-5"
```[cite: 3]

#### Terminal 2 (`pc-alpha-2` — Cores 6-11)
```powershell
cargo run --release -- --config config.yaml --from-csv inventory_pc1.csv --worker-id pc-alpha-2 --cpu-affinity "6-11"
```[cite: 3]

---

### 📊 Expected Outcome

With stale leases cleared, `pc-alpha-1` and `pc-alpha-2` will cleanly pick up the **253 `TriagedHighInterest` records**, lock them under their respective worker IDs, and begin full Whisper transcription without colliding or exiting early[cite: 3, 5, 8, 14]!

```
