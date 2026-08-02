use anyhow::{Context, Result};
use serde::{Deserialize, Serialize};
use std::fs;
use std::path::Path;

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ScannerConfig {
    pub input_directory: String,
    pub excluded_extensions: Vec<String>,
    pub recursive: bool,
    pub min_file_size_bytes: u64,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct StateStoreConfig {
    pub db_path: String,
    pub busy_timeout_ms: u64,
    pub journal_mode: String,
    pub synchronous: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct DecoderConfig {
    pub worker_threads: usize,
    pub target_sample_rate: u32,
    pub channels: u16,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SttConfig {
    pub enabled: bool,
    pub model_path: String,
    pub language: String,
    pub workers: usize,
    pub threads_per_worker: usize,
    pub beam_size: usize,
    pub enable_timestamps: bool,
    pub chunk_length_seconds: u32,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SidecarConfig {
    pub enabled: bool,
    pub python_executable: String,
    pub script_path: String,
    pub worker_threads: usize,
    pub timeout_seconds: u64,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ExporterConfig {
    pub output_directory: String,
    pub export_json: bool,
    pub export_csv: bool,
    pub export_parquet: bool,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PipelineConfig {
    pub max_inflight_audio_mb: usize,
    pub max_inflight_chunks: usize,
    pub max_retries: usize,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct LoggingConfig {
    pub level: String,
    pub format: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Config {
    pub scanner: ScannerConfig,
    pub state_store: StateStoreConfig,
    pub decoder: DecoderConfig,
    pub stt: SttConfig,
    pub sidecar: SidecarConfig,
    pub exporter: ExporterConfig,
    pub pipeline: PipelineConfig,
    pub logging: LoggingConfig,
}

impl Config {
    pub fn load_from_file<P: AsRef<Path>>(path: P) -> Result<Self> {
        let content = fs::read_to_string(path.as_ref())
            .with_context(|| format!("Failed to read config file at {:?}", path.as_ref()))?;
        let config: Config = serde_yaml::from_str(&content)
            .with_context(|| "Failed to parse YAML config content")?;
        Ok(config)
    }
}
