use crate::config::SttConfig;
use crate::models::SpeechContent;
use crate::vad::AudioChunk;
use anyhow::{Context, Result};
use std::path::Path;
use std::sync::{Arc, mpsc};
use std::thread;
use tracing::{error, info};
use whisper_rs::{FullParams, SamplingStrategy, WhisperContext, WhisperContextParameters, WhisperState, WhisperTokenId};

pub struct SttRequest {
    pub chunk: AudioChunk,
    pub response_tx: mpsc::Sender<SttResult>,
}

pub struct SttResult {
    pub chunk_id: String,
    pub record_id: String,
    pub speech: SpeechContent,
}

pub struct WhisperPool {
    request_tx: mpsc::Sender<SttRequest>,
}

impl WhisperPool {
    pub fn new(config: SttConfig, model_override: Option<&str>) -> Result<Self> {
        let model_path_str = model_override.unwrap_or(&config.model_path).to_string();
        let (request_tx, request_rx) = mpsc::channel::<SttRequest>();
        let request_rx = std::sync::Arc::new(std::sync::Mutex::new(request_rx));

        let model_path = Path::new(&model_path_str);
        if !model_path.exists() {
            anyhow::bail!("STT model path does not exist: {:?}", model_path);
        }

        info!("Loading shared WhisperContext once for STT pool: {}", model_path_str);
        let ctx = Arc::new(
            WhisperContext::new_with_params(&model_path_str, WhisperContextParameters::default())
                .with_context(|| format!("Failed to load Whisper context from {}", model_path_str))?,
        );
        let token_eot = ctx.token_eot();

        info!(
            "Initializing Whisper STT pool with {} persistent workers ({} threads per worker) on model {}",
            config.workers, config.threads_per_worker, model_path_str
        );

        for worker_id in 0..config.workers {
            let rx = request_rx.clone();
            let config = config.clone();
            let ctx = ctx.clone();

            thread::spawn(move || {
                let mut state = match ctx.create_state() {
                    Ok(s) => s,
                    Err(e) => {
                        error!("[STT Worker {}] Failed to create persistent Whisper state: {:?}", worker_id, e);
                        return;
                    }
                };

                loop {
                    let req = {
                        let lock = rx.lock().unwrap();
                        match lock.recv() {
                            Ok(r) => r,
                            Err(_) => break, // pool shutdown
                        }
                    };

                    match process_chunk(&mut state, &config, &req.chunk, token_eot) {
                        Ok(speech) => {
                            let _ = req.response_tx.send(SttResult {
                                chunk_id: req.chunk.chunk_id,
                                record_id: req.chunk.record_id,
                                speech,
                            });
                        }
                        Err(e) => {
                            error!("[STT Worker {}] Error processing chunk {}: {:?}", worker_id, req.chunk.chunk_id, e);
                        }
                    }
                }
            });
        }

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

fn process_chunk(state: &mut WhisperState, config: &SttConfig, chunk: &AudioChunk, token_eot: WhisperTokenId) -> Result<SpeechContent> {
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
    params.set_progress_callback_safe(move |progress| {
        if progress > 0 && progress % 25 == 0 {
            info!("[STT Progress] Chunk {}: {}%", chunk_id_label, progress);
        }
    });

    state.full(params, &chunk.samples)
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
