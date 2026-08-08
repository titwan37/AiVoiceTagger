# AiVoiceTagger Supervisor Dashboard — Angular Implementation Plan

## Overview

Build a real-time observability monitoring dashboard in **Angular 16+** for system supervisors tracking distributed AiVoiceTagger worker nodes. The dashboard provides live telemetry into the multi-stage pipeline state machine, per-node health, Audio Quality Index (AQI), and resource utilization — all powered by Angular Signals and WebSocket streaming.

> [!IMPORTANT]
> The Angular app lives inside `c:\Dev\AiVoiceTagger\dashboard\` as a standalone project. The Rust backend will need a future `/api/telemetry/ws` WebSocket endpoint (or SSE). For now the dashboard ships with a **mock WebSocket service** that simulates realistic telemetry payloads for development and demo purposes.

## Open Questions

> [!IMPORTANT]
> **Backend Telemetry Endpoint**: The Rust engine does not yet expose a WebSocket or HTTP telemetry API. This plan includes a mock service for standalone development. A future Rust-side `actix-web` or `axum` telemetry endpoint can be wired in by swapping the mock URL.

---

## Proposed Changes

### Project Scaffold

```
c:\Dev\AiVoiceTagger\dashboard\
├── angular.json
├── package.json
├── tsconfig.json
├── tsconfig.app.json
├── src/
│   ├── index.html
│   ├── main.ts
│   ├── styles.scss
│   ├── app/
│   │   ├── app.component.ts          # Root shell
│   │   ├── app.component.html
│   │   ├── app.component.scss
│   │   ├── models/
│   │   │   └── telemetry.models.ts   # All TypeScript interfaces
│   │   ├── services/
│   │   │   ├── telemetry-store.service.ts      # Signal-based reactive store
│   │   │   └── monitoring-websocket.service.ts # WebSocket + mock data layer
│   │   ├── components/
│   │   │   ├── global-banner/
│   │   │   │   ├── global-banner.component.ts
│   │   │   │   ├── global-banner.component.html
│   │   │   │   └── global-banner.component.scss
│   │   │   ├── node-status-card/
│   │   │   │   ├── node-status-card.component.ts
│   │   │   │   ├── node-status-card.component.html
│   │   │   │   └── node-status-card.component.scss
│   │   │   ├── aqi-badge/
│   │   │   │   ├── aqi-badge.component.ts
│   │   │   │   ├── aqi-badge.component.html
│   │   │   │   └── aqi-badge.component.scss
│   │   │   └── pipeline-stage-bar/
│   │   │       ├── pipeline-stage-bar.component.ts
│   │   │       ├── pipeline-stage-bar.component.html
│   │   │       └── pipeline-stage-bar.component.scss
│   │   └── pages/
│   │       └── supervisor-dashboard/
│   │           ├── supervisor-dashboard.component.ts
│   │           ├── supervisor-dashboard.component.html
│   │           └── supervisor-dashboard.component.scss
│   └── environments/
│       ├── environment.ts
│       └── environment.prod.ts
```

---

### 1. Data Models & Interfaces

#### [NEW] [telemetry.models.ts](file:///c:/Dev/AiVoiceTagger/dashboard/src/app/models/telemetry.models.ts)

TypeScript interfaces mirroring Rust domain types:

- `PipelineStage` — union type: `'DISCOVERED' | 'QUEUED' | 'DECODED' | 'TRANSCRIBED' | 'NLP_DONE' | 'EXPORTED' | 'DONE' | 'DEAD_LETTER' | 'FAILED' | 'RETRY'`
- `QualityGrade` — `'GOOD' | 'DEGRADED' | 'UNUSABLE'`
- `NodeHealth` — `'HEALTHY' | 'STALLED' | 'OFFLINE'`
- `SidecarStatus` — `'ACTIVE' | 'RESTARTING' | 'BACKPRESSURE_PAUSED' | 'OFFLINE'`
- `NodeTelemetry` — per-worker telemetry snapshot (worker_id, cpu_affinity, health, active file, current stage, chunk progress %, loaded model, sidecar status, resource metrics, lease_expires_at, last_heartbeat)
- `AqiBreakdown` — `{ good: number, degraded: number, unusable: number }`
- `PipelineStageCounts` — counts per stage for the global funnel
- `GlobalMetrics` — aggregate metrics (total_discovered, total_queued, audio_duration_processed_sec, wall_clock_elapsed_sec, real_time_factor, aqi_breakdown, dead_letter_count, failure_count, pipeline_stage_counts)
- `TelemetryPayload` — `{ timestamp: string, global: GlobalMetrics, nodes: NodeTelemetry[] }`

---

### 2. Services

#### [NEW] [monitoring-websocket.service.ts](file:///c:/Dev/AiVoiceTagger/dashboard/src/app/services/monitoring-websocket.service.ts)

- Injectable standalone service using `inject()`.
- Connects to `environment.wsUrl` (default: `ws://localhost:9090/api/telemetry/ws`).
- Implements **exponential backoff reconnection** (1s → 2s → 4s → 8s → max 30s) on disconnect.
- Exposes `messages$: Observable<TelemetryPayload>` RxJS stream.
- **Mock mode**: When `environment.useMockData === true`, generates simulated `TelemetryPayload` every 2 seconds using `interval()` + randomized worker states, AQI distributions, and stage progression.

#### [NEW] [telemetry-store.service.ts](file:///c:/Dev/AiVoiceTagger/dashboard/src/app/services/telemetry-store.service.ts)

- Signal-based reactive store using Angular `signal()`, `computed()`, and `effect()`.
- Writable signals:
  - `globalMetrics = signal<GlobalMetrics>(...)` 
  - `nodes = signal<NodeTelemetry[]>([])`
  - `connectionStatus = signal<'CONNECTED' | 'RECONNECTING' | 'DISCONNECTED'>('DISCONNECTED')`
  - `lastUpdateTimestamp = signal<string>('')`
  - `searchFilter = signal<string>('')`
  - `stageFilter = signal<PipelineStage | 'ALL'>('ALL')`
  - `aqiFilter = signal<QualityGrade | 'ALL'>('ALL')`
- Computed signals (derived, zero-cost, fine-grained):
  - `activeNodeCount = computed(() => nodes that are HEALTHY)`
  - `stalledNodeCount = computed(() => nodes that are STALLED)`
  - `realTimeFactor = computed(() => audio_duration / wall_clock)`
  - `degradedRatio = computed(() => degraded / total AQI)`
  - `filteredNodes = computed(() => apply search + stage + AQI filters)`
- `effect()` watcher that logs stale-node heartbeat warnings (last_heartbeat > 60s ago).
- Subscribes to `MonitoringWebSocketService.messages$` in constructor to hydrate signals.

---

### 3. Components

#### [NEW] [global-banner.component.ts](file:///c:/Dev/AiVoiceTagger/dashboard/src/app/components/global-banner/global-banner.component.ts)

Top banner displaying aggregated global telemetry KPIs:
- Total Files Discovered / Queued
- Audio Duration Processed (formatted `HH:MM:SS`)
- Real-Time Factor (RTF) with color indicator
- AQI Breakdown (3 mini-badges: Good / Degraded / Unusable with counts + percentages)
- Dead-Letter + Failure alert counter (pulsing red when > 0)
- Connection status indicator dot

#### [NEW] [node-status-card.component.ts](file:///c:/Dev/AiVoiceTagger/dashboard/src/app/components/node-status-card/node-status-card.component.ts)

Per-worker card with:
- Header: Worker ID badge + health status dot (green/amber/red) + CPU affinity label
- Active file name + current pipeline stage badge
- Chunk progress bar (0-100%) with animated fill
- Loaded model label (e.g. `ggml-small-q8_0.bin`)
- Sidecar IPC status indicator
- Resource gauges: CPU %, RSS Memory MB
- Lease expiration countdown timer
- Last heartbeat relative time ("12s ago", "45s ago")

#### [NEW] [aqi-badge.component.ts](file:///c:/Dev/AiVoiceTagger/dashboard/src/app/components/aqi-badge/aqi-badge.component.ts)

Reusable quality grade badge:
- `@Input() grade: QualityGrade`
- Color-coded: Emerald (`GOOD`), Amber (`DEGRADED`), Dark Red (`UNUSABLE`)
- Pill-shaped with icon + label

#### [NEW] [pipeline-stage-bar.component.ts](file:///c:/Dev/AiVoiceTagger/dashboard/src/app/components/pipeline-stage-bar/pipeline-stage-bar.component.ts)

Horizontal segmented bar showing the pipeline funnel distribution:
- Each stage gets a proportional width segment
- Color gradient: teal → blue → indigo → violet → emerald → gray → red
- Hover tooltips showing exact count per stage

---

### 4. Pages

#### [NEW] [supervisor-dashboard.component.ts](file:///c:/Dev/AiVoiceTagger/dashboard/src/app/pages/supervisor-dashboard/supervisor-dashboard.component.ts)

Main dashboard container:
- Injects `TelemetryStore`
- Layout: Global Banner (top) → Filter Bar → Pipeline Stage Bar → Node Grid (CSS Grid, responsive 1-3 columns)
- Uses Angular `@for` / `@if` control flow
- Filter bar with search input, stage dropdown, AQI dropdown
- Auto-refreshing relative timestamps

---

### 5. Styling & UX

#### [NEW] [styles.scss](file:///c:/Dev/AiVoiceTagger/dashboard/src/styles.scss)

- Dark mode theme (HSL-based design tokens)
- CSS custom properties for colors, spacing, radii, shadows
- Google Fonts: Inter (body), JetBrains Mono (metrics)
- Glassmorphism card effects with `backdrop-filter: blur()`
- Smooth micro-animations for progress bars, status transitions, pulse effects
- Responsive breakpoints: mobile (1 col), tablet (2 col), desktop (3 col)

---

## Verification Plan

### Automated
```powershell
cd c:\Dev\AiVoiceTagger\dashboard
npm install
ng serve --open
```

### Manual Verification
- Verify mock telemetry data streams to the dashboard every 2 seconds.
- Confirm AQI badges render with correct colors (emerald/amber/red).
- Confirm node cards show animated chunk progress bars.
- Confirm pipeline stage bar distributes proportionally.
- Confirm filter controls narrow displayed nodes.
- Confirm stale heartbeat detection marks nodes as STALLED (amber) after 60s.
- Confirm dead-letter counter pulses red when > 0.
- Verify responsive layout at 3 breakpoints.
