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

    /// Override the Whisper model path from config
    #[arg(short, long)]
    model: Option<String>,

    /// Path to export CSV inventory manifest
    #[arg(long)]
    export_manifest: Option<PathBuf>,

    /// Process input from a CSV inventory manifest instead of scanning directory
    #[arg(long)]
    from_csv: Option<PathBuf>,

    /// Unique identifier for this worker instance (default: auto-generated)
    #[arg(long)]
    worker_id: Option<String>,

    /// Pin process execution to specific CPU cores/kernels (e.g., "0-5" or "0,1,2,3")
    #[arg(long)]
    cpu_affinity: Option<String>,

    /// Scan directory and exit (dry run)
    #[arg(long, default_value_t = false)]
    scan_only: bool,

    /// Run worker strictly in high-speed Triage Mode across all files
    #[arg(long, default_value_t = false)]
    triage_only: bool,
}

fn parse_cpu_affinity(affinity_str: &str) -> usize {
    let mut mask: usize = 0;
    for part in affinity_str.split(',') {
        let part = part.trim();
        if part.contains('-') {
            let bounds: Vec<&str> = part.split('-').collect();
            if bounds.len() == 2 {
                if let (Ok(start), Ok(end)) = (bounds[0].parse::<usize>(), bounds[1].parse::<usize>()) {
                    for core in start..=end {
                        if core < 64 {
                            mask |= 1 << core;
                        }
                    }
                }
            }
        } else if let Ok(core) = part.parse::<usize>() {
            if core < 64 {
                mask |= 1 << core;
            }
        }
    }
    mask
}

#[cfg(target_os = "windows")]
fn set_process_cpu_affinity(mask: usize) -> bool {
    extern "system" {
        fn GetCurrentProcess() -> isize;
        fn SetProcessAffinityMask(hProcess: isize, dwProcessAffinityMask: usize) -> i32;
    }
    unsafe {
        let handle = GetCurrentProcess();
        SetProcessAffinityMask(handle, mask) != 0
    }
}

#[cfg(not(target_os = "windows"))]
fn set_process_cpu_affinity(_mask: usize) -> bool {
    true
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

    if let Some(affinity_str) = &args.cpu_affinity {
        let mask = parse_cpu_affinity(affinity_str);
        if mask > 0 {
            if set_process_cpu_affinity(mask) {
                info!("Successfully pinned process to CPU affinity mask: 0x{:X} ({})", mask, affinity_str);
            } else {
                tracing::warn!("Failed to apply CPU affinity mask: 0x{:X}", mask);
            }
        }
    }

    let worker_id = args.worker_id.unwrap_or_else(|| {
        std::env::var("COMPUTERNAME")
            .or_else(|_| std::env::var("HOSTNAME"))
            .unwrap_or_else(|_| format!("worker_{}", std::process::id()))
    });
    info!("Running as worker instance: {}", worker_id);

    let mut config = Config::load_from_file(&args.config)
        .with_context(|| format!("Failed to load configuration from {:?}", args.config))?;

    // Override model path if provided via CLI
    if let Some(model_override) = args.model {
        info!("Overriding STT model path with: {}", model_override);
        config.stt.model_path = model_override;
    }

    // Override input manifest if provided via CLI
    if let Some(manifest_path) = args.from_csv {
        info!("Overriding input source with manifest CSV: {:?}", manifest_path);
        config.scanner.input_manifest = Some(manifest_path.to_string_lossy().to_string());
    }

    if args.scan_only {
        info!("Running in scan-only dry-run mode...");
        let scanner = scanner::FileScanner::new(config.scanner.clone())?;
        let records = scanner.scan_or_load()?;
        info!("Found {} matching audio records.", records.len());
        for (idx, r) in records.iter().enumerate().take(10) {
            info!("  [{}] {} ({}) - Path: {}/{}", idx + 1, r.name, r.size_human, r.directory, r.name);
        }

        let export_path = args.export_manifest.unwrap_or_else(|| PathBuf::from("inventory_manifest.csv"));
        scanner.export_manifest_csv(&records, &export_path)?;
        info!("Exported inventory manifest with {} records to {:?}", records.len(), export_path);
        return Ok(());
    }

    let pipeline = Pipeline::new(config, worker_id, args.triage_only)?;
    pipeline.run().await?;

    info!("AiVoiceTagger finished successfully.");
    Ok(())
}
