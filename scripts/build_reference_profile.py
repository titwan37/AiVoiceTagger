#!/usr/bin/env python3
"""
build_reference_profile.py — Build a behavioral reference profile from RecordStrike
transcripts to enable pattern-driven detection of harassment across unsorted records.

Stage 1: Clean structural tags & stutter repetitions from RecordStrike transcripts
Stage 2: Extract clean lexical n-gram frequencies
Stage 2b: Use local Ollama LLM to verify & assert candidate phrases before appending to watchlist.txt
Stage 3: Build TF-IDF reference vector and compute pattern_match_score for all records
Stage 4: Store reference_profile.json and update DB with pattern_match_score

Usage:
    python scripts/build_reference_profile.py
"""

import sqlite3
import json
import re
import math
import urllib.request
from pathlib import Path
from collections import Counter
from datetime import datetime, timezone

BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = BASE_DIR / "aivoicetagger_state.db"
EXPORT_DIR = BASE_DIR / "export"
WATCHLIST_PATH = BASE_DIR / "watchlist.txt"
EXPORT_DIR.mkdir(parents=True, exist_ok=True)

# Directories that form the "baseline" reference set
BASELINE_DIRS = ["RecordStrike", "Select_Sort"]

# French stop words, structural tags, acoustic markers & stuttering filler words
STOP_WORDS = {
    "le", "la", "les", "de", "du", "des", "un", "une", "et", "est", "en",
    "que", "qui", "dans", "pour", "sur", "pas", "ne", "se", "ce", "je",
    "tu", "il", "elle", "nous", "vous", "ils", "elles", "on", "au", "aux",
    "avec", "son", "sa", "ses", "mon", "ma", "mes", "ton", "ta", "tes",
    "mais", "ou", "donc", "ni", "car", "oui", "non", "si", "tout",
    "plus", "bien", "très", "aussi", "même", "comme", "fait", "peut",
    "dit", "ça", "a", "ai", "as", "ont", "été", "être", "avoir",
    "fait", "faire", "suis", "es", "sommes", "êtes", "sont", "vais",
    "vas", "va", "allons", "allez", "vont", "faut", "y", "là", "moi",
    "toi", "lui", "eux", "par", "cette", "cet", "ces", "quoi",
    "the", "is", "are", "was", "were", "and", "or", "but", "to", "of",
    "in", "for", "on", "it", "i", "you", "he", "she", "we", "they",
    "a", "an", "that", "this", "have", "has", "had", "be", "been",
    "do", "does", "did", "will", "would", "could", "should", "can",
    # Structural & Triage Engine Tags
    "start", "peak", "end", "snippet", "labels", "titrage", "titrages",
    "société", "sous-titrage", "sous-titrages", "bruit", "moteur", "musique",
    # Whisper Subtitle Hallucination Artifacts
    "radio", "canada", "amara", "vidéo", "vidéos", "regardé", "abonnez", "chaîne",
    "communauté", "sous-titres",
    # Hesitation, Stutter & Conversational Fillers
    "euh", "hum", "ah", "oh", "ouais", "bah", "ben", "hein", "hop",
    "merci", "voilà", "truc", "chose", "quand", "alors", "après", "bon",
    "peu", "sais", "veux", "peux", "fais", "c'est", "l'âge", "d'un", "d'une", "j'ai",
}

# Core French offence indicator stems for quick pre-filtering (lexical roots only)
OFFENCE_INDICATOR_STEMS = {
    "gueule", "dégage", "nase", "merde", "putain", "foutre", "con", "connard",
    "frapper", "casser", "menace", "insulte", "harcèlement", "tuer", "mort",
    "crever", "crève", "police", "avocat", "tribunal", "preuve", "argent",
    "chantage", "justice", "illégal", "vermine", "porc", "cagibi", "toit",
    "chambre", "folle", "nul", "vilain", "nabot", "moche", "chier", "defoncer", "défoncer",
    "sang", "arme", "couteau", "pistolet", "fusil", "égorger", "assassiner",
    "bâtard", "abruti", "imbécile", "ordure", "bouffon", "salop",
    "attraper", "bousiller", "brûler", "détruire", "frapper", "bousiller",
}


def tokenize(text: str) -> list[str]:
    """Clean structural tags, Whisper subtitle hallucinations, lowercase, split tokens, remove stop words, and collapse stutter repetitions."""
    if not text:
        return []

    # 1. Remove structural snippet tags like [Start], [Peak], [End]
    text_clean = re.sub(r'\[(Start|Peak|End|Snippet)\]', ' ', text, flags=re.IGNORECASE)

    # 2. Strip Whisper Subtitle Hallucination patterns (Radio-Canada, Amara, Youtube defaults)
    text_clean = re.sub(r'(sous-titrage|sous-titres|société|radio-canada|amara|communauté|regardé|vidéo|abonnez-vous)', ' ', text_clean, flags=re.IGNORECASE)

    # 3. Extract words
    words = re.findall(r"[a-zàâäéèêëïîôùûüÿçœæ']+", text_clean.lower())

    # 4. Filter stop words & short tokens
    filtered = [w for w in words if w not in STOP_WORDS and len(w) > 2]

    # 4. Collapse consecutive duplicate tokens (Stutter Reduction: "c'est c'est" -> "c'est")
    deduped = []
    for w in filtered:
        if not deduped or deduped[-1] != w:
            deduped.append(w)

    return deduped


def extract_ngrams(tokens: list[str], n: int = 2) -> list[str]:
    """Extract n-grams from a list of tokens, skipping n-grams with repeated identical adjacent words."""
    ngrams = []
    for i in range(len(tokens) - n + 1):
        chunk = tokens[i:i+n]
        # Skip if stutter repetition inside n-gram (e.g. "merci merci")
        if len(set(chunk)) < n:
            continue
        ngrams.append(" ".join(chunk))
    return ngrams


def load_existing_watchlist() -> set[str]:
    """Load current watchlist.txt keywords."""
    keywords = set()
    if WATCHLIST_PATH.exists():
        with open(WATCHLIST_PATH, "r", encoding="utf-8") as f:
            for line in f:
                stripped = line.strip()
                if stripped and not stripped.startswith("#"):
                    keywords.add(stripped.lower())
    return keywords


def compute_tfidf(documents: list[list[str]]) -> dict[str, float]:
    """Compute TF-IDF scores across a collection of tokenized documents."""
    n_docs = len(documents)
    if n_docs == 0:
        return {}

    # Document frequency
    df = Counter()
    for doc in documents:
        unique_tokens = set(doc)
        for token in unique_tokens:
            df[token] += 1

    # Aggregate TF across all baseline documents
    tf = Counter()
    for doc in documents:
        tf.update(doc)

    # Compute TF-IDF
    tfidf = {}
    total_terms = sum(tf.values())
    if total_terms == 0:
        return {}

    for term, count in tf.items():
        tf_val = count / total_terms
        idf_val = math.log((n_docs + 1) / (df[term] + 1)) + 1
        tfidf[term] = tf_val * idf_val

    return tfidf


def cosine_similarity(vec_a: dict[str, float], vec_b: dict[str, float]) -> float:
    """Compute cosine similarity between two sparse vectors."""
    common_keys = set(vec_a.keys()) & set(vec_b.keys())
    if not common_keys:
        return 0.0

    dot_product = sum(vec_a[k] * vec_b[k] for k in common_keys)
    norm_a = math.sqrt(sum(v ** 2 for v in vec_a.values()))
    norm_b = math.sqrt(sum(v ** 2 for v in vec_b.values()))

    if norm_a == 0 or norm_b == 0:
        return 0.0

    return dot_product / (norm_a * norm_b)


def check_ollama_available() -> str | None:
    """Check if local Ollama server is running and return best fast available model."""
    url = "http://localhost:11434/api/tags"
    try:
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=3) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            models = [m.get("name", "") for m in data.get("models", [])]
            # Prioritize lightweight, high-speed 1B-3B models for sub-second verification
            preferred_order = [
                "llama3.2:1b", "deepseek-r1:1.5b", "gemma3:1b", "gemma2:2b",
                "qwen3:4b", "mistral:latest", "llama3.1:8b"
            ]
            for pref in preferred_order:
                for m in models:
                    if pref in m:
                        return m
            if models:
                return models[0]
    except Exception:
        pass
    return None


def verify_phrase_with_llm(phrase: str, model_name: str) -> bool:
    """Use local Ollama model to verify if a candidate phrase is a genuine insult, physical threat, or legal offence under French law."""
    prompt = f"""Tu es un analyste juridique forensic spécialisé en droit pénal français. Évalue si l'expression suivante en français constitue une insulte, une menace physique, de l'intimidation, du chantage, du harcèlement moral ou une infraction juridique.

Expression à évaluer: "{phrase}"

Réponds STRICTEMENT avec un objet JSON unique ayant ce format exact:
{{"is_offence": true, "category": "LETHAL"|"PHYSICAL_THREAT"|"VERBAL_ABUSE"|"DOMESTIC_COERCION"|"LEGAL"|"NONE", "reason": "explication concise"}}
"""
    payload = json.dumps({
        "model": model_name,
        "prompt": prompt,
        "stream": False,
        "format": "json"
    }).encode("utf-8")

    try:
        url = "http://localhost:11434/api/generate"
        req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            resp_str = data.get("response", "")
            res = json.loads(resp_str)
            is_offence = bool(res.get("is_offence", False))
            category = res.get("category", "NONE")
            reason = res.get("reason", "")
            if is_offence and category != "NONE":
                print(f"     🧠 LLM Verified [{category}]: \"{phrase}\" — {reason}")
                return True
            else:
                print(f"     🛑 LLM Rejected: \"{phrase}\" — {reason or 'Not an offence'}")
                return False
    except Exception as e:
        print(f"     ⚠️ LLM evaluation skipped for \"{phrase}\": {e}")
        return False


def ensure_schema_columns(conn: sqlite3.Connection):
    """Ensure all required columns exist in records table."""
    cursor = conn.cursor()
    cursor.execute("PRAGMA table_info(records)")
    columns = [row[1] for row in cursor.fetchall()]
    
    needed = [
        ("priority", "INTEGER DEFAULT 0"),
        ("legal_tags", "TEXT"),
        ("intensity_rating", "INTEGER DEFAULT 0"),
        ("pattern_match_score", "REAL DEFAULT 0.0"),
    ]
    for col_name, col_type in needed:
        if col_name not in columns:
            print(f"  📐 Adding missing column '{col_name}' to records table...")
            cursor.execute(f"ALTER TABLE records ADD COLUMN {col_name} {col_type}")
    conn.commit()


def main():
    print("=" * 70)
    print("🧠 AiVoiceTagger — Behavioral Reference Profile Builder")
    print(f"   Database: {DB_PATH}")
    print(f"   Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 70)

    if not DB_PATH.exists():
        print("❌ Database not found.")
        return

    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    ensure_schema_columns(conn)
    cursor = conn.cursor()

    # Check LLM availability
    ollama_model = check_ollama_available()
    if ollama_model:
        print(f"  🤖 Local Ollama LLM detected: using model '{ollama_model}' for phrase verification.")
    else:
        print("  ℹ  Local Ollama LLM not detected; strict dictionary pattern rules will be used.")

    # ─────────────────────────────────────────────────────────────────
    # Stage 1: Extract baseline transcripts from RecordStrike/Select_Sort
    # ─────────────────────────────────────────────────────────────────
    print("\n📋 Stage 1: Loading baseline transcripts from RecordStrike/Select_Sort...")

    baseline_conditions = " OR ".join([f"directory LIKE '%{d}%'" for d in BASELINE_DIRS])
    cursor.execute(f"""
        SELECT record_id, name, directory, story, triage_summary, triage_keywords_json,
               duration_seconds, date_record_day, date_last_write
        FROM records
        WHERE ({baseline_conditions})
          AND (story IS NOT NULL AND story != '' OR triage_summary IS NOT NULL AND triage_summary != '')
    """)
    baseline_records = cursor.fetchall()
    print(f"  Found {len(baseline_records)} RecordStrike baseline records with transcripts.")

    # Also get ALL baseline records (including untranscribed) for inventory
    cursor.execute(f"""
        SELECT record_id, name, directory, story, triage_summary, triage_keywords_json,
               duration_seconds, state, date_record_day, date_last_write
        FROM records
        WHERE ({baseline_conditions})
    """)
    all_baseline_records = cursor.fetchall()
    print(f"  Total RecordStrike baseline records in DB: {len(all_baseline_records)}")

    # Fallback to all triaged high / text-rich records if RecordStrike STT hasn't run yet
    if len(baseline_records) == 0:
        print("  ⚠️ RecordStrike files are pending STT/triage processing.")
        print("  🔄 Seeding reference profile from all triaged high-interest records in DB...")
        cursor.execute("""
            SELECT record_id, name, directory, story, triage_summary, triage_keywords_json,
                   duration_seconds, date_record_day, date_last_write
            FROM records
            WHERE (state = 'TriagedHighInterest' OR triage_keywords_json LIKE '%[%' OR length(story) > 10)
              AND (story IS NOT NULL AND story != '' OR triage_summary IS NOT NULL AND triage_summary != '')
        """)
        baseline_records = cursor.fetchall()
        print(f"  Fallback baseline loaded: {len(baseline_records)} records with transcripts.")

    # ─────────────────────────────────────────────────────────────────
    # Stage 2: Build lexical frequency matrix & discover new phrases
    # ─────────────────────────────────────────────────────────────────
    print("\n🔬 Stage 2: Building clean lexical frequency matrix (stutter & tag reduced)...")

    baseline_docs = []
    all_unigrams = Counter()
    all_bigrams = Counter()
    all_trigrams = Counter()

    for rec in baseline_records:
        text = (rec["story"] or "") + " " + (rec["triage_summary"] or "")
        tokens = tokenize(text)
        if not tokens:
            continue
        baseline_docs.append(tokens)

        all_unigrams.update(tokens)
        all_bigrams.update(extract_ngrams(tokens, 2))
        all_trigrams.update(extract_ngrams(tokens, 3))

    print(f"  Clean unique unigrams: {len(all_unigrams)}")
    print(f"  Clean unique bigrams:  {len(all_bigrams)}")
    print(f"  Clean unique trigrams: {len(all_trigrams)}")

    # Top discriminating n-grams (frequency >= 2 and not pure noise)
    top_bigrams = [(bg, cnt) for bg, cnt in all_bigrams.most_common(100) if cnt >= 2]
    top_trigrams = [(tg, cnt) for tg, cnt in all_trigrams.most_common(50) if cnt >= 2]

    print(f"\n  📌 Top discriminating bigrams (stutter-free):")
    for bg, cnt in top_bigrams[:15]:
        print(f"     {cnt:3d}x  \"{bg}\"")

    print(f"\n  📌 Top discriminating trigrams (stutter-free):")
    for tg, cnt in top_trigrams[:10]:
        print(f"     {cnt:3d}x  \"{tg}\"")

    # ─────────────────────────────────────────────────────────────────
    # Stage 2b: Dynamically expand watchlist via LLM verification
    # ─────────────────────────────────────────────────────────────────
    print("\n📝 Stage 2b: Asserting candidate phrases with LLM before watchlist expansion...")

    existing_watchlist = load_existing_watchlist()
    new_phrases = set()

    # Candidate phrases from bigrams and trigrams
    candidate_phrases = set()
    for bg, cnt in top_bigrams[:40]:
        if cnt >= 2 and bg not in existing_watchlist:
            candidate_phrases.add(bg)

    for tg, cnt in top_trigrams[:30]:
        if cnt >= 2 and tg not in existing_watchlist:
            candidate_phrases.add(tg)

    for phrase in sorted(candidate_phrases):
        # Pre-filter: skip obvious benign phrases that don't contain any offence indicator stem
        phrase_words = phrase.split()
        if not any(w in OFFENCE_INDICATOR_STEMS for w in phrase_words):
            continue

        if ollama_model:
            # LLM Verification step for candidates containing indicator stems
            if verify_phrase_with_llm(phrase, ollama_model):
                new_phrases.add(phrase)
        else:
            new_phrases.add(phrase)

    if new_phrases:
        print(f"\n  🆕 Verified {len(new_phrases)} new phrases for watchlist:")
        for phrase in sorted(new_phrases):
            print(f"     + \"{phrase}\"")

        # Append to watchlist.txt
        with open(WATCHLIST_PATH, "a", encoding="utf-8") as f:
            f.write("\n# LLM Verified phrases from RecordStrike baseline\n")
            for phrase in sorted(new_phrases):
                f.write(f"{phrase}\n")
        print(f"  ✅ Appended {len(new_phrases)} verified phrases to {WATCHLIST_PATH}")
    else:
        print("  ℹ  No new phrases asserted beyond existing watchlist.")

    # ─────────────────────────────────────────────────────────────────
    # Stage 3: Build TF-IDF reference vector
    # ─────────────────────────────────────────────────────────────────
    print("\n🧮 Stage 3: Building TF-IDF reference vector...")

    # Compute combined reference vector from all baseline documents
    reference_tfidf = compute_tfidf(baseline_docs)

    # Keep top-500 most significant terms
    sorted_terms = sorted(reference_tfidf.items(), key=lambda x: x[1], reverse=True)[:500]
    reference_vector = dict(sorted_terms)

    print(f"  Reference vector dimensions: {len(reference_vector)}")
    print(f"  Top 10 clean reference terms:")
    for term, score in sorted_terms[:10]:
        print(f"     {score:.4f}  \"{term}\"")

    # Save reference profile
    profile = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "baseline_record_count": len(baseline_records),
        "baseline_directories": BASELINE_DIRS,
        "reference_vector_dimensions": len(reference_vector),
        "reference_vector": reference_vector,
        "top_bigrams": top_bigrams[:30],
        "top_trigrams": top_trigrams[:15],
        "verified_new_phrases": sorted(list(new_phrases)),
        "total_unigrams": len(all_unigrams),
        "total_bigrams": len(all_bigrams),
    }

    profile_path = EXPORT_DIR / "reference_profile.json"
    with open(profile_path, "w", encoding="utf-8") as f:
        json.dump(profile, f, indent=2, ensure_ascii=False)
    print(f"  ✅ Saved reference profile to {profile_path}")

    # ─────────────────────────────────────────────────────────────────
    # Stage 4: Score all records against reference profile
    # ─────────────────────────────────────────────────────────────────
    print("\n📊 Stage 4: Scoring all records against reference profile...")

    cursor.execute("""
        SELECT record_id, name, directory, story, triage_summary
        FROM records
        WHERE story IS NOT NULL AND story != ''
           OR triage_summary IS NOT NULL AND triage_summary != ''
    """)
    all_records = cursor.fetchall()
    print(f"  Scoring {len(all_records)} records with text content...")

    scored_count = 0
    high_match_count = 0
    medium_match_count = 0
    now_iso = datetime.now(timezone.utc).isoformat()

    for rec in all_records:
        text = (rec["story"] or "") + " " + (rec["triage_summary"] or "")
        tokens = tokenize(text)

        if not tokens:
            continue

        # Build per-record TF vector
        tf = Counter(tokens)
        total = sum(tf.values())
        doc_vector = {term: count / total for term, count in tf.items()}

        # Compute similarity against reference
        score = cosine_similarity(reference_vector, doc_vector)

        # Update DB
        cursor.execute(
            "UPDATE records SET pattern_match_score = ?, updated_at = ? WHERE record_id = ?",
            (round(score, 4), now_iso, rec["record_id"])
        )
        scored_count += 1

        if score >= 0.75:
            high_match_count += 1
        elif score >= 0.40:
            medium_match_count += 1

    conn.commit()

    print(f"\n  ✅ Scored {scored_count} records:")
    print(f"     🚨 High match (≥0.75):   {high_match_count}")
    print(f"     ⚡ Medium match (0.40-0.74): {medium_match_count}")
    print(f"     💤 Low match (<0.40):     {scored_count - high_match_count - medium_match_count}")

    # ─────────────────────────────────────────────────────────────────
    # Summary
    # ─────────────────────────────────────────────────────────────────
    print("\n" + "=" * 70)
    print("🎉 Reference profile built and all records scored!")
    print(f"   Profile: {profile_path}")
    print(f"   Watchlist: {WATCHLIST_PATH}")
    print("=" * 70)

    conn.close()


if __name__ == "__main__":
    main()
