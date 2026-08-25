# Implementation Plan: Tripartite Post-Analytics & 3D Forensic Semantic Intelligence

This plan details the implementation of the post-processing analytics architecture specified in [Analytics_Architecture_v1.md](file:///c:/Dev/AiVoiceTagger/docs/Analytics_Architecture_v1.md). It transforms raw Whisper transcriptions and SQLite state tags from `aivoicetagger_state.db` into holistic, court-admissible forensic intelligence across three synchronized dimensions: **Discourse Semantics**, **Swiss Forensic Law**, and **Psychodynamics / Behavioral Relational Dynamics**, along with an interactive 3D WebGL visualization pipeline.

## User Review Required

> [!NOTE]
> The post-analytics engine uses `litellm` which supports both cloud APIs (OpenAI, Anthropic, Gemini) and 100% offline, air-gapped local models via **Ollama** (e.g. `ollama/qwen2.5:32b`, `ollama/mistral`). Default configuration will gracefully support local or mock execution when API keys are not present.

---

## Proposed Changes

### 1. Python Post-Analytics Core Pipeline

#### [NEW] [generate_tripartite_post_analytics.py](file:///c:/Dev/AiVoiceTagger/scripts/generate_tripartite_post_analytics.py)
- Connects to `aivoicetagger_state.db` using safe SQLite WAL pragmas (`busy_timeout = 10000`).
- Aggregates speech segments using **Polars** to compute discourse telemetry:
  - Speaker talk-time distribution and percentage of conversational dominance.
  - Lexical repetition cycles (n-gram loop detection for eviction commands like *"dégage"*, *"tu sors"*).
  - Chronological millisecond-accurate transcript formatting (`[HH:MM:SS.mmm --> HH:MM:SS.mmm] [Speaker] Utterance`).
- Multi-provider LLM batch execution via `litellm` using the Master Forensic Tripartite Prompt:
  - **Tier 1 (Discourse & Semantics):** Lexical loops, conversational dominance, cognitive evasion/gaslighting.
  - **Tier 2 (Swiss Forensic Law):** Statutory mapping under **Art. 180 CP** (Threats), **Art. 181 CP** (Coercion), **Art. 177 CP** (Insults), **Art. 186 CP** (Domicile violation), and **Art. 28/28b CC** (Personality protection).
  - **Tier 3 (Psychodynamics):** Projective identification, coercive control architecture, family triangulation/parental alienation, double-bind directives.
- Outputs dual files per record:
  - Court-ready Markdown report: `export/post_analytics/Report_<base>_<id>.md`
  - Structured JSON telemetry sidecar: `export/post_analytics/Telemetry_<base>_<id>.json`

---

### 2. 3D Forensic Semantic Data Bridge

#### [NEW] [export_post_analytics_3d.py](file:///c:/Dev/AiVoiceTagger/scripts/export_post_analytics_3d.py)
- Extracts dialogue nodes from `aivoicetagger_state.db` and computes spatial coordinates:
  - **$X, Y$ Semantic Plane:** 2D semantic embedding projections.
  - **$Z$-Axis Intensity:** RMS energy, speech rate, and Audio Quality Index (AQI).
  - **Cylindrical Coordinates $(r, \theta, z)$:** Angular partitions corresponding to Swiss legal statutes (Art. 180 CP, 181 CP, 177 CP, 186 CP, 28b CC), radial severity distance ($r$), and timeline height ($z$).
- Exports `export/post_analytics/3d_constellation.json` ready for consumption by WebGL / React Three Fiber visualizers.

---

### 3. WebGL / React Three Fiber 3D Visualizer Assets

#### [NEW] [shaders.ts](file:///c:/Dev/AiVoiceTagger/dashboard/src/app/visualizer/shaders.ts)
- Custom GLSL vertex and fragment shaders for:
  - Conversational agitation wave simulation based on RMS decibels.
  - Gravitational vortex / lexical attractor well deformations.
  - Tri-color crisis heatmap palette (Cyan $\rightarrow$ Amber $\rightarrow$ Crimson).

#### [NEW] [ForensicVisualizer3D.tsx](file:///c:/Dev/AiVoiceTagger/dashboard/src/app/visualizer/ForensicVisualizer3D.tsx)
- Complete interactive 3D canvas supporting 3 projection layers:
  1. `SEMANTIC`: Dynamic deformable manifold and glowing dialogue ribbon spline.
  2. `LEGAL_STATUTORY`: Cylindrical Swiss legal constellation with radial severity scoring and timeline grid.
  3. `PSYCHODYNAMIC`: Tetrahedral agent tension vectors (Target Parent, Aggressor, Triangulated Minor, Authority).

---

### 4. Sidecar API Server Integration

#### [MODIFY] [server.py](file:///c:/Dev/AiVoiceTagger/sidecar/server.py)
- Add API endpoints to serve post-analytics artifacts to the dashboard:
  - `GET /api/post_analytics/reports`: Lists generated forensic dossiers and summary metrics.
  - `GET /api/post_analytics/3d`: Returns the latest 3D constellation spatial payload.

---

## Verification Plan

### Automated Tests
1. **Pipeline Unit & Dry-Run Test**:
   ```powershell
   python scripts/generate_tripartite_post_analytics.py --help
   python scripts/export_post_analytics_3d.py --db-path "aivoicetagger_state.db" --limit 5
   ```
2. **Output Validation**:
   - Verify `export/post_analytics/3d_constellation.json` schema and data integrity.
   - Verify telemetry calculation via Polars with zero null-pointer crashes on empty segments.

### Manual Verification
- Review generated forensic dossiers for alignment with the tripartite structure and Swiss legal citations.
