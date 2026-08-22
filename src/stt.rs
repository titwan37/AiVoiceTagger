use crate::config::SttConfig;
use crate::hardware::ComputeDevice;
use crate::models::SpeechContent;
use crate::vad::AudioChunk;
use anyhow::{Context, Result};
use std::path::Path;
use std::sync::{Arc, mpsc};
use std::thread;
use tracing::{error, info, warn};
use whisper_rs::{FullParams, SamplingStrategy, WhisperContext, WhisperContextParameters, WhisperTokenId};

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum SttEngineProvider {
    Whisper,
    Parakeet,
    Auto,
}

impl SttEngineProvider {
    pub fn parse(s: Option<&str>) -> Self {
        match s.unwrap_or("auto").to_lowercase().as_str() {
            "parakeet" => Self::Parakeet,
            "whisper" => Self::Whisper,
            _ => Self::Auto,
        }
    }
}

pub struct SttRequest {
    pub chunk: AudioChunk,
    pub response_tx: mpsc::Sender<SttResult>,
}

pub struct SttResult {
    #[allow(dead_code)]
    pub chunk_id: String,
    #[allow(dead_code)]
    pub record_id: String,
    pub speech: SpeechContent,
}

pub struct WhisperPool {
    request_tx: mpsc::Sender<SttRequest>,
}

impl WhisperPool {
    pub fn new(config: SttConfig, compute_device: ComputeDevice, model_override: Option<&str>) -> Result<Self> {
        let provider_type = SttEngineProvider::parse(config.provider.as_deref());
        let model_path_str = model_override.unwrap_or(&config.model_path).to_string();
        let (request_tx, request_rx) = mpsc::channel::<SttRequest>();
        let request_rx = std::sync::Arc::new(std::sync::Mutex::new(request_rx));

        let model_path = Path::new(&model_path_str);
        if !model_path.exists() {
            anyhow::bail!("STT model path does not exist: {:?}", model_path);
        }

        let mut ctx_params = WhisperContextParameters::default();
        match &compute_device {
            ComputeDevice::Cuda { name, total_vram_mb } => {
                info!("Enabling CUDA GPU acceleration on device: {} (VRAM: {} MB)", name, total_vram_mb);
                ctx_params.use_gpu(true);
            }
            ComputeDevice::IntelGpu { name } => {
                info!("Configuring execution for Intel GPU adapter: {}", name);
                ctx_params.use_gpu(true);
            }
            ComputeDevice::Cpu { available_cores } => {
                info!("Configuring Whisper STT context for CPU execution across {} cores", available_cores);
                ctx_params.use_gpu(false);
            }
        }

        info!("Initializing STT pool [Engine Provider: {:?}] loading shared context from: {}", provider_type, model_path_str);
        let ctx = Arc::new(
            WhisperContext::new_with_params(&model_path_str, ctx_params)
                .with_context(|| format!("Failed to load Whisper context from {}", model_path_str))?,
        );
        let token_eot = ctx.token_eot();

        let (workers, threads_per_worker) = match compute_device {
            ComputeDevice::Cpu { .. } => (
                config.cpu_fallback_workers.unwrap_or(config.workers),
                config.cpu_fallback_threads_per_worker.unwrap_or(config.threads_per_worker),
            ),
            ComputeDevice::Cuda { total_vram_mb, .. } => (
                if total_vram_mb > 8192 { 2 } else { 1 },
                config.threads_per_worker,
            ),
            ComputeDevice::IntelGpu { .. } => (1, config.threads_per_worker),
        };

        info!(
            "Initializing Whisper STT pool with {} GPU/CPU workers ({} threads per worker) on model {}",
            workers, threads_per_worker, model_path_str
        );

        for worker_id in 0..workers {
            let rx = request_rx.clone();
            let config = config.clone();
            let ctx = ctx.clone();

            thread::spawn(move || {
                info!("[STT Worker {}] Worker thread ready for chunk requests.", worker_id);

                loop {
                    let req = {
                        let lock = rx.lock().unwrap();
                        match lock.recv() {
                            Ok(r) => r,
                            Err(_) => break, // pool shutdown
                        }
                    };

                    let chunk_id = req.chunk.chunk_id.clone();
                    info!("[STT Worker {}] Processing chunk {}", worker_id, chunk_id);

                    // Execute chunk with fresh state & automatic retry on transient CUDA memory spikes
                    let mut result = process_chunk(&ctx, &config, &req.chunk, token_eot);
                    if result.is_err() {
                        warn!("[STT Worker {}] Chunk {} initial pass encountered error. Retrying after VRAM pause...", worker_id, chunk_id);
                        thread::sleep(std::time::Duration::from_millis(300));
                        result = process_chunk(&ctx, &config, &req.chunk, token_eot);
                    }

                    match result {
                        Ok(speech) => {
                            info!("[STT Worker {}] Chunk {} completed successfully.", worker_id, chunk_id);
                            let _ = req.response_tx.send(SttResult {
                                chunk_id: req.chunk.chunk_id,
                                record_id: req.chunk.record_id,
                                speech,
                            });
                        }
                        Err(e) => {
                            error!("[STT Worker {}] Error processing chunk {}: {:?}", worker_id, chunk_id, e);
                        }
                    }
                }
            });
        }

        // Fallback: If the user requests a specific provider and it's not Whisper, spawn a single dedicated thread
        // if provider_type != SttEngineProvider::Whisper {
        //     info!("Using non-Whisper STT engine (Parakeet). Spawning dedicated thread.");
            
        //             match process_chunk(&mut state, &config, &req.chunk, token_eot) {
        //                 Ok(speech) => {
        //                     let _ = req.response_tx.send(SttResult {
        //                         chunk_id: req.chunk.chunk_id,
        //                         record_id: req.chunk.record_id,
        //                         speech,
        //                     });
        //                 }
        //                 Err(e) => {
        //                     error!("[STT Worker {}] Error processing chunk {}: {:?}", worker_id, req.chunk.chunk_id, e);
        //                 }
        //             }
        //         }
        //     });
        // }

        Ok(Self { request_tx })
    }

    pub fn submit(&self, chunk: AudioChunk) -> Result<mpsc::Receiver<SttResult>> {
        let (tx, rx) = mpsc::channel();
        self.request_tx
            .send(SttRequest {
                chunk,
                response_tx: tx,
            })
            .context("Failed to submit chunk to STT worker pool")?;
        Ok(rx)
    }
}

fn process_chunk(ctx: &WhisperContext, config: &SttConfig, chunk: &AudioChunk, token_eot: WhisperTokenId) -> Result<SpeechContent> {
    let mut state = ctx.create_state().context("Failed to create Whisper state for chunk")?;
    let mut params = FullParams::new(SamplingStrategy::Greedy {
        best_of: config.beam_size as i32,
    });

    params.set_language(Some(&config.language));
    params.set_n_threads(config.threads_per_worker as i32);
    params.set_print_special(false);
    params.set_print_progress(false);
    params.set_print_realtime(false);
    params.set_print_timestamps(false);

    // Noisy audio parameter optimizations
    params.set_no_context(true);
    params.set_suppress_blank(true);
    params.set_logprob_thold(-1.50);
    params.set_temperature_inc(0.0);

    if config.enable_timestamps {
        params.set_token_timestamps(true);
        params.set_split_on_word(true);
    }

    let chunk_id_label = chunk.chunk_id.clone();
    let last_activity = Arc::new(std::sync::atomic::AtomicU64::new(
        std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .unwrap_or_default()
            .as_secs(),
    ));

    let last_logged_progress = Arc::new(std::sync::atomic::AtomicU8::new(0));

    let last_act_progress = last_activity.clone();
    let chunk_id_progress = chunk_id_label.clone();
    let last_logged_progress_cb = last_logged_progress.clone();
    params.set_progress_callback_safe(move |progress| {
        let now = std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .unwrap_or_default()
            .as_secs();
        last_act_progress.store(now, std::sync::atomic::Ordering::Relaxed);
        
        let current_bracket = (progress / 25) as u8;
        let last_bracket = last_logged_progress_cb.load(std::sync::atomic::Ordering::Relaxed);
        
        if current_bracket > last_bracket && progress > 0 {
            let log_val = if progress >= 100 { 100 } else { current_bracket * 25 };
            info!("[STT Progress] Chunk {}: {}%", chunk_id_progress, log_val);
            last_logged_progress_cb.store(current_bracket, std::sync::atomic::Ordering::Relaxed);
        }
    });

    // Pad short audio input (< 100ms / 1600 samples at 16kHz) with silence to satisfy Whisper requirements
    let padded_storage;
    let samples_to_process: &[f32] = if chunk.samples.len() < 1600 {
        if chunk.samples.is_empty() {
            return Ok(crate::models::SpeechContent::new(
                String::new(),
                1.0,
                chunk.start_ms,
                chunk.end_ms.saturating_sub(chunk.start_ms),
            ));
        }
        padded_storage = {
            let mut p = chunk.samples.clone();
            p.resize(1600, 0.0);
            p
        };
        &padded_storage
    } else {
        &chunk.samples
    };

    state.full(params, samples_to_process)
        .context("Failed to run Whisper full transcription")?;

    let num_segments = state.full_n_segments();
    let mut full_text = String::new();
    let mut word_timings = Vec::with_capacity((num_segments as usize) * 15);
    let mut total_confidence = 0.0;
    let mut token_count = 0;

    for i in 0..num_segments {
        if let Some(segment) = state.get_segment(i) {
            if let Ok(text) = segment.to_str() {
                full_text.push_str(text);
                full_text.push(' ');
            }

            if config.enable_timestamps {
                let num_tokens = segment.n_tokens();
                for t in 0..num_tokens {
                    if let Some(token) = segment.get_token(t) {
                        if token.token_id() >= token_eot {
                            continue;
                        }
                        if let Ok(raw_text) = token.to_str() {
                            let clean_word = raw_text.replace('\u{2581}', " ").trim().to_string();
                            if !clean_word.is_empty() {
                                let data = token.token_data();
                                let p = data.p;
                                total_confidence += p as f64;
                                token_count += 1;
                                word_timings.push(crate::models::WordTiming {
                                    word: clean_word,
                                    start_ms: (data.t0 as u64) * 10,
                                    end_ms: (data.t1 as u64) * 10,
                                    confidence: p,
                                });
                            }
                        }
                    }
                }
            }
        }
    }

    let avg_confidence = if token_count > 0 {
        total_confidence / token_count as f64
    } else {
        0.85
    };

    let mut speech = SpeechContent::new(
        full_text.trim().to_string(),
        avg_confidence,
        chunk.start_ms,
        chunk.end_ms - chunk.start_ms,
    );

    if config.enable_timestamps && !word_timings.is_empty() {
        speech.words = Some(word_timings);
    }

    Ok(speech)
}

/// Run fast triage pass using ggml-tiny-q8_0.bin model.
/// Transcribes audio snippets and checks for French watchlist keywords.
pub fn run_triage_pass(
    model_path: &Path,
    snippets: &[Vec<f32>],
    watchlist: &[String],
) -> Result<(bool, Vec<String>, String)> {
    if snippets.is_empty() {
        return Ok((false, Vec::new(), String::new()));
    }

    let ctx = WhisperContext::new_with_params(
        model_path.to_str().unwrap_or("models/ggml-tiny-q8_0.bin"),
        WhisperContextParameters::default(),
    )
    .context("Failed to load lightweight Triage Whisper model (ggml-tiny-q8_0.bin)")?;

    // Owned by worker thread loop
    let mut state = ctx.create_state().context("Failed to create Triage Whisper state")?;
    let mut snippet_parts = Vec::new();
    let labels = ["Start", "Peak", "End"];

    for (idx, snippet) in snippets.iter().enumerate() {
        if snippet.is_empty() {
            continue;
        }

        let mut params = FullParams::new(SamplingStrategy::Greedy { best_of: 1 });
        params.set_language(Some("fr"));
        params.set_print_special(false);
        params.set_print_progress(false);
        params.set_print_realtime(false);
        params.set_print_timestamps(false);

        if state.full(params, snippet).is_ok() {
            let n_seg = state.full_n_segments();
            let mut seg_text = String::new();
            for i in 0..n_seg {
                if let Some(segment) = state.get_segment(i) {
                    if let Ok(txt) = segment.to_str() {
                        let cleaned = txt.trim();
                        if !cleaned.is_empty() {
                            seg_text.push_str(cleaned);
                            seg_text.push(' ');
                        }
                    }
                }
            }
            let trimmed = seg_text.trim();
            if !trimmed.is_empty() {
                let tag = if idx < labels.len() { labels[idx] } else { "Snippet" };
                snippet_parts.push(format!("[{}] {}", tag, trimmed));
            }
        }
    }

    let raw_combined = snippet_parts.join(" ");
    let mut summary = raw_combined.clone();
    if summary.chars().count() > 300 {
        summary = summary.chars().take(297).collect::<String>() + "...";
    }

    let lower_text = raw_combined.to_lowercase();
    let mut matched = Vec::new();
    for kw in watchlist {
        let kw_lower = kw.to_lowercase();
        if lower_text.contains(&kw_lower) {
            matched.push(kw.clone());
        }
    }

    let is_high_interest = !matched.is_empty();
    Ok((is_high_interest, matched, summary))
}
