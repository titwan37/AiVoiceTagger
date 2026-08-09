import logging
import urllib.request
import json
from models import RecordInfo
from verbatim import VerbatimAnalyzer

logger = logging.getLogger("nlp_worker")


class NlpPipeline:
    def __init__(self, ollama_url: str = "http://localhost:11434/api/generate"):
        self.verbatim_analyzer = VerbatimAnalyzer()
        self.ollama_url = ollama_url

    def generate_ollama_summary(self, story: str, model: str = "qwen2.5:7b") -> str | None:
        """Call local Ollama endpoint for 100% offline incident summarization (Meetily architecture)."""
        if not story or len(story) < 30:
            return None

        prompt = f"Fourni un résumé synthétique de 2 phrases et l'évaluation du risque pour ce compte rendu audio:\n\n{story[:1500]}"
        payload = json.dumps({"model": model, "prompt": prompt, "stream": False}).encode("utf-8")
        
        try:
            req = urllib.request.Request(self.ollama_url, data=payload, headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=3) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                return data.get("response", "").strip()
        except Exception:
            return None

    def process_record(self, record: RecordInfo) -> RecordInfo:
        # Step 1: Rule-based verbatim statistics
        record = self.verbatim_analyzer.analyze_record(record)

        # Step 2: Clean and format story text
        if record.speeches:
            scripts = [s.script.strip() for s in record.speeches if s.script.strip()]
            record.story = " ".join(scripts)
            record.speech_count = len(record.speeches)

        # Step 3: Optional local Ollama summarization
        if record.story and not record.triage_summary:
            ollama_summary = self.generate_ollama_summary(record.story)
            if ollama_summary:
                record.triage_summary = f"[Ollama LLM Summary] {ollama_summary}"

        return record

