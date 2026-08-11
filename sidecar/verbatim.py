import re
from typing import List, Dict
from models import StatsVerbatim, RecordInfo

# 87 Consolidated Keywords organized into 6 Watch Categories
# ----------------------------------------------------------------------

# 1. WATCH_LETHAL — High-Risk Physical Violence & Lethal Threats
WATCH_LETHAL = [
    "arme", "assassiner", "cadavre", "couteau", "crever", "crève",
    "égorger", "fusil", "meurtre", "mort", "pistolet", "sang",
    "suicide", "suicider", "tu vas mourir", "tuer"
]

# 2. WATCH_PHYSICAL_THREATS — Physical Coercion & Assault Intent
WATCH_PHYSICAL_THREATS = [
    "attaque", "attraper", "bousiller", "brûler", "casser",
    "casser la gueule", "défoncer", "détruire", "faire payer", "frapper",
    "je vais te defoncer", "je vais te faire", "menace", "menacer",
    "pas fini avec toi", "retrouver", "tu va voir", "tu vas voir ta gueule",
    "éclater"
]

# 3. WATCH_VERBAL_ABUSE — Insults, Invective & Verbal Degradation
WATCH_VERBAL_ABUSE = [
    "abruti", "blanc bec", "bouffon", "bâtard", "casse-toi", "con",
    "connard", "dégage", "enculé", "gros nase", "gros porc", "imbécile",
    "insulte", "merde", "ordure", "porc", "putain", "pute", "sale",
    "sale blanc bec", "salop", "t'es moche", "t'es nul",
    "t'es un gros nul", "t'es vilain", "ta gueule", "un gros nase",
    "va chier", "va te faire foutre", "vermine"
]

# 4. WATCH_DOMESTIC_COERCION — Domicile Infringement, Isolation & Coercive Control
WATCH_DOMESTIC_COERCION = [
    "argent", "cagibi", "chambre", "chantage", "harcèlement",
    "mon frère"
]

# 5. WATCH_LEGAL_PROCEDURAL — Judicial Intervention, Law Enforcement & Evidence
WATCH_LEGAL_PROCEDURAL = [
    "avocat", "commissariat", "gendarmerie", "huissier", "juge",
    "juridique", "justice", "loi", "plainte", "police", "prison",
    "procès", "tribunal"
]

# 6. WATCH_EVIDENCE_INTEGRITY — Tampering, Illegality & Proof
WATCH_EVIDENCE_INTEGRITY = [
    "illégal", "preuve"
]

WATCHLIST_CATEGORIES: Dict[str, List[str]] = {
    "WATCH_LETHAL": WATCH_LETHAL,
    "WATCH_PHYSICAL_THREATS": WATCH_PHYSICAL_THREATS,
    "WATCH_VERBAL_ABUSE": WATCH_VERBAL_ABUSE,
    "WATCH_DOMESTIC_COERCION": WATCH_DOMESTIC_COERCION,
    "WATCH_LEGAL_PROCEDURAL": WATCH_LEGAL_PROCEDURAL,
    "WATCH_EVIDENCE_INTEGRITY": WATCH_EVIDENCE_INTEGRITY,
}


def compile_pattern(word: str) -> re.Pattern:
    """Compile regex pattern for exact phrase or stemmed word match."""
    escaped = re.escape(word)
    if " " in word or "'" in word:
        return re.compile(escaped, re.IGNORECASE)
    return re.compile(r'\b' + escaped + r'\w*', re.IGNORECASE)


class VerbatimAnalyzer:
    def __init__(self):
        self.category_patterns = {
            cat: [compile_pattern(w) for w in words]
            for cat, words in WATCHLIST_CATEGORIES.items()
        }

    def analyze_text(self, text: str) -> StatsVerbatim:
        stats = StatsVerbatim()
        occurrences = []

        if not text:
            return stats

        # 1. WATCH_LETHAL
        for p in self.category_patterns["WATCH_LETHAL"]:
            matches = p.findall(text)
            stats.count_lethal += len(matches)
            occurrences.extend(matches)

        # 2. WATCH_PHYSICAL_THREATS
        for p in self.category_patterns["WATCH_PHYSICAL_THREATS"]:
            matches = p.findall(text)
            stats.count_physical_threats += len(matches)
            occurrences.extend(matches)

        # 3. WATCH_VERBAL_ABUSE
        for p in self.category_patterns["WATCH_VERBAL_ABUSE"]:
            matches = p.findall(text)
            stats.count_verbal_abuse += len(matches)
            occurrences.extend(matches)

        # 4. WATCH_DOMESTIC_COERCION
        for p in self.category_patterns["WATCH_DOMESTIC_COERCION"]:
            matches = p.findall(text)
            stats.count_domestic_coercion += len(matches)
            occurrences.extend(matches)

        # 5. WATCH_LEGAL_PROCEDURAL
        for p in self.category_patterns["WATCH_LEGAL_PROCEDURAL"]:
            matches = p.findall(text)
            stats.count_legal_procedural += len(matches)
            occurrences.extend(matches)

        # 6. WATCH_EVIDENCE_INTEGRITY
        for p in self.category_patterns["WATCH_EVIDENCE_INTEGRITY"]:
            matches = p.findall(text)
            stats.count_evidence_integrity += len(matches)
            occurrences.extend(matches)

        # Legacy backward-compatibility mappings
        stats.count_menaces = stats.count_physical_threats
        stats.count_insultes = stats.count_verbal_abuse + stats.count_domestic_coercion
        stats.count_legal = stats.count_legal_procedural + stats.count_evidence_integrity

        stats.occurrences = list(set([o.lower() for o in occurrences]))
        return stats

    def analyze_record(self, record: RecordInfo) -> RecordInfo:
        text = record.story
        if not text and record.speeches:
            text = " ".join(s.script for s in record.speeches)

        record.stats_verbatim = self.analyze_text(text)
        return record
