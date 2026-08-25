# Walkthrough: Tripartite Post-Analytics & 3D Forensic Intelligence

We have implemented the complete Post-Processing Analytics and 3D Visualization subsystem for **AiVoiceTagger** according to [Analytics_Architecture_v1.md](file:///c:/Dev/AiVoiceTagger/docs/Analytics_Architecture_v1.md).

---

## 🚀 Key Modules Implemented

### 1. Tripartite Post-Analytics Pipeline (`scripts/generate_tripartite_post_analytics.py`)
[generate_tripartite_post_analytics.py](file:///c:/Dev/AiVoiceTagger/scripts/generate_tripartite_post_analytics.py) connects directly to `aivoicetagger_state.db` and computes:

* **Discourse & Semantic Metrics (Polars)**:
  * Exact speaker talk-time distribution and conversational dominance ratios.
  * Lexical repetition cycle detection (n-gram loops for eviction/threat commands e.g. *"dégage"*, *"tu sors"*).
  * Chronological timestamped transcript formatting (`[HH:MM:SS.mmm --> HH:MM:SS.mmm] [Speaker] Utterance`).
* **Multi-Model LLM Execution (`litellm`)**:
  * **Tier 1 (Discourse Semantics):** Lexical loops, conversational dominance, cognitive evasion/gaslighting.
  * **Tier 2 (Swiss Forensic Law):** Statutory evaluation under **Art. 180 CP** (Threats), **Art. 181 CP** (Coercion), **Art. 177 CP** (Insults), **Art. 186 CP** (Violation de domicile), and **Art. 28/28b CC** (Personality Protection).
  * **Tier 3 (Psychodynamics):** Projective identification, coercive control architecture, family triangulation / parental alienation, double-bind directives.
* **Dual Output Structure**:
  * Court-admissible Markdown Dossiers: `export/post_analytics/Report_<name>_<id>.md`
  * JSON Telemetry Sidecars: `export/post_analytics/Telemetry_<name>_<id>.json`

---

### 2. 3D Forensic Constellation Data Bridge (`scripts/export_post_analytics_3d.py`)
[export_post_analytics_3d.py](file:///c:/Dev/AiVoiceTagger/scripts/export_post_analytics_3d.py) bridges SQLite transcripts into spatial coordinates:
* **$X, Y$ Semantic Plane:** Deterministic 2D sentence embedding projections (`umapX`, `umapY`).
* **$Z$-Axis Intensity:** RMS energy, syllable rate, and speech duration.
* **Cylindrical Statutory Sectors $(r, \theta, z)$:** Angular partitions for Swiss Criminal & Civil Code statutes (Art. 180 CP, 181 CP, 177 CP, 186 CP, 28b CC), radial severity scoring ($r$), and multi-year timeline height ($z$).
* **Output Payload:** `export/post_analytics/3d_constellation.json`.

---

### 3. WebGL 3D Visualizer & Custom GLSL Shaders
* [shaders.ts](file:///c:/Dev/AiVoiceTagger/dashboard/src/app/visualizer/shaders.ts): GLSL vertex/fragment shaders for RMS conversational agitation waves, gravitational attractor vortexes for repetitive lexical loops, and crisis heatmaps (Cyan $\rightarrow$ Amber $\rightarrow$ Crimson).
* [ForensicVisualizer3D.tsx](file:///c:/Dev/AiVoiceTagger/dashboard/src/app/visualizer/ForensicVisualizer3D.tsx): React Three Fiber interactive 3D canvas supporting 3 projection layers:
  1. `SEMANTIC`: Dynamic deformable manifold + glowing dialogue ribbon.
  2. `LEGAL_STATUTORY`: Cylindrical Swiss legal constellation with radial severity scoring.
  3. `PSYCHODYNAMIC`: Tetrahedral agent tension vectors (Target Parent, Aggressor, Triangulated Minor, Authority).

---

### 4. Sidecar API Server Integration (`sidecar/server.py`)
[server.py](file:///c:/Dev/AiVoiceTagger/sidecar/server.py) now exposes:
* `GET /api/post_analytics/reports`: Live list of generated forensic dossiers and JSON telemetry.
* `GET /api/post_analytics/3d`: Live 3D constellation payload for the WebGL frontend.

---

## 🛠️ Usage Guide

### 1. Run Tripartite Forensic Analysis
```powershell
# Analyze top red-flag priority files
python scripts/generate_tripartite_post_analytics.py --db-path "aivoicetagger_state.db" --min-score 300 --limit 5

# Target a specific recording ID
python scripts/generate_tripartite_post_analytics.py --db-path "aivoicetagger_state.db" --record-id "rec_0641a5f442d0dd96dcd6e561b58c7c9fae4543f8"

# Run with local privacy-first Ollama LLM
python scripts/generate_tripartite_post_analytics.py --model "ollama/qwen2.5:32b" --min-score 300
```

### 2. Export 3D Constellation Data
```powershell
python scripts/export_post_analytics_3d.py --db-path "aivoicetagger_state.db" --output "export/post_analytics/3d_constellation.json"
```
