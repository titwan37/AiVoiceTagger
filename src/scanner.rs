use crate::config::ScannerConfig;
use crate::models::RecordInfo;
use anyhow::{Context, Result};
use chrono::{NaiveDate, TimeZone, Utc};
use regex::Regex;
use sha1::{Digest, Sha1};
use std::fs;
use std::path::Path;

pub struct FileScanner {
    config: ScannerConfig,
    date_regex_full: Regex,
    date_regex_day: Regex,
}

impl FileScanner {
    pub fn new(config: ScannerConfig) -> Result<Self> {
        // Legacy regex pattern 1: YYYY-MM-DD-HHhMM or YYYY-MM-DD-HH-MM-SS
        let date_regex_full = Regex::new(r"(\d{4})[-_](\d{2})[-_](\d{2})[-_](\d{2})[hH_-]?(\d{2})(?:[-_](\d{2}))?")
            .context("Failed to compile full date regex")?;

        // Legacy regex pattern 2: YYYY-MM-DD
        let date_regex_day = Regex::new(r"(\d{4})[-_](\d{2})[-_](\d{2})")
            .context("Failed to compile day date regex")?;

        Ok(Self {
            config,
            date_regex_full,
            date_regex_day,
        })
    }

    /// Automatically scans directory or loads from CSV manifest if configured.
    pub fn scan_or_load(&self) -> Result<Vec<RecordInfo>> {
        if let Some(manifest_path) = &self.config.input_manifest {
            tracing::info!("Loading audio file inventory from CSV manifest: {}", manifest_path);
            self.load_from_manifest_csv(Path::new(manifest_path))
        } else {
            self.scan_directory()
        }
    }

    /// Export scanned records inventory to a CSV manifest file.
    pub fn export_manifest_csv(&self, records: &[RecordInfo], path: &Path) -> Result<()> {
        let mut writer = csv::Writer::from_path(path)?;
        writer.write_record(&["record_id", "name", "directory", "length_bytes", "size_human", "date_record_day", "date_last_write"])?;
        for r in records {
            writer.write_record(&[
                &r.record_id,
                &r.name,
                &r.directory,
                &r.length_bytes.to_string(),
                &r.size_human,
                &r.date_record_day.map(|d| d.to_rfc3339()).unwrap_or_default(),
                &r.date_last_write.to_rfc3339(),
            ])?;
        }
        writer.flush()?;
        Ok(())
    }

    /// Load records inventory directly from an exported CSV manifest file.
    pub fn load_from_manifest_csv(&self, path: &Path) -> Result<Vec<RecordInfo>> {
        let mut reader = csv::Reader::from_path(path)?;
        let mut records = Vec::new();
        for result in reader.records() {
            let record = result?;
            if record.len() < 7 {
                continue;
            }
            let record_id = record[0].to_string();
            let name = record[1].to_string();
            let directory = record[2].to_string();
            let length_bytes: u64 = record[3].parse().unwrap_or(0);
            let date_record_day = if !record[5].is_empty() {
                chrono::DateTime::parse_from_rfc3339(&record[5]).ok().map(|d| d.with_timezone(&chrono::Utc))
            } else {
                None
            };
            let date_last_write = chrono::DateTime::parse_from_rfc3339(&record[6])
                .ok()
                .map(|d| d.with_timezone(&chrono::Utc))
                .unwrap_or_else(chrono::Utc::now);

            records.push(RecordInfo::new(
                record_id,
                name,
                directory,
                date_record_day,
                date_last_write,
                length_bytes,
            ));
        }
        Ok(records)
    }

    /// Recursively scan the configured input directory and yield metadata records.
    pub fn scan_directory(&self) -> Result<Vec<RecordInfo>> {
        let input_path = Path::new(&self.config.input_directory);
        if !input_path.exists() {
            anyhow::bail!("Input directory does not exist: {:?}", input_path);
        }

        let mut records = Vec::new();
        let walker = walkdir::WalkDir::new(input_path)
            .max_depth(if self.config.recursive { usize::MAX } else { 1 })
            .into_iter();

        for entry in walker.filter_map(|e| e.ok()) {
            let path = entry.path();
            if path.is_file() {
                if let Some(ext) = path.extension().and_then(|s| s.to_str()) {
                    let ext_dot = format!(".{}", ext.to_lowercase());
                    if self.config.excluded_extensions.iter().any(|e| e.to_lowercase() == ext_dot) {
                        continue;
                    }
                }

                let metadata = match fs::metadata(path) {
                    Ok(m) => m,
                    Err(_) => continue,
                };

                if metadata.len() < self.config.min_file_size_bytes {
                    continue;
                }

                if let Ok(record) = self.parse_file_record(path, &metadata) {
                    records.push(record);
                }
            }
        }

        Ok(records)
    }

    fn parse_file_record(&self, path: &Path, metadata: &fs::Metadata) -> Result<RecordInfo> {
        let file_name = path
            .file_name()
            .and_then(|s| s.to_str())
            .unwrap_or("unknown")
            .to_string();

        let parent_dir = path
            .parent()
            .and_then(|p| p.to_str())
            .unwrap_or("")
            .to_string();

        let last_write_time = metadata
            .modified()
            .map(|t| Utc.timestamp_opt(t.duration_since(std::time::UNIX_EPOCH).unwrap_or_default().as_secs() as i64, 0).single())
            .unwrap_or(None)
            .unwrap_or_else(Utc::now);

        let date_record_day = self.parse_date_from_filename(&file_name);

        let record_id = generate_record_id(path, metadata.len(), last_write_time);

        Ok(RecordInfo::new(
            record_id,
            file_name,
            parent_dir,
            date_record_day,
            last_write_time,
            metadata.len(),
        ))
    }

    fn parse_date_from_filename(&self, name: &str) -> Option<chrono::DateTime<Utc>> {
        if let Some(caps) = self.date_regex_full.captures(name) {
            let year: i32 = caps[1].parse().ok()?;
            let month: u32 = caps[2].parse().ok()?;
            let day: u32 = caps[3].parse().ok()?;
            let hour: u32 = caps[4].parse().ok()?;
            let min: u32 = caps[5].parse().ok()?;
            let sec: u32 = caps.get(6).and_then(|m| m.as_str().parse().ok()).unwrap_or(0);

            if let Some(dt) = NaiveDate::from_ymd_opt(year, month, day)
                .and_then(|d| d.and_hms_opt(hour, min, sec))
            {
                return Some(Utc.from_utc_datetime(&dt));
            }
        }

        if let Some(caps) = self.date_regex_day.captures(name) {
            let year: i32 = caps[1].parse().ok()?;
            let month: u32 = caps[2].parse().ok()?;
            let day: u32 = caps[3].parse().ok()?;

            if let Some(dt) = NaiveDate::from_ymd_opt(year, month, day)
                .and_then(|d| d.and_hms_opt(0, 0, 0))
            {
                return Some(Utc.from_utc_datetime(&dt));
            }
        }

        None
    }
}

pub fn generate_record_id(path: &Path, file_size: u64, mtime: chrono::DateTime<Utc>) -> String {
    let mut hasher = Sha1::new();
    hasher.update(path.to_string_lossy().as_bytes());
    hasher.update(file_size.to_le_bytes());
    hasher.update(mtime.timestamp().to_le_bytes());
    format!("rec_{:x}", hasher.finalize())
}
