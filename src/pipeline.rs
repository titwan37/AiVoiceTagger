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
    triage_only: bool,
}

impl Pipeline {
    pub fn new(config: Config, worker_id: String, triage_only: bool) -> Result<Self> {
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
            triage_only,
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
            let state_clone = self.state_store.clone();
            let (stop_heartbeat_tx, mut stop_heartbeat_rx) = tokio::sync::oneshot::channel::<()>();

            tokio::spawn(async move {
                let mut interval = tokio::time::interval(std::time::Duration::from_secs(30));
                interval.tick().await;
                loop {
                    tokio::select! {
                        _ = interval.tick() => {
                            info!("[Heartbeat] Worker {} is processing record {}...", worker_lbl, record_lbl);
                            let _ = state_clone.touch_heartbeat(&record_lbl, 1800);
                        }
                        _ = &mut stop_heartbeat_rx => {
                            break;
                        }
                    }
                }
            });

            let path = Path::new(&record.directory).join(&record.name);
            let lock_path = std::path::PathBuf::from(format!("{}.lock", path.to_string_lossy()));

            let _lock_guard = match FileLockGuard::create(lock_path, &self.worker_id, 1800) {
                Ok(Some(guard)) => guard,
                Ok(None) => {
                    info!("Record {} ({}) has active .lock file. Skipping.", record.record_id, record.name);
                    let _ = stop_heartbeat_tx.send(());
                    continue;
                }
                Err(e) => {
                    warn!("Lockfile creation warning for record {}: {:?}. Continuing processing.", record.record_id, e);
                    FileLockGuard::dummy()
                }
            };

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

            // Stage 2.5: High-Speed 3-Stage Triage Pass (ggml-tiny-q8_0.bin)
            let watchlist = load_external_watchlist(&self.config.stt);
            let triage_model = self.config.stt.triage_model_path.as_deref().unwrap_or("models/ggml-tiny-q8_0.bin");

            if Path::new(triage_model).exists() {
                if let Ok(snippets) = self.decoder.extract_triage_snippets(&path, record.length_bytes) {
                    if !snippets.is_empty() {
                        info!("[Triage Engine] Running ggml-tiny triage pass on {} audio snippets for record {}...", snippets.len(), record.record_id);
                        if let Ok((is_high, matched_kw, triage_text)) = crate::stt::run_triage_pass(Path::new(triage_model), &snippets, &watchlist) {
                            let kw_json = serde_json::to_string(&matched_kw).unwrap_or_default();
                            record.triage_summary = Some(triage_text.clone());
                            if record.story.is_empty() {
                                record.story = triage_text.clone();
                            }

                            if is_high {
                                info!("[Triage Engine] 🚨 Record {} flagged HIGH INTEREST (Matched: {:?})", record.record_id, matched_kw);
                                record.state = RecordState::TriagedHighInterest;
                                let _ = self.state_store.update_triage_result(&record.record_id, RecordState::TriagedHighInterest, &kw_json, &triage_text, self.triage_only);
                                if self.triage_only {
                                    let _ = stop_heartbeat_tx.send(());
                                    processed_records.push(record);
                                    continue;
                                }
                            } else {
                                info!("[Triage Engine] 💤 Record {} marked LOW INTEREST (0 watchlist matches). Preview persisted.", record.record_id);
                                record.state = RecordState::TriagedLowInterest;
                                let _ = self.state_store.update_triage_result(&record.record_id, RecordState::TriagedLowInterest, &kw_json, &triage_text, true);
                                let _ = stop_heartbeat_tx.send(());
                                processed_records.push(record);
                                continue;
                            }
                        }
                    }
                }
            }

            // Stage 3: STT transcription (Pass 1 & optional Pass 2)
            if let (Some(pool), Some(pcm)) = (&primary_stt_pool, probe.pcm_data) {
                let vad = VadSegmenter::new(
                    self.config.stt.chunk_length_seconds,
                    self.config.decoder.target_sample_rate,
                );
                let chunks = vad.segment_audio(&record.record_id, &pcm);

                let diarizer = crate::diarization::SpeakerDiarizer::new(
                    self.config.stt.diarization_enabled.unwrap_or(true)
                );

                // Pass 1 (Primary model)
                for chunk in &chunks {
                    if let Ok(rx) = pool.submit(chunk.clone()) {
                        if let Ok(mut res) = rx.recv() {
                            if let Ok(diarized) = diarizer.diarize_chunk(&chunk.samples, chunk.start_ms, chunk.end_ms - chunk.start_ms) {
                                diarizer.assign_speaker_to_speech(&mut res.speech, &diarized);
                            }
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
                            if let Ok(mut res) = rx.recv() {
                                if let Ok(diarized) = diarizer.diarize_chunk(&chunk.samples, chunk.start_ms, chunk.end_ms - chunk.start_ms) {
                                    diarizer.assign_speaker_to_speech(&mut res.speech, &diarized);
                                }
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

pub struct FileLockGuard {
    path: Option<std::path::PathBuf>,
}

impl FileLockGuard {
    pub fn create(lock_path: std::path::PathBuf, worker_id: &str, stale_secs: u64) -> Result<Option<Self>> {
        if lock_path.exists() {
            if let Ok(metadata) = std::fs::metadata(&lock_path) {
                if let Ok(modified) = metadata.modified() {
                    if let Ok(elapsed) = modified.elapsed() {
                        if elapsed.as_secs() < stale_secs {
                            tracing::info!(
                                "Lockfile {:?} is active (age {}s < {}s). Skipping file.",
                                lock_path, elapsed.as_secs(), stale_secs
                            );
                            return Ok(None);
                        } else {
                            tracing::warn!(
                                "Lockfile {:?} is stale (age {}s >= {}s). Overwriting stale lock.",
                                lock_path, elapsed.as_secs(), stale_secs
                            );
                        }
                    }
                }
            }
        }

        let content = format!(
            "Worker: {} | Timestamp: {}\n",
            worker_id,
            chrono::Utc::now().to_rfc3339()
        );
        std::fs::write(&lock_path, content)
            .with_context(|| format!("Failed to write lockfile {:?}", lock_path))?;

        Ok(Some(Self {
            path: Some(lock_path),
        }))
    }

    pub fn dummy() -> Self {
        Self { path: None }
    }
}

impl Drop for FileLockGuard {
    fn drop(&mut self) {
        if let Some(ref lock_path) = self.path {
            if lock_path.exists() {
                let _ = std::fs::remove_file(lock_path);
            }
        }
    }
}

fn load_external_watchlist(config: &crate::config::SttConfig) -> Vec<String> {
    let mut keywords = Vec::new();

    // 1. Try loading from external text file (e.g. watchlist.txt)
    let file_path = config.watchlist_file.as_deref().unwrap_or("watchlist.txt");
    if Path::new(file_path).exists() {
        if let Ok(content) = std::fs::read_to_string(file_path) {
            for line in content.lines() {
                let trimmed = line.trim();
                if !trimmed.is_empty() && !trimmed.starts_with('#') {
                    keywords.push(trimmed.to_string());
                }
            }
        }
    }

    // 2. Fall back to config.yaml watchlist_keywords if file was empty or missing
    if keywords.is_empty() {
        if let Some(list) = &config.watchlist_keywords {
            keywords.extend(list.clone());
        }
    }

    // 3. Fall back to default inline list if still empty
    if keywords.is_empty() {
        keywords = vec![
            "harcèlement".to_string(), "menace".to_string(), "insulte".to_string(), "dégage".to_string(),
            "va chier".to_string(), "va te faire foutre".to_string(), "t'es nul".to_string(), "un gros nase".to_string(),
            "cagibi".to_string(), "casser la gueule".to_string(), "ta gueule".to_string(), "mon frère".to_string(),
            "avocat".to_string(), "police".to_string(), "tribunal".to_string(),
            "argent".to_string(), "preuve".to_string(), "justice".to_string(), "chantage".to_string()
        ];
    }

    keywords
}
