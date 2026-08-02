use crate::config::SttConfig;
use crate::models::SpeechContent;
use crate::vad::AudioChunk;
use anyhow::{Context, Result};
use std::path::Path;
use std::sync::mpsc;
use std::thread;
use tracing::{error, info};
use whisper_rs::{FullParams, SamplingStrategy, WhisperContext, WhisperContextParameters};

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
    pub fn new(config: SttConfig) -> Result<Self> {
        let (request_tx, request_rx) = mpsc::channel::<SttRequest>();
        let request_rx = std::sync::Arc::new(std::sync::Mutex::new(request_rx));

        info!(
            "Initializing Whisper STT pool with {} workers ({} threads per worker) on model {}",
            config.workers, config.threads_per_worker, config.model_path
        );

        for worker_id in 0..config.workers {
            let rx = request_rx.clone();
            let config = config.clone();

            thread::spawn(move || {
                let model_path = Path::new(&config.model_path);
                if !model_path.exists() {
                    error!("[STT Worker {}] Model path does not exist: {:?}", worker_id, model_path);
                    return;
                }

                let ctx = match WhisperContext::new_with_params(
                    &config.model_path,
                    WhisperContextParameters::default(),
                ) {
                    Ok(c) => c,
                    Err(e) => {
                        error!("[STT Worker {}] Failed to load Whisper context: {:?}", worker_id, e);
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

                    match process_chunk(&ctx, &config, &req.chunk) {
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

fn process_chunk(ctx: &WhisperContext, config: &SttConfig, chunk: &AudioChunk) -> Result<SpeechContent> {
    let mut state = ctx.create_state().context("Failed to create Whisper state")?;
    let mut params = FullParams::new(SamplingStrategy::Greedy {
        best_of: config.beam_size as i32,
    });

    params.set_language(Some(&config.language));
    params.set_n_threads(config.threads_per_worker as i32);
    params.set_print_special(false);
    params.set_print_progress(false);
    params.set_print_realtime(false);
    params.set_print_timestamps(false);

    if config.enable_timestamps {
        params.set_token_timestamps(true);
    }

    state.full(params, &chunk.samples)
        .context("Failed to run Whisper full transcription")?;

    let num_segments = state.full_n_segments();
    let mut full_text = String::new();
    let total_confidence = 0.0;
    let word_timings = Vec::new();

    for i in 0..num_segments {
        if let Some(segment) = state.get_segment(i) {
            if let Ok(text) = segment.to_str() {
                full_text.push_str(text);
                full_text.push(' ');
            }
        }
    }

    let avg_confidence = if !word_timings.is_empty() {
        total_confidence / word_timings.len() as f64
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
