use crate::config::Config;
use crate::decoder::AudioDecoder;
use crate::export::Exporter;
use crate::models::{RecordInfo, RecordState};
use crate::scanner::FileScanner;
use crate::state::StateStore;
use crate::stt::WhisperPool;
use crate::vad::VadSegmenter;
use anyhow::{Context, Result};
use std::path::Path;
use std::process::{Command, Stdio};
use std::io::{BufRead, BufReader, Write};
use std::sync::Arc;
use tracing::{error, info, warn};

pub struct Pipeline {
    config: Config,
    state_store: Arc<StateStore>,
    scanner: FileScanner,
    decoder: AudioDecoder,
    exporter: Exporter,
    worker_id: String,
}

impl Pipeline {
    pub fn new(config: Config, worker_id: String) -> Result<Self> {
        let state_store = Arc::new(StateStore::new(&config.state_store)?);
        let scanner = FileScanner::new(config.scanner.clone())?;
        let decoder = AudioDecoder::new(config.decoder.clone());
        let exporter = Exporter::new(config.exporter.clone())?;

        Ok(Self {
            config,
            state_store,
            scanner,
            decoder,
            exporter,
            worker_id,
        })
    }

    pub async fn run(&self) -> Result<()> {
        info!("Starting AiVoiceTagger pipeline execution (worker: {})...", self.worker_id);

        // Stage 1: Directory scan or CSV manifest load & populate DB
        let records = self.scanner.scan_or_load()?;
        info!("Discovered {} files for processing.", records.len());

        for record in &records {
            if let Ok(None) = self.state_store.get_record_state(&record.record_id) {
                let _ = self.state_store.insert_or_update_record(record);
            }
        }

        let mut processed_records = Vec::new();

        // Optional STT worker pool(s)
        let primary_stt_pool = if self.config.stt.enabled {
            match WhisperPool::new(self.config.stt.clone(), None) {
                Ok(p) => Some(p),
                Err(e) => {
                    warn!("Failed to initialize primary STT pool: {:?}", e);
                    None
                }
            }
        } else {
            None
        };

        let adaptive_enabled = self.config.stt.adaptive_multipass.unwrap_or(false);
        let heavy_stt_pool = if adaptive_enabled && self.config.stt.enabled {
            if let Some(heavy_path) = &self.config.stt.heavy_model_path {
                if Path::new(heavy_path).exists() {
                    match WhisperPool::new(self.config.stt.clone(), Some(heavy_path)) {
                        Ok(p) => Some(p),
                        Err(e) => {
                            warn!("Heavy STT model initialization failed ({:?}). Falling back to single pass.", e);
                            None
                        }
                    }
                } else {
                    info!("Heavy STT model file not found at {:?}. Multi-pass dynamic fallback disabled.", heavy_path);
                    None
                }
            } else {
                None
            }
        } else {
            None
        };

        let confidence_threshold = self.config.stt.confidence_threshold.unwrap_or(0.80);
        let intensity_threshold = self.config.stt.intensity_threshold_rms.unwrap_or(0.15);

        // Worker claim loop
        while let Ok(Some(mut record)) = self.state_store.claim_unprocessed_record(&self.worker_id, 300) {
            info!("[Worker {}] Claimed record: {} ({})", self.worker_id, record.record_id, record.name);

            // Spawn 30-second heartbeat monitor
            let worker_lbl = self.worker_id.clone();
            let record_lbl = record.record_id.clone();
            let (stop_heartbeat_tx, mut stop_heartbeat_rx) = tokio::sync::oneshot::channel::<()>();

            tokio::spawn(async move {
                let mut interval = tokio::time::interval(std::time::Duration::from_secs(30));
                interval.tick().await;
                loop {
                    tokio::select! {
                        _ = interval.tick() => {
                            info!("[Heartbeat] Worker {} is processing record {}...", worker_lbl, record_lbl);
                        }
                        _ = &mut stop_heartbeat_rx => {
                            break;
                        }
                    }
                }
            });

            let path = Path::new(&record.directory).join(&record.name);

            // Stage 2: Probe & decode audio
            let probe = match self.decoder.probe_and_decode(&path, record.length_bytes, self.config.stt.enabled) {
                Ok(p) => p,
                Err(e) => {
                    error!("Failed to probe audio for record {}: {:?}", record.record_id, e);
                    self.state_store.record_dead_letter(
                        Some(&record.record_id),
                        None,
                        "DECODE",
                        &e.to_string(),
                    )?;
                    continue;
                }
            };

            record.duration_seconds = probe.duration_seconds;
            record.is_degraded = probe.is_degraded;
            record.state = RecordState::Decoded;
            self.state_store.insert_or_update_record(&record)?;

            // Stage 3: STT transcription (Pass 1 & optional Pass 2)
            if let (Some(pool), Some(pcm)) = (&primary_stt_pool, probe.pcm_data) {
                let vad = VadSegmenter::new(
                    self.config.stt.chunk_length_seconds,
                    self.config.decoder.target_sample_rate,
                );
                let chunks = vad.segment_audio(&record.record_id, &pcm);

                // Pass 1 (Primary model)
                for chunk in &chunks {
                    if let Ok(rx) = pool.submit(chunk.clone()) {
                        if let Ok(res) = rx.recv() {
                            record.speeches.push(res.speech);
                        }
                    }
                }

                let total_conf: f64 = record.speeches.iter().map(|s| s.confidence).sum();
                let avg_confidence = if !record.speeches.is_empty() {
                    total_conf / record.speeches.len() as f64
                } else {
                    1.0
                };

                let triggers_pass_two = (avg_confidence < confidence_threshold) || (probe.rms_intensity > intensity_threshold);

                if triggers_pass_two && heavy_stt_pool.is_some() {
                    let heavy_pool = heavy_stt_pool.as_ref().unwrap();
                    info!(
                        "[Adaptive Multi-Pass] Triggering Pass 2 (Heavy Model) for record {}: avg_confidence={:.2} (threshold={:.2}), rms_intensity={:.3} (threshold={:.3})",
                        record.record_id, avg_confidence, confidence_threshold, probe.rms_intensity, intensity_threshold
                    );

                    record.speeches.clear();
                    for chunk in &chunks {
                        if let Ok(rx) = heavy_pool.submit(chunk.clone()) {
                            if let Ok(res) = rx.recv() {
                                record.speeches.push(res.speech);
                            }
                        }
                    }
                }

                record.speech_count = record.speeches.len();
                record.story = record.speeches.iter().map(|s| s.script.as_str()).collect::<Vec<_>>().join(" ");

                let total_conf: f64 = record.speeches.iter().map(|s| s.confidence).sum();
                let final_avg_conf = if !record.speeches.is_empty() {
                    total_conf / record.speeches.len() as f64
                } else {
                    0.0
                };

                record.avg_logprob = (final_avg_conf - 1.0) * 2.0;
                record.background_noise_detected = probe.rms_intensity > intensity_threshold;

                if record.speeches.is_empty() || record.story.trim().is_empty() {
                    record.quality_grade = crate::models::QualityGrade::Unusable;
                } else if record.background_noise_detected || final_avg_conf < confidence_threshold {
                    record.quality_grade = crate::models::QualityGrade::Degraded;
                } else {
                    record.quality_grade = crate::models::QualityGrade::Good;
                }

                record.state = RecordState::Transcribed;
                self.state_store.insert_or_update_record(&record)?;
            }

            // Stage 4: Python Sidecar NLP enrichment (if enabled)
            if self.config.sidecar.enabled {
                match run_sidecar_ipc(&self.config, &record) {
                    Ok(enriched) => {
                        record = enriched;
                        record.state = RecordState::NlpDone;
                        self.state_store.insert_or_update_record(&record)?;
                    }
                    Err(e) => {
                        warn!("Sidecar NLP processing failed for record {}: {:?}", record.record_id, e);
                    }
                }
            }

            record.state = RecordState::Done;
            self.state_store.insert_or_update_record(&record)?;
            processed_records.push(record);
            let _ = stop_heartbeat_tx.send(());
        }

        // Stage 5: Export aggregated outputs
        self.exporter.export_records(&processed_records)?;
        info!("Pipeline finished. Exported {} records.", processed_records.len());

        Ok(())
    }
}

fn run_sidecar_ipc(config: &Config, record: &RecordInfo) -> Result<RecordInfo> {
    let mut child = Command::new(&config.sidecar.python_executable)
        .arg(&config.sidecar.script_path)
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .spawn()
        .context("Failed to spawn Python sidecar process")?;

    let json_req = serde_json::to_string(record)?;

    if let Some(mut stdin) = child.stdin.take() {
        writeln!(stdin, "{}", json_req)?;
    }

    let stdout = child.stdout.take().context("Failed to open child stdout")?;
    let mut reader = BufReader::new(stdout);
    let mut line = String::new();
    reader.read_line(&mut line)?;

    let enriched: RecordInfo = serde_json::from_str(line.trim())
        .context("Failed to parse sidecar response JSON")?;

    let _ = child.wait();
    Ok(enriched)
}
