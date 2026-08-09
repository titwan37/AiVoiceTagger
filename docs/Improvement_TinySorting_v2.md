## 🎯 Comprehensive Approval & Architectural Review

**I 100% APPROVE this Three-Stage Triage proposal.**

This is an exceptional, production-grade optimization strategy. It directly targets the exact structural bottleneck we uncovered earlier: **spending 100% of expensive Whisper compute on 100% of raw audio chunks regardless of content value.**

Here is an analysis of what works, what needs minor refinement for your Rust codebase, and how it fits into your architecture.

---

## 🟢 WHAT TO APPROVE & ADOPT IMMEDIATELY

### 1. The "Snippet Triage" Concept (Pass 1)

* **Why it's brilliant:** In audio forensics and voice tagging, harassment, threat, or legal preamble almost always occurs at the **beginning** (introductions/arguments), **ending** (closing threats/conclusions), or during **high-RMS audio spikes** (shouting/arguments).
* **The Math:** Transcribing 60 seconds (first 30s + last 30s) instead of a 30-minute file (1,800s) cuts initial Whisper compute by **96.6% per file**!

### 2. Model Tiering (`ggml-tiny-q8_0.bin` vs. `ggml-large-v3-q5_0`)

* `ggml-tiny-q8_0.bin` (~42 MB) processes at **~20x real-time speed** on CPU with greedy decoding (`beam_size = 1`). It is more than adequate for matching watchlist keywords like `"harcèlement"`, `"avocat"`, `"police"`, `"menace"`.

### 3. Dedicated Core Split (12 Triage Cores / 8 Deep Dive Cores)

* Allocating 12 cores to rapid triage means you can scan all 6,539 files in **under 3–4 hours**, creating an immediate "High Interest" list in `aivoicetagger_state.db` while your remaining 8 cores do full transcription in the background.

---

## 🟡 IMPORTANT REFINEMENTS & CORRECTIONS FOR YOUR CODEBASE

Before giving your AI coding assistant the instruction to implement this, there are **3 key technical adjustments** you must enforce so it integrates seamlessly with your existing Rust implementation:

### Adjustment 1: Smart Snippet Selection (Include High-RMS Spikes)

Don't *only* sample the first 60s and last 60s. If a file is 2 hours long, the argument might happen in minute 45.

* **Refinement:** During `decoder.rs` probing, check energy spikes! Sample:

1. First 60 seconds
2. Last 60 seconds
3. Smart pick on long files, around **The 30-second window with the highest RMS audio energy** (where shouting/loud voices occur).

### Adjustment 2: Symphonia Audio Seeking in `decoder.rs`

In Rust, decoding *only* specific snippets requires seeking in `symphonia` rather than decoding the whole file to PCM.

* Ensure `decoder.rs` uses `format.seek()` to jump straight to byte/sample offsets for snippet extraction, avoiding reading the entire file into RAM.

### Adjustment 3: Align with your Existing 3-Layer Concurrency Architecture

Because you are running two worker machines (`pc-alpha` and `pc-beta`) on a shared SQLite database (`\\SyNAS\Records\aivoicetagger_state.db`), the Triage result should be saved directly as a new state in `models.rs` and `state.rs`:

* Add states to `RecordState`: `TRIAGED_LOW_INTEREST` and `TRIAGED_HIGH_INTEREST`.
* Both `pc-alpha` and `pc-beta` can run Triage Mode concurrently using atomic ticket leases!

---

## 🚀 IMPLEMENTATION PROMPT FOR YOUR AI CODING ASSISTANT

Give the following prompt to your AI assistant (Cursor / Claude / GPT) to update your codebase:

```markdown
# Role & Task
You are a Principal Rust Engineer optimizing **AiVoiceTagger**. 
Implement a **3-Stage Triage Engine** to rapidly categorize 6,539 audio files (488 GB) by performing lightweight keyword spotting before committing heavy CPU cycles to full transcription.

---

## ─── 1. Models & State Store Update (`src/models.rs` & `src/state.rs`) ───

1. **New States (`models.rs`):**
   Add `TriagedLowInterest` and `TriagedHighInterest` to `RecordState`.
2. **Database Schema (`state.rs`):**
   Add a column `triage_keywords_json TEXT` to the `records` table.

---

## ─── 2. Fast Snippet Extractor (`src/decoder.rs`) ───

Implement `extract_triage_snippets(path, duration_secs) -> Vec<AudioChunk>`:
- If `duration_secs <= 90.0`, return the entire audio PCM.
- If `duration_secs > 90.0`, seek and extract exactly 3 audio snippets:
  1. **Start:** `0.0s .. 30.0s`
  2. **End:** `(duration - 30.0s) .. duration`
  3. **Peak RMS:** The 30-second window containing the highest RMS audio energy.

---

## ─── 3. Triage STT Worker (`src/stt.rs` & `src/pipeline.rs`) ───

1. **Triage Whisper Pool:**
   Initialize a secondary, ultra-lightweight Whisper pool using `models/ggml-tiny-q8_0.bin` (or `ggml-base-q8_0.bin`) with `beam_size = 1`, `temperature = 0.0`, and `no_context = true`.
2. **Watchlist Keyword Matcher:**
   Load watchlist terms from `config.yaml` (`harcèlement`, `menace`, `insulte`, `avocat`, `tribunal`, `police`, `argent`, `preuve`, `justice`).
3. **Execution Logic (`pipeline.rs`):**
   - Step A: Extract 3 snippets for claimed record.
   - Step B: Run `ggml-tiny` transcription on snippets.
   - Step C: Check text against French watchlists.
   - **If Match Found:** Set state to `TriagedHighInterest`, store matched keywords in `triage_keywords_json`, and queue for full STT transcription.
   - **If No Match:** Set state to `TriagedLowInterest` and skip full heavy transcription pass.

---

## ─── 4. CLI Controls (`src/main.rs`) ───

Add a CLI flag `--triage-only` to allow running worker nodes strictly in high-speed Triage Mode across all files before running full transcription passes.

```

---

### 📊 Expected Impact

* **Triage Pass Speed:** **10–15 seconds per file** (instead of 3–5 minutes).
* **Entire 6,539 File Collection Processed:** **~3 to 4 hours** total across 2 machines.
* **CPU Cycle Savings:** **~85% reduction** in total processing compute!
