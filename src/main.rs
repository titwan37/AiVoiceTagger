mod config;
mod decoder;
mod export;
mod models;
mod pipeline;
mod retry;
mod scanner;
mod state;
mod legacy_import;
mod stt;
mod vad;

use crate::config::Config;
use crate::pipeline::Pipeline;
use anyhow::{Context, Result};
use clap::Parser;
use std::path::PathBuf;
use tracing::info;
use tracing_subscriber::EnvFilter;

#[derive(Parser, Debug)]
#[command(author, version, about = "AiVoiceTagger — Resilient, CPU-Optimized Batch Audio Processing Core")]
struct Args {
    /// Path to YAML configuration file
    #[arg(short, long, default_value = "config.yaml")]
    config: PathBuf,

    /// Scan directory and exit (dry run)
    #[arg(long, default_value_t = false)]
    scan_only: bool,
}

#[tokio::main]
async fn main() -> Result<()> {
    let args = Args::parse();

    // Initialize tracing subscriber
    let filter = EnvFilter::try_from_default_env().unwrap_or_else(|_| EnvFilter::new("info"));
    tracing_subscriber::fmt()
        .with_env_filter(filter)
        .with_target(false)
        .init();

    info!("Starting AiVoiceTagger Core v0.1.0");

    let config = Config::load_from_file(&args.config)
        .with_context(|| format!("Failed to load configuration from {:?}", args.config))?;

    if args.scan_only {
        info!("Running in scan-only dry-run mode...");
        let scanner = scanner::FileScanner::new(config.scanner.clone())?;
        let records = scanner.scan_directory()?;
        info!("Found {} matching audio records.", records.len());
        for (idx, r) in records.iter().enumerate().take(10) {
            info!("  [{}] {} ({}) - Date: {:?}", idx + 1, r.name, r.size_human, r.date_record_day);
        }
        return Ok(());
    }

    let pipeline = Pipeline::new(config)?;
    pipeline.run().await?;

    info!("AiVoiceTagger finished successfully.");
    Ok(())
}
