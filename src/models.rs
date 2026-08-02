use chrono::{DateTime, Utc};
use serde::{Deserialize, Serialize};
use std::fmt;

/// State of a record in the supervisor state machine.
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "SCREAMING_SNAKE_CASE")]
pub enum RecordState {
    Discovered,
    Queued,
    Decoded,
    Transcribed,
    NlpDone,
    Exported,
    Done,
    Retry,
    Failed,
    DeadLetter,
}

impl fmt::Display for RecordState {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "{:?}", self)
    }
}

/// Word-level timing metric matching Whisper output.
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct WordTiming {
    pub word: String,
    pub start_ms: u64,
    pub end_ms: u64,
    pub confidence: f32,
}

/// Transcribed speech segment matching legacy SpeechContent.
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct SpeechContent {
    pub time_frame: String,
    pub script: String,
    pub confidence: f64,
    pub word_count: usize,
    pub offset_ms: u64,
    pub duration_ms: u64,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub words: Option<Vec<WordTiming>>,
}

impl SpeechContent {
    pub fn new(script: String, confidence: f64, offset_ms: u64, duration_ms: u64) -> Self {
        let words: Vec<&str> = script.split_whitespace().collect();
        let word_count = words.len();
        let start_sec = offset_ms / 1000;
        let end_sec = (offset_ms + duration_ms) / 1000;
        let time_frame = format!("{:02}:{:02}:{:02} --> {:02}:{:02}:{:02}",
            start_sec / 3600, (start_sec % 3600) / 60, start_sec % 60,
            end_sec / 3600, (end_sec % 3600) / 60, end_sec % 60
        );

        Self {
            time_frame,
            script,
            confidence,
            word_count,
            offset_ms,
            duration_ms,
            words: None,
        }
    }
}

/// Verbatim count summary matching legacy watchVerbatim statistics.
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Default)]
pub struct StatsVerbatim {
    pub count_lethal: usize,
    pub count_legal: usize,
    pub count_menaces: usize,
    pub count_insultes: usize,
    pub occurrences: Vec<String>,
}

impl StatsVerbatim {
    pub fn total_matches(&self) -> usize {
        self.count_lethal + self.count_legal + self.count_menaces + self.count_insultes
    }

    pub fn is_remarkable(&self) -> bool {
        self.total_matches() > 0
    }
}

/// Core domain record model mapping legacy C# RecordInfo.
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct RecordInfo {
    pub record_id: String,
    pub name: String,
    pub directory: String,
    pub date_record_day: Option<DateTime<Utc>>,
    pub date_last_write: DateTime<Utc>,
    pub length_bytes: u64,
    pub size_human: String,
    pub duration_seconds: f64,
    pub speech_count: usize,
    pub speeches: Vec<SpeechContent>,
    pub story: String,
    pub stats_verbatim: StatsVerbatim,
    pub state: RecordState,
    pub is_degraded: bool,
}

impl RecordInfo {
    pub fn new(
        record_id: String,
        name: String,
        directory: String,
        date_record_day: Option<DateTime<Utc>>,
        date_last_write: DateTime<Utc>,
        length_bytes: u64,
    ) -> Self {
        let size_human = format_size(length_bytes);
        Self {
            record_id,
            name,
            directory,
            date_record_day,
            date_last_write,
            length_bytes,
            size_human,
            duration_seconds: 0.0,
            speech_count: 0,
            speeches: Vec::new(),
            story: String::new(),
            stats_verbatim: StatsVerbatim::default(),
            state: RecordState::Discovered,
            is_degraded: false,
        }
    }

    /// Convert C# TimeSpan ticks (100ns units) to milliseconds.
    pub fn ticks_to_ms(ticks: u64) -> u64 {
        ticks / 10_000
    }

    /// Convert milliseconds to C# TimeSpan ticks.
    pub fn ms_to_ticks(ms: u64) -> u64 {
        ms * 10_000
    }

    /// Legacy C# fallback duration heuristic: duration_sec = round(bytes / 15563.4)
    pub fn legacy_fallback_duration(length_bytes: u64) -> f64 {
        (length_bytes as f64 / 15563.4).round()
    }
}

fn format_size(bytes: u64) -> String {
    if bytes < 1024 {
        format!("{} B", bytes)
    } else if bytes < 1024 * 1024 {
        format!("{:.2} KB", bytes as f64 / 1024.0)
    } else if bytes < 1024 * 1024 * 1024 {
        format!("{:.2} MB", bytes as f64 / (1024.0 * 1024.0))
    } else {
        format!("{:.2} GB", bytes as f64 / (1024.0 * 1024.0 * 1024.0))
    }
}
