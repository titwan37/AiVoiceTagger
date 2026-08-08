# AiVoiceTagger Supervisor Dashboard Enhancement Plan

Transform the **AiVoiceTagger Supervisor Dashboard** from a simulated mock view into a **Real-Time Live Telemetry & Control Center** connected directly to `aivoicetagger_state.db` and the multi-machine processing pipeline.

---

## 🔍 Instant Situation vs. Current Dashboard Gaps

| Feature / Metric | Current Dashboard (Mock Mode) | Proposed Enhanced Live Dashboard |
| :--- | :--- | :--- |
| **Data Source** | Hardcoded mock generator (`useMockData: true`) | Live SQLite WAL reader (`aivoicetagger_state.db`) |
| **Worker Discovery** | Static mock cards (`node-1`, `node-2`, `node-3`) | Dynamic worker nodes (`pc-alpha`, `pc-beta`, etc.) derived from active DB leases |
| **Live Transcripts & Verbatim** | ❌ None | ⚡ Live feed of transcribed audio, speech counts, and verbatim alert triggers |
| **Manifest Partition Tracking** | ❌ None | 📦 Visual breakdown of partitioned CSV manifests (`inventory_pc1.csv`, `inventory_pc2.csv`) |
| **Instant CSV Export** | ❌ None | 📥 One-click "Export Live CSV" button in dashboard header |
| **AQI & Error Feed** | Aggregate numbers only | Interactive filterable table with exact error logs from `dead_letter` |

---

## 🏗️ Architectural Blueprint

```
 ┌──────────────────────────────────────────────────────────────────────────────────┐
 │                               AIVOICETAGGER CORE                                 │
 │  Worker pc-alpha ──┐                                                             │
 │  Worker pc-beta  ──┼──► [aivoicetagger_state.db] (WAL Mode)                       │
 └────────────────────┼─────────────────────┬───────────────────────────────────────┘
                      │                     │
                      │                     ▼
 ┌────────────────────┼─────────────────────────────────────────────────────────────┐
 │                    │   PYTHON LIVE TELEMETRY SERVER (sidecar/server.py)          │
 │                    │   • Polling / SQLite REST & WebSocket API                   │
 │                    │   • Dynamic worker node state & active lease aggregation    │
 │                    │   • Live transcripts & verbatim alerts endpoint             │
 └────────────────────┼─────────────────────┬───────────────────────────────────────┘
                      │                     │
                      │                     ▼
 ┌────────────────────┼─────────────────────────────────────────────────────────────┐
 │                    └─► ANGULAR SUPERVISOR DASHBOARD (http://localhost:4200)       │
 │                        • Dynamic Multi-Machine Worker Node Cards                 │
 │                        • Real-Time Transcripts & Verbatim Watchlist Panel        │
 │                        • One-Click "Instant CSV Export" Header Action            │
 └──────────────────────────────────────────────────────────────────────────────────┘
```

---

## ─── Proposed Changes ───

### 1. Python Live Telemetry & API Server (`sidecar/server.py`)
#### [NEW] [sidecar/server.py](file:///c:/Dev/AiVoiceTagger/sidecar/server.py)

- Create a lightweight Python HTTP / WebSocket API server using standard library `http.server` (or `FastAPI` / `Flask` / `asyncio`) to interface directly with `aivoicetagger_state.db`:
  - `GET /api/telemetry`: Queries `records`, `speeches`, `chunks`, and `dead_letter` tables in WAL mode. Returns:
    - Aggregate state counts (`Discovered`, `Queued`, `Decoded`, `Transcribed`, `Done`, `DeadLetter`).
    - Dynamic worker node telemetry (groups active `lease_owner` entries, current active file, progress, lease expiration).
    - Latest 10 transcribed audio stories (`story`), speech segment counts, AQI grades, and verbatim watchlist hits.
  - `GET /api/export/csv`: Generates and triggers instant timestamped CSV export (`YYYYMMDD_HHMMSS_Live_RecordList.csv`).

---

### 2. Angular Dashboard Backend Integration & Environment Update
#### [MODIFY] [dashboard/src/environments/environment.ts](file:///c:/Dev/AiVoiceTagger/dashboard/src/environments/environment.ts)
#### [MODIFY] [dashboard/src/app/services/monitoring-websocket.service.ts](file:///c:/Dev/AiVoiceTagger/dashboard/src/app/services/monitoring-websocket.service.ts)

- Update `environment.ts`:
  - Set `useMockData: false`.
  - Set `apiUrl: 'http://localhost:9090'`.
- Update `MonitoringWebSocketService` / telemetry service to fetch live telemetry polling from `http://localhost:9090/api/telemetry` (with 2-second auto-refresh) when WebSocket is connecting.

---

### 3. Angular UI Enhancement Components
#### [MODIFY] [supervisor-dashboard.component.html](file:///c:/Dev/AiVoiceTagger/dashboard/src/app/pages/supervisor-dashboard/supervisor-dashboard.component.html)
#### [MODIFY] [supervisor-dashboard.component.ts](file:///c:/Dev/AiVoiceTagger/dashboard/src/app/pages/supervisor-dashboard/supervisor-dashboard.component.ts)
#### [NEW] [live-transcripts-panel](file:///c:/Dev/AiVoiceTagger/dashboard/src/app/components/live-transcripts-panel)

- **Header Enhancement**:
  - Add **"📥 Export Live CSV"** button next to connection status.
  - Display active worker count badge (e.g. `2 Workers Active (pc-alpha, pc-beta)`).
- **Dynamic Worker Cards**:
  - Dynamically render worker node cards for any discovered `lease_owner` (`pc-alpha`, `pc-beta`, `node-1`, etc.) instead of hardcoded cards.
- **Live Transcripts & Verbatim Watchlist Feed**:
  - Add a dedicated interactive transcript feed component showing:
    - File Name & Directory.
    - Audio Quality Index badge (`GOOD`, `DEGRADED`, `UNUSABLE`).
    - Speech Segment count.
    - Transcribed story preview.
    - Verbatim watchlist tags (`Lethal`, `Legal`, `Menaces`, `Insultes`).

---

## 🧪 Verification Plan

### Automated & Manual Verification
1. **Launch Live Telemetry Server**:
   - Run `python sidecar/server.py` and verify `http://localhost:9090/api/telemetry` returns live data from `aivoicetagger_state.db`.
2. **Dashboard Verification**:
   - Serve Angular dashboard (`npm start` or `ng serve` in `dashboard/`).
   - Verify dynamic node cards update for `pc-alpha`, `pc-beta`, etc.
   - Verify live transcript feed displays real audio transcripts and speech segment counts.
   - Test clicking the **"📥 Export Live CSV"** button to verify instant CSV download.
