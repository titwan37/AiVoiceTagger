import re
from typing import List, Tuple
from models import StatsVerbatim, RecordInfo

# French verbatim watchlists ported from legacy watchVerbatim.cs
WATCH_LETHAL = [
    "tuer", "mort", "meurtre", "suicide", "suicider", "sang", "cadavre",
    "arme", "couteau", "pistolet", "fusil", "crever", "égorger", "assassiner"
]

WATCH_LEGAL = [
    "police", "avocat", "tribunal", "plainte", "juge", "procès", "prison",
    "gendarmerie", "justice", "commissariat", "juridique", "loi", "huissier"
]

WATCH_MENACES = [
    "menace", "menacer", "frapper", "casser", "détruire", "brûler", "retrouver",
    "attraper", "défoncer", "bousiller", "éclater", "faire payer"
]

WATCH_INSULTES = [
    "con", "connard", "salop", "salope", "pute", "enculé", "putain", "merde",
    "bâtard", "abruti", "imbécile", "ordure", "bouffon"
]


class VerbatimAnalyzer:
    def __init__(self):
        self.lethal_patterns = [re.compile(r'\b' + re.escape(w) + r'\w*', re.IGNORECASE) for w in WATCH_LETHAL]
        self.legal_patterns = [re.compile(r'\b' + re.escape(w) + r'\w*', re.IGNORECASE) for w in WATCH_LEGAL]
        self.menaces_patterns = [re.compile(r'\b' + re.escape(w) + r'\w*', re.IGNORECASE) for w in WATCH_MENACES]
        self.insultes_patterns = [re.compile(r'\b' + re.escape(w) + r'\w*', re.IGNORECASE) for w in WATCH_INSULTES]

    def analyze_text(self, text: str) -> StatsVerbatim:
        stats = StatsVerbatim()
        occurrences = []

        for p in self.lethal_patterns:
            matches = p.findall(text)
            stats.count_lethal += len(matches)
            occurrences.extend(matches)

        for p in self.legal_patterns:
            matches = p.findall(text)
            stats.count_legal += len(matches)
            occurrences.extend(matches)

        for p in self.menaces_patterns:
            matches = p.findall(text)
            stats.count_menaces += len(matches)
            occurrences.extend(matches)

        for p in self.insultes_patterns:
            matches = p.findall(text)
            stats.count_insultes += len(matches)
            occurrences.extend(matches)

        stats.occurrences = list(set([o.lower() for o in occurrences]))
        return stats

    def analyze_record(self, record: RecordInfo) -> RecordInfo:
        text = record.story
        if not text and record.speeches:
            text = " ".join(s.script for s in record.speeches)

        record.stats_verbatim = self.analyze_text(text)
        return record
