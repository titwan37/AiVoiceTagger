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


        // Populate database with newly discovered records from CSV or scanner
        for record in &records {
            if let Ok(None) = self.state_store.get_record_state(&record.record_id) {
                let _ = self.state_store.insert_or_update_record(record);
            }
        }

        // for record in &records {
        //     let current_state = self.state_store.get_record_state(&record.record_id)?;

        //     // If running full transcription, process DISCOVERED, DECODED, or TRIAGED_HIGH_INTEREST
        //     if current_state == RecordState::Done || current_state == RecordState::TriagedLowInterest {
        //         continue;
        //     }

        //     // Claim ticket lease and process
        //     if self.state_store.claim_record_lease(&record.record_id, &self.worker_id)? {
        //         self.process_single_record(record).await?;
        //     }
        // }

        let mut processed_records = Vec::new();

        // Stage 1.5: Probe Hardware & GPU Engine
        let compute_device = crate::hardware::HardwareDetector::probe_system(&self.config.hardware);
        info!("Active Pipeline Compute Device: {:?}", compute_device);

        // Optional STT worker pool(s)
        let primary_stt_pool = if self.config.stt.enabled {
            match WhisperPool::new(self.config.stt.clone(), compute_device.clone(), None) {
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
                    let mut heavy_stt_config = self.config.stt.clone();
                    heavy_stt_config.workers = self.config.stt.heavy_workers.unwrap_or(1);
                    heavy_stt_config.threads_per_worker = self.config.stt.heavy_threads_per_worker.unwrap_or(6);

                    info!(
                        "Initializing Heavy STT pool with {} workers ({} threads per worker) on model {}",
                        heavy_stt_config.workers, heavy_stt_config.threads_per_worker, heavy_path
                    );
                    match WhisperPool::new(heavy_stt_config, compute_device.clone(), Some(heavy_path)) {
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
        loop {
            let mut claim_attempts = 0;
            let claim_res = loop {
                match self.state_store.claim_unprocessed_record(&self.worker_id, 300) {
                    Ok(res) => break Ok(res),
                    Err(e) => {
                        claim_attempts += 1;
                        if claim_attempts <= 5 {
                            warn!("[Worker {}] SQLite database lock busy during claim: {:?}. Retrying ({}/5)...", self.worker_id, e, claim_attempts);
                            std::thread::sleep(std::time::Duration::from_millis(200 * claim_attempts));
                        } else {
                            break Err(e);
                        }
                    }
                }
            };

            match claim_res {
                Ok(Some(mut record)) => {
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

            if crate::SHUTDOWN_FLAG.load(std::sync::atomic::Ordering::Relaxed) {
                tracing::info!("Shutdown flag detected. Stopping worker loop.");
                break;
            }

            let path = Path::new(&record.directory).join(&record.name);
            let lock_path = std::path::PathBuf::from(format!("{}.lock", path.to_string_lossy()));

            let _lock_guard = match FileLockGuard::create(lock_path, &self.worker_id, 180) {
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
                let mut chunks = vad.segment_audio(&record.record_id, &pcm);
                let total_chunks = chunks.len();
                
                if record.processed_chunks > 0 && (record.processed_chunks as usize) < total_chunks {
                    tracing::info!("Resuming STT for {} from chunk {}/{}", record.record_id, record.processed_chunks, total_chunks);
                    chunks = chunks.into_iter().skip(record.processed_chunks as usize).collect();
                }

                let diarizer = crate::diarization::SpeakerDiarizer::new(
                    self.config.stt.diarization_enabled.unwrap_or(true)
                );

                let is_high_interest = record.state == RecordState::TriagedHighInterest;
                let use_direct_heavy = is_high_interest && heavy_stt_pool.is_some();

                if use_direct_heavy {
                    let heavy_pool = heavy_stt_pool.as_ref().unwrap();
                    info!(
                        "[Direct Heavy STT Fast-Path] Record {} flagged TriagedHighInterest. Directly invoking Heavy STT Model.",
                        record.record_id
                    );
                    let start_time = std::time::Instant::now();
                    for (idx, chunk) in chunks.iter().enumerate() {
                        if crate::SHUTDOWN_FLAG.load(std::sync::atomic::Ordering::Relaxed) {
                            tracing::warn!("Gracefully stopping Direct Heavy STT pass for {}...", record.record_id);
                            record.processed_chunks += idx as u32;
                            break;
                        }
                        if let Ok(rx) = heavy_pool.submit(chunk.clone()) {
                            if let Ok(mut res) = rx.recv() {
                                if let Ok(diarized) = diarizer.diarize_chunk(&chunk.samples, chunk.start_ms, chunk.end_ms - chunk.start_ms) {
                                    diarizer.assign_speaker_to_speech(&mut res.speech, &diarized);
                                }
                                record.speeches.push(res.speech);
                                let actual_idx = record.processed_chunks as usize + idx + 1;
                                
                                let elapsed = start_time.elapsed().as_secs_f64();
                                let chunks_done_session = (idx + 1) as f64;
                                let time_per_chunk = elapsed / chunks_done_session;
                                let chunks_left = chunks.len() - (idx + 1);
                                let eta_secs = time_per_chunk * (chunks_left as f64);
                                let eta_mins = (eta_secs / 60.0).floor() as u64;
                                let eta_rem_secs = (eta_secs % 60.0) as u64;

                                info!("[Global Progress] Record {} (Heavy Fast-Path): {}/{} chunks ({:.1}%) - ETA: {}m {:02}s", record.record_id, actual_idx, total_chunks, (actual_idx as f64 / total_chunks as f64) * 100.0, eta_mins, eta_rem_secs);
                            }
                        }
                    }
                    if !crate::SHUTDOWN_FLAG.load(std::sync::atomic::Ordering::Relaxed) {
                        record.processed_chunks = total_chunks as u32;
                    }
                } else {
                    // Pass 1 (Primary model)
                    let start_time = std::time::Instant::now();
                    for (idx, chunk) in chunks.iter().enumerate() {
                        if crate::SHUTDOWN_FLAG.load(std::sync::atomic::Ordering::Relaxed) {
                            tracing::warn!("Gracefully stopping Pass 1 STT for {}...", record.record_id);
                            record.processed_chunks += idx as u32;
                            break;
                        }
                        if let Ok(rx) = pool.submit(chunk.clone()) {
                            if let Ok(mut res) = rx.recv() {
                                if let Ok(diarized) = diarizer.diarize_chunk(&chunk.samples, chunk.start_ms, chunk.end_ms - chunk.start_ms) {
                                    diarizer.assign_speaker_to_speech(&mut res.speech, &diarized);
                                }
                                record.speeches.push(res.speech);
                                let actual_idx = record.processed_chunks as usize + idx + 1;

                                let elapsed = start_time.elapsed().as_secs_f64();
                                let chunks_done_session = (idx + 1) as f64;
                                let time_per_chunk = elapsed / chunks_done_session;
                                let chunks_left = chunks.len() - (idx + 1);
                                let eta_secs = time_per_chunk * (chunks_left as f64);
                                let eta_mins = (eta_secs / 60.0).floor() as u64;
                                let eta_rem_secs = (eta_secs % 60.0) as u64;

                                info!("[Global Progress] Record {} (Pass 1): {}/{} chunks ({:.1}%) - ETA: {}m {:02}s", record.record_id, actual_idx, total_chunks, (actual_idx as f64 / total_chunks as f64) * 100.0, eta_mins, eta_rem_secs);
                            }
                        }
                    }
                    if !crate::SHUTDOWN_FLAG.load(std::sync::atomic::Ordering::Relaxed) {
                        record.processed_chunks = total_chunks as u32;
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
                        let start_time = std::time::Instant::now();
                        for (idx, chunk) in chunks.iter().enumerate() {
                            if crate::SHUTDOWN_FLAG.load(std::sync::atomic::Ordering::Relaxed) {
                                tracing::warn!("Gracefully stopping Pass 2 STT for {}... (Will restart Pass 2 on resume)", record.record_id);
                                record.processed_chunks = 0; // Reset so next time it starts from 0 for Pass 1. (Fallback)
                                record.speeches.clear();
                                break;
                            }
                            if let Ok(rx) = heavy_pool.submit(chunk.clone()) {
                                if let Ok(mut res) = rx.recv() {
                                    if let Ok(diarized) = diarizer.diarize_chunk(&chunk.samples, chunk.start_ms, chunk.end_ms - chunk.start_ms) {
                                        diarizer.assign_speaker_to_speech(&mut res.speech, &diarized);
                                    }
                                    record.speeches.push(res.speech);
                                    
                                    let elapsed = start_time.elapsed().as_secs_f64();
                                    let chunks_done_session = (idx + 1) as f64;
                                    let time_per_chunk = elapsed / chunks_done_session;
                                    let chunks_left = chunks.len() - (idx + 1);
                                    let eta_secs = time_per_chunk * (chunks_left as f64);
                                    let eta_mins = (eta_secs / 60.0).floor() as u64;
                                    let eta_rem_secs = (eta_secs % 60.0) as u64;

                                    info!("[Global Progress] Record {} (Pass 2): {}/{} chunks ({:.1}%) - ETA: {}m {:02}s", record.record_id, idx + 1, total_chunks, ((idx + 1) as f64 / total_chunks as f64) * 100.0, eta_mins, eta_rem_secs);
                                }
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
                },
                Ok(None) => break, // No more records
                Err(e) => {
                    error!("Error claiming record: {:?}", e);
                    break;
                }
            }
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
    let mut buf = Vec::new();
    reader.read_until(b'\n', &mut buf)?;

    let line = String::from_utf8_lossy(&buf);

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
