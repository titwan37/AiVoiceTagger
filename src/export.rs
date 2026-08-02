use crate::config::ExporterConfig;
use crate::models::RecordInfo;
use anyhow::{Context, Result};
use csv::WriterBuilder;
use std::fs::{self};
use std::io::Write;
use std::path::{Path, PathBuf};

pub struct Exporter {
    config: ExporterConfig,
}

impl Exporter {
    pub fn new(config: ExporterConfig) -> Result<Self> {
        let out_dir = Path::new(&config.output_directory);
        if !out_dir.exists() {
            fs::create_dir_all(out_dir)
                .with_context(|| format!("Failed to create export directory {:?}", out_dir))?;
        }
        Ok(Self { config })
    }

    /// Export aggregated records into JSON, CSV, and optional Parquet formats using atomic writes.
    pub fn export_records(&self, records: &[RecordInfo]) -> Result<()> {
        let out_dir = PathBuf::from(&self.config.output_directory);

        if self.config.export_json {
            let json_path = out_dir.join("RecordInfo.json");
            let json_bytes = serde_json::to_vec_pretty(records)?;
            atomic_write(&json_path, &json_bytes)?;

            // Digest export (stripped speeches)
            let digest_records: Vec<_> = records.iter().map(|r| {
                let mut d = r.clone();
                d.speeches.clear();
                d
            }).collect();
            let digest_path = out_dir.join("DigestRecordInfo.json");
            let digest_bytes = serde_json::to_vec_pretty(&digest_records)?;
            atomic_write(&digest_path, &digest_bytes)?;

            // Remarkable records export
            let remarkable_records: Vec<_> = records.iter()
                .filter(|r| r.stats_verbatim.is_remarkable())
                .cloned()
                .collect();
            let remarkable_path = out_dir.join("RemarkableRecordInfo.json");
            let remarkable_bytes = serde_json::to_vec_pretty(&remarkable_records)?;
            atomic_write(&remarkable_path, &remarkable_bytes)?;
        }

        if self.config.export_csv {
            let csv_path = out_dir.join("RecordList.csv");
            let mut writer = WriterBuilder::new().from_writer(Vec::new());

            writer.write_record(&[
                "RecordID", "Name", "Directory", "DateRecordDay", "DateLastWrite",
                "SizeHuman", "DurationSeconds", "SpeechCount", "Lethal", "Legal",
                "Menaces", "Insultes", "IsDegraded", "State"
            ])?;

            for r in records {
                writer.write_record(&[
                    &r.record_id,
                    &r.name,
                    &r.directory,
                    &r.date_record_day.map(|d| d.to_rfc3339()).unwrap_or_default(),
                    &r.date_last_write.to_rfc3339(),
                    &r.size_human,
                    &r.duration_seconds.to_string(),
                    &r.speech_count.to_string(),
                    &r.stats_verbatim.count_lethal.to_string(),
                    &r.stats_verbatim.count_legal.to_string(),
                    &r.stats_verbatim.count_menaces.to_string(),
                    &r.stats_verbatim.count_insultes.to_string(),
                    &r.is_degraded.to_string(),
                    &r.state.to_string(),
                ])?;
            }

            let csv_bytes = writer.into_inner()?;
            atomic_write(&csv_path, &csv_bytes)?;
        }

        Ok(())
    }
}

pub fn atomic_write(target_path: &Path, content: &[u8]) -> Result<()> {
    let parent = target_path.parent().unwrap_or_else(|| Path::new("."));
    let temp_file = tempfile::NamedTempFile::new_in(parent)?;
    
    let mut file = temp_file.as_file();
    file.write_all(content)?;
    file.flush()?;
    file.sync_all()?;

    temp_file.persist(target_path)
        .with_context(|| format!("Failed to atomically rename temp file to {:?}", target_path))?;

    Ok(())
}
