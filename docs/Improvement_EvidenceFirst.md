## Executive Architectural Brief

To transform **AiVoiceTagger** into a high-precision, pattern-driven engine for legal evidence collection, you can implement a **Few-Shot Behavioral Pattern Transfer Pipeline**.

By leveraging your pre-selected files in `RecordStrike` as a ground-truth reference baseline, the system can extract acoustic, lexical, and psychological patterns. It can then apply these metrics across the remaining candidate pool to automatically detect undetected harassment events across your multi-year timeline.

---

## Technical Strategy: 3-Stage Pipeline Upgrade

```
┌────────────────────────────────────────────────────────────────────────┐
│ STAGE 1: Template & Model Building (RecordStrike Calibration)         │
│ • Extract lexical clusters, prosodic markers & speaker profiles        │
│ • Build dynamic target vector embeddings                               │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │ Reference Signature
┌───────────────────────────────────▼────────────────────────────────────┐
│ STAGE 2: Accelerated Similarity Scanning                           │
│ • Run fast triage model (ggml-tiny) across unseen records               │
│ • Compute cosine distance against baseline profile                     │
│ • Promote high-confidence matches to full transcription pipeline       │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │ Matched High-Interest Candidates
┌───────────────────────────────────▼────────────────────────────────────┐
│ STAGE 3: Legal-Grade Synthesis & Chronological Timeline Assembly       │
│ • Quantify harassment escalation metrics (intensity x frequency x time) │
│ • Tag legal offenses under French penal code framework                 │
└────────────────────────────────────────────────────────────────────────┘

```

---

## Enhanced System Prompt Template

You can feed this prompt to your Python sidecar module (or directly to your primary LLM processing layer) to process raw transcriptions against your baseline patterns.

```markdown
# SYSTEM PROMPT: LEGAL EVIDENCE EXTRACTOR & BEHAVIORAL PATTERN TRANSFER ENGINE

## CONTEXT & ROLE
You are an expert legal tech forensic analyst specializing in domestic violence and moral harassment under French penal law (e.g., Articles 222-33-2-1 and 222-14-3 of the Code Pénal). Your task is to process transcribed audio records, compare them against a baseline set of pre-validated harassment templates ("RecordStrike"), and identify, categorize, and quantify harassment and intimidation patterns across a multi-year timeframe.

---

## INPUT DATA STRUCTURE
You will receive JSON payloads containing:
1. `record_metadata`: ID, timestamp, file path, duration, and speaker diarization labels.
2. `raw_transcript`: Full text transcription with segment-level timestamps.
3. `reference_patterns`: Dynamic vector/lexical signatures derived from the `RecordStrike` baseline folder.

---

## EVALUATION FRAMEWORK & LEGAL QUALIFICATION
For each input record, evaluate against the following legal criteria:

### 1. Moral Harassment & Psychological Abuse (Code Pénal Art. 222-33-2-1)
* **Target Behaviours:** Continuous degradation of living conditions, repetitive insult loops, humiliation, isolation, sleep disruption, or persistent verbal degradation.
* **Lexical Markers:** Repeated profanities, derogatory insults, invalidation of personal rights (e.g., *"ta gueule"*, *"un gros nase"*, *"vermine"*, *"tu dégages"*).

### 2. Intimidation, Physical Threats & Coercion (Code Pénal Art. 222-14-3)
* **Target Behaviours:** Direct or indirect threats of physical violence, threats involving third parties/relatives, property destruction, or forced entry/boundary violations.
* **Lexical Markers:** Threats of physical harm, destruction of property, third-party escalation (e.g., *"je vais te casser la gueule"*, *"je fais venir mon frère"*, *"table basse renversée"*).

### 3. Financial Harassment & Domestic Coercive Control
* **Target Behaviours:** Financial blackmail, unauthorized appropriation of property, forced financial restitution under duress, denial of access to shared spaces.
* **Lexical Markers:** Unilateral demands for money, threats regarding housing access (e.g., *"je dicte ma loi sous ton toit"*, *"volige sous mon toit"*).

### 4. Legal Retaliation & Evidence Tampering Interference
* **Target Behaviours:** Intimidation regarding law enforcement/lawyer contact, attempts to prevent or penalize evidence collection.
* **Lexical Markers:** Mocking recording efforts, threats regarding police or judicial intervention.

---

## PROCESSING INSTRUCTIONS

### Step 1: Baseline Similarity Scoring
Calculate a `Pattern_Match_Score` (0.0 to 1.0) by matching the record's transcription, acoustic intensity, and lexical choices against the signatures in `RecordStrike`:
* **High Similarity (≥ 0.75):** Promote to `Priority Legal Evidence`.
* **Medium Similarity (0.40 - 0.74):** Tag for manual review / secondary pass.
* **Low Similarity (< 0.40):** Archive as background context.

### Step 2: Chronological Escalation Indexing
Extract or infer the precise date/time. Assign an `Intensity_Rating` (1 to 10) based on:
* Loudness/RMS peak energy markers.
* Frequency of explicit threat keywords.
* Presence of physical degradation indicators.

### Step 3: Legal Fact Extraction
Generate a structured report for each identified high-interest record.

---

## REQUIRED OUTPUT FORMAT (JSON)

```json
{
  "record_id": "string",
  "pattern_match_score": 0.88,
  "legal_qualification": [
    "Harcèlement Moral (Art. 222-33-2-1)",
    "Menaces de Violences (Art. 222-14-3)"
  ],
  "intensity_rating": 8,
  "verbatim_evidence": [
    {
      "timestamp_start": "00:01:15",
      "timestamp_end": "00:01:28",
      "speaker": "SPEAKER_01",
      "transcription_verbatim": "Exact text quote here",
      "matched_keyword": "casser la gueule",
      "legal_relevance": "Direct threat of physical assault."
    }
  ],
  "contextual_summary": "Brief factual summary of the incident without emotional language, formatted for court submission.",
  "escalation_marker": true
}

```

```

---

## Recommended Integration into your `AiVoiceTagger` Pipeline

To execute this pattern transfer in your current Rust/Python stack:

### 1. Build the Reference Profile (`RecordStrike`)
Run a script over `RecordStrike` to compile a baseline key-phrase frequency matrix and embedding vector. Store these signatures in SQLite:

```bash
# Export the baseline vocabulary and acoustic features from RecordStrike
cargo run --release -- --from-csv export/TriagedHighInterest.csv --triage-only

```

### 2. Update `watchlist.txt` Dynamics

Expand your active watchlist dynamically by parsing key phrases from the `RecordStrike` transcripts:

```text
# Dynamically extracted from RecordStrike baseline
mon frère
table basse
sous mon toit
mon droit à moi
te mettre à terre
la claque de ta vie
insults non stop

```

### 3. Aggregate for Chronological Reporting

Use Polars in your Python sidecar to build a continuous temporal trajectory showing the accumulation of events over time:

```python
import polars as pl

# Generate temporal density and legal intensity matrix
df = pl.read_json("export/TriagedHighInterest.json")
timeline = (
    df.lazy()
    .groupby_dynamic("date_record_day", every="1m")
    .agg([
        pl.count("record_id").alias("incident_count"),
        pl.col("intensity_rating").mean().alias("avg_intensity"),
        pl.col("matched_keywords").explode().unique().alias("pattern_diversity")
    ])
    .collect()
)

```

This approach allows you to train the system using the pre-selected `RecordStrike` baseline, scan through the remaining unsorted records, and organize the extracted evidence into a clear, chronological structure suitable for legal review.

---

```python
legacy_lists = {
    "WATCH_LETHAL": ["tuer", "mort", "meurtre", "suicide", "suicider", "sang", "cadavre", "arme", "couteau", "pistolet", "fusil", "crever", "égorger", "assassiner"],
    "WATCH_LEGAL": ["police", "avocat", "tribunal", "plainte", "juge", "procès", "prison", "gendarmerie", "justice", "commissariat", "juridique", "loi", "huissier"],
    "WATCH_MENACES": ["menace", "menacer", "frapper", "casser", "détruire", "brûler", "retrouver", "attraper", "défoncer", "bousiller", "éclater", "faire payer"],
    "WATCH_INSULTES": ["con", "connard", "salop", "salope", "pute", "enculé", "putain", "merde", "bâtard", "abruti", "imbécile", "ordure", "bouffon"]
}

yaml_keywords = [
    "harcèlement", "chambre", "cagibi", "menace", "insulte", "avocat", "police", "tribunal",
    "argent", "preuve", "justice", "chantage", "dégage", "casse-toi", "illégal", "police",
    "va te faire foutre", "va chier", "t'es nul", "un gros nase", "ta gueule", "gros porc",
    "vermine", "gros nase", "sale blanc bec", "casser la gueule", "mon frère"
]

txt_keywords = [
    "harcèlement", "menace", "insulte", "avocat", "police", "tribunal", "argent", "preuve",
    "justice", "chantage", "dégage", "attaque", "va chier", "va te faire foutre", "un gros nase",
    "ta gueule", "t'es nul", "t'es un gros nul", "t'es moche", "t'es vilain", "harcèlement",
    "chambre", "cagibi", "menace", "insulte", "avocat", "police", "tribunal", "argent", "preuve",
    "justice", "chantage", "dégage", "casse-toi", "illégal", "police", "va te faire foutre",
    "va chier", "t'es nul", "porc", "gros porc", "un gros nase", "ta gueule", "vermine",
    "sale", "blanc bec", "sale blanc bec", "cagibi", "casser la gueule", "mon frère",
    "pas fini avec toi", "tu va voir", "je vais te faire", "je vais te defoncer",
    "tu vas voir ta gueule", "tu vas mourir", "crève"
]

all_terms = set()
for l in legacy_lists.values():
    all_terms.update(l)
all_terms.update(yaml_keywords)
all_terms.update(txt_keywords)

# Clean up whitespace
all_terms = {t.strip() for t in all_terms if t.strip()}

print(f"Total Unique Keywords: {len(all_terms)}")
print(sorted(list(all_terms)))


```

```text
Total Unique Keywords: 87
['abruti', 'argent', 'arme', 'assassiner', 'attaque', 'attraper', 'avocat', 'blanc bec', 'bouffon', 'bousiller', 'brûler', 'bâtard', 'cadavre', 'cagibi', 'casse-toi', 'casser', 'casser la gueule', 'chambre', 'chantage', 'commissariat', 'con', 'connard', 'couteau', 'crever', 'crève', 'défoncer', 'dégage', 'détruire', 'enculé', 'faire payer', 'frapper', 'fusil', 'gendarmerie', 'gros nase', 'gros porc', 'harcèlement', 'huissier', 'illégal', 'imbécile', 'insulte', 'je vais te defoncer', 'je vais te faire', 'juge', 'juridique', 'justice', 'loi', 'menace', 'menacer', 'merde', 'meurtre', 'mon frère', 'mort', 'ordure', 'pas fini avec toi', 'pistolet', 'plainte', 'police', 'porc', 'preuve', 'prison', 'procès', 'putain', 'pute', 'retrouver', 'sale', 'sale blanc bec', 'salop', 'salope', 'sang', 'suicide', 'suicider', "t'es moche", "t'es nul", "t'es un gros nul", "t'es vilain", 'ta gueule', 'tribunal', 'tu va voir', 'tu vas mourir', 'tu vas voir ta gueule', 'tuer', 'un gros nase', 'va chier', 'va te faire foutre', 'vermine', 'éclater', 'égorger']


```

Here is a structured consolidation of all **87 unique keywords** extracted across your legacy code, `config.yaml`, and `watchlist.txt`.

To optimize pattern recognition for legal triage and domestic harassment evidence, the terms have been organized into **6 cohesive, non-overlapping Watch Categories**.

---

## 🏷️ Proposed Watch Categories & Keyword Mapping

### 1. `WATCH_LETHAL` — High-Risk Physical Violence & Lethal Threats

> **Legal Focus:** Death threats, weapon references, severe physical harm (Code Pénal Art. 222-14-3 / Art. 221-1).

```python
WATCH_LETHAL = [
    "arme", "assassiner", "cadavre", "couteau", "crever", "crève", 
    "égorger", "fusil", "meurtre", "mort", "pistolet", "sang", 
    "suicide", "suicider", "tu vas mourir", "tuer"
]

```

---

## 2. `WATCH_PHYSICAL_THREATS` — Physical Coercion & Assault Intent

> **Legal Focus:** Intimidation, physical battery, threats of violence, property destruction.

```python
WATCH_PHYSICAL_THREATS = [
    "attaque", "attraper", "bousiller", "brûler", "casser", 
    "casser la gueule", "défoncer", "détruire", "faire payer", "frapper", 
    "je vais te defoncer", "je vais te faire", "menace", "menacer", 
    "pas fini avec toi", "retrouver", "tu va voir", "tu vas voir ta gueule", 
    "éclater"
]

```

---

## 3. `WATCH_VERBAL_ABUSE` — Insults, Invective & Verbal Degradation

> **Legal Focus:** Systematic verbal abuse, moral degradation, insults, vulgarities (Code Pénal Art. 222-33-2-1).

```python
WATCH_VERBAL_ABUSE = [
    "abruti", "blanc bec", "bouffon", "bâtard", "casse-toi", "con", 
    "connard", "dégage", "enculé", "gros nase", "gros porc", "imbécile", 
    "insulte", "merde", "ordure", "porc", "putain", "pute", "sale", 
    "sale blanc bec", "salop", "salope", "t'es moche", "t'es nul", 
    "t'es un gros nul", "t'es vilain", "ta gueule", "un gros nase", 
    "va chier", "va te faire foutre", "vermine"
]

```

---

## 4. `WATCH_DOMESTIC_COERCION` — Domicile Infringement, Isolation & Coercive Control

> **Legal Focus:** Invasion of private space inside the home, financial intimidation, blackmail, third-party escalation.

```python
WATCH_DOMESTIC_COERCION = [
    "argent", "cagibi", "chambre", "chantage", "harcèlement", 
    "mon frère"
]

```

---

## 5. `WATCH_LEGAL_PROCEDURAL` — Judicial Intervention, Law Enforcement & Evidence

> **Legal Focus:** Statements regarding legal action, reporting, police, courts, or rights.

```python
WATCH_LEGAL_PROCEDURAL = [
    "avocat", "commissariat", "gendarmerie", "huissier", "juge", 
    "juridique", "justice", "loi", "plainte", "police", "prison", 
    "procès", "tribunal"
]

```

---

## 6. `WATCH_EVIDENCE_INTEGRITY` — Tampering, Illegality & Proof

> **Legal Focus:** References to proof, recordings, or legal violations.

```python
WATCH_EVIDENCE_INTEGRITY = [
    "illégal", "preuve"
]

```

---

## 📋 Consolidated Python Dictionary Strategy

For integration into your Python sidecar or data pipeline:

```python
WATCHLIST_CATEGORIES = {
    "WATCH_LETHAL": WATCH_LETHAL,
    "WATCH_PHYSICAL_THREATS": WATCH_PHYSICAL_THREATS,
    "WATCH_VERBAL_ABUSE": WATCH_VERBAL_ABUSE,
    "WATCH_DOMESTIC_COERCION": WATCH_DOMESTIC_COERCION,
    "WATCH_LEGAL_PROCEDURAL": WATCH_LEGAL_PROCEDURAL,
    "WATCH_EVIDENCE_INTEGRITY": WATCH_EVIDENCE_INTEGRITY,
}

```
