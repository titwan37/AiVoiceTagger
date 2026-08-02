use crate::models::{RecordInfo, RecordState, SpeechContent};
use crate::state::StateStore;
use anyhow::Result;
use chrono::{DateTime, Utc};
use serde::Deserialize;
use std::fs;
use std::path::Path;
use tracing::info;

#[derive(Debug, Deserialize)]
struct LegacySpeechContent {
    pub time_frame: Option<String>,
    pub script: Option<String>,
    pub confidence: Option<f64>,
}

#[derive(Debug, Deserialize)]
struct LegacyRecordInfo {
    pub name: Option<String>,
    pub directory: Option<String>,
    pub date_record_day: Option<String>,
    pub date_last_write: Option<String>,
    pub length: Option<u64>,
    pub speeches: Option<Vec<LegacySpeechContent>>,
    pub story: Option<String>,
}

pub fn import_legacy_json(json_path: &Path, state_store: &StateStore) -> Result<usize> {
    info!("Importing legacy JSON file from {:?}", json_path);
    let content = fs::read_to_string(json_path)?;
    let legacy_list: Vec<LegacyRecordInfo> = serde_json::from_str(&content)?;

    let mut imported = 0;

    for legacy in legacy_list {
        let name = legacy.name.unwrap_or_else(|| "unknown.wav".to_string());
        let directory = legacy.directory.unwrap_or_else(|| "C:\\Records".to_string());
        let length_bytes = legacy.length.unwrap_or(0);
        let date_last_write = parse_legacy_date(legacy.date_last_write.as_deref()).unwrap_or_else(Utc::now);
        let date_record_day = parse_legacy_date(legacy.date_record_day.as_deref());

        let record_id = crate::scanner::generate_record_id(
            &Path::new(&directory).join(&name),
            length_bytes,
            date_last_write,
        );

        let mut record = RecordInfo::new(
            record_id,
            name,
            directory,
            date_record_day,
            date_last_write,
            length_bytes,
        );

        if let Some(speeches) = legacy.speeches {
            for (idx, sp) in speeches.into_iter().enumerate() {
                let script = sp.script.unwrap_or_default();
                let conf = sp.confidence.unwrap_or(0.85);
                let offset_ms = (idx as u64) * 30_000;
                let duration_ms = 30_000;
                record.speeches.push(SpeechContent::new(script, conf, offset_ms, duration_ms));
            }
        }

        record.story = legacy.story.unwrap_or_default();
        record.speech_count = record.speeches.len();
        record.state = RecordState::Done;

        state_store.insert_or_update_record(&record)?;
        imported += 1;
    }

    info!("Successfully imported {} records into state store.", imported);
    Ok(imported)
}

fn parse_legacy_date(date_str: Option<&str>) -> Option<DateTime<Utc>> {
    let s = date_str?;
    DateTime::parse_from_rfc3339(s).map(|d| d.with_timezone(&Utc)).ok()
}
