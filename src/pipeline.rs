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
}

impl Pipeline {
    pub fn new(config: Config) -> Result<Self> {
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
        })
    }

    pub async fn run(&self) -> Result<()> {
        info!("Starting AiVoiceTagger pipeline execution...");

        // Stage 1: Directory scan
        let records = self.scanner.scan_directory()?;
        info!("Discovered {} files in target directory", records.len());

        let mut processed_records = Vec::new();

        // Optional STT worker pool
        let stt_pool = if self.config.stt.enabled {
            Some(WhisperPool::new(self.config.stt.clone())?)
        } else {
            None
        };

        for mut record in records {
            // Check state store for deduplication & resume
            if let Ok(Some(existing_state)) = self.state_store.get_record_state(&record.record_id) {
                if existing_state == RecordState::Done || existing_state == RecordState::Exported {
                    info!("Record {} already completed ({:?}). Skipping.", record.record_id, existing_state);
                    continue;
                }
            }

            record.state = RecordState::Queued;
            self.state_store.insert_or_update_record(&record)?;

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

            // Stage 3: STT transcription
            if let (Some(pool), Some(pcm)) = (&stt_pool, probe.pcm_data) {
                let vad = VadSegmenter::new(
                    self.config.stt.chunk_length_seconds,
                    self.config.decoder.target_sample_rate,
                );
                let chunks = vad.segment_audio(&record.record_id, &pcm);

                for chunk in chunks {
                    if let Ok(rx) = pool.submit(chunk) {
                        if let Ok(res) = rx.recv() {
                            record.speeches.push(res.speech);
                        }
                    }
                }

                record.speech_count = record.speeches.len();
                record.story = record.speeches.iter().map(|s| s.script.as_str()).collect::<Vec<_>>().join(" ");
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
