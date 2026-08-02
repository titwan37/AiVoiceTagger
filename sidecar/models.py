from typing import List, Optional
from datetime import datetime
from pydantic import BaseModel, Field


class WordTiming(BaseModel):
    word: str
    start_ms: int
    end_ms: int
    confidence: float


class SpeechContent(BaseModel):
    time_frame: str
    script: str
    confidence: float
    word_count: int
    offset_ms: int
    duration_ms: int
    words: Optional[List[WordTiming]] = None


class StatsVerbatim(BaseModel):
    count_lethal: int = 0
    count_legal: int = 0
    count_menaces: int = 0
    count_insultes: int = 0
    occurrences: List[str] = Field(default_factory=list)

    def total_matches(self) -> int:
        return self.count_lethal + self.count_legal + self.count_menaces + self.count_insultes

    def is_remarkable(self) -> bool:
        return self.total_matches() > 0


class RecordInfo(BaseModel):
    record_id: str
    name: str
    directory: str
    date_record_day: Optional[datetime] = None
    date_last_write: datetime
    length_bytes: int
    size_human: str
    duration_seconds: float = 0.0
    speech_count: int = 0
    speeches: List[SpeechContent] = Field(default_factory=list)
    story: str = ""
    stats_verbatim: StatsVerbatim = Field(default_factory=StatsVerbatim)
    state: str = "DISCOVERED"
    is_degraded: bool = False
