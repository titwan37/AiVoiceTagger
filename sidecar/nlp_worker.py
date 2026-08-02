import logging
from models import RecordInfo
from verbatim import VerbatimAnalyzer

logger = logging.getLogger("nlp_worker")


class NlpPipeline:
    def __init__(self):
        self.verbatim_analyzer = VerbatimAnalyzer()

    def process_record(self, record: RecordInfo) -> RecordInfo:
        # Step 1: Rule-based verbatim statistics
        record = self.verbatim_analyzer.analyze_record(record)

        # Step 2: Clean and format story text
        if record.speeches:
            scripts = [s.script.strip() for s in record.speeches if s.script.strip()]
            record.story = " ".join(scripts)
            record.speech_count = len(record.speeches)

        return record
