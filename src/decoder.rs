use crate::config::DecoderConfig;
use crate::models::RecordInfo;
use anyhow::{Context, Result};
use std::fs::File;
use std::path::Path;
use symphonia::core::audio::{AudioBufferRef, Signal};
use symphonia::core::codecs::DecoderOptions;
use symphonia::core::errors::Error;
use symphonia::core::formats::FormatOptions;
use symphonia::core::io::MediaSourceStream;
use symphonia::core::meta::MetadataOptions;
use symphonia::core::probe::Hint;

pub struct AudioProbeResult {
    pub duration_seconds: f64,
    pub sample_rate: u32,
    pub channels: u16,
    pub pcm_data: Option<Vec<f32>>,
    pub is_degraded: bool,
}

pub struct AudioDecoder {
    config: DecoderConfig,
}

impl AudioDecoder {
    pub fn new(config: DecoderConfig) -> Self {
        Self { config }
    }

    /// Probe audio metadata and optionally decode to 16 kHz mono PCM samples.
    pub fn probe_and_decode(&self, file_path: &Path, file_size: u64, decode_samples: bool) -> Result<AudioProbeResult> {
        let file = File::open(file_path)
            .with_context(|| format!("Failed to open audio file at {:?}", file_path))?;
        let mss = MediaSourceStream::new(Box::new(file), Default::default());

        let mut hint = Hint::new();
        if let Some(ext) = file_path.extension().and_then(|s| s.to_str()) {
            hint.with_extension(ext);
        }

        let format_opts = FormatOptions {
            enable_gapless: true,
            ..Default::default()
        };
        let metadata_opts = MetadataOptions::default();

        match symphonia::default::get_probe().format(&hint, mss, &format_opts, &metadata_opts) {
            Ok(probed) => {
                let mut format = probed.format;
                let track = match format.default_track() {
                    Some(t) => t,
                    None => return Ok(self.fallback_result(file_size)),
                };

                let track_id = track.id;
                let sample_rate = track.codec_params.sample_rate.unwrap_or(16000);
                let channels = track.codec_params.channels.map(|c| c.count() as u16).unwrap_or(1);

                let mut duration_seconds = 0.0;
                if let (Some(n_frames), Some(tb)) = (track.codec_params.n_frames, track.codec_params.time_base) {
                    let time = tb.calc_time(n_frames);
                    duration_seconds = time.seconds as f64 + time.frac;
                }

                if duration_seconds <= 0.0 {
                    duration_seconds = RecordInfo::legacy_fallback_duration(file_size);
                }

                let mut pcm_samples = Vec::new();
                let mut is_degraded = false;

                if decode_samples {
                    let decoder_opts = DecoderOptions::default();
                    match symphonia::default::get_codecs().make(&track.codec_params, &decoder_opts) {
                        Ok(mut decoder) => {
                            while let Ok(packet) = format.next_packet() {
                                if packet.track_id() != track_id {
                                    continue;
                                }
                                match decoder.decode(&packet) {
                                    Ok(audio_buf) => {
                                        let mono_chunk = downmix_and_resample(&audio_buf, sample_rate, self.config.target_sample_rate);
                                        pcm_samples.extend(mono_chunk);
                                    }
                                    Err(Error::DecodeError(_)) => {
                                        is_degraded = true;
                                        continue;
                                    }
                                    Err(_) => break,
                                }
                            }
                        }
                        Err(_) => {
                            is_degraded = true;
                        }
                    }
                }

                Ok(AudioProbeResult {
                    duration_seconds,
                    sample_rate,
                    channels,
                    pcm_data: if decode_samples { Some(pcm_samples) } else { None },
                    is_degraded,
                })
            }
            Err(_) => Ok(self.fallback_result(file_size)),
        }
    }

    fn fallback_result(&self, file_size: u64) -> AudioProbeResult {
        AudioProbeResult {
            duration_seconds: RecordInfo::legacy_fallback_duration(file_size),
            sample_rate: self.config.target_sample_rate,
            channels: self.config.channels,
            pcm_data: None,
            is_degraded: true,
        }
    }
}

/// Downmix multi-channel AudioBuffer to mono f32 array and resample if needed.
fn downmix_and_resample(buf: &AudioBufferRef, source_rate: u32, target_rate: u32) -> Vec<f32> {
    

    let mut samples = Vec::new();
    match buf {
        AudioBufferRef::F32(b) => extract_mono_samples(b, &mut samples),
        AudioBufferRef::U8(b) => extract_mono_samples_converted(b, &mut samples, |v| (v as f32 - 128.0) / 128.0),
        AudioBufferRef::S16(b) => extract_mono_samples_converted(b, &mut samples, |v| v as f32 / 32768.0),
        AudioBufferRef::S24(b) => extract_mono_samples_converted(b, &mut samples, |v| v.0 as f32 / 8388608.0),
        AudioBufferRef::S32(b) => extract_mono_samples_converted(b, &mut samples, |v| v as f32 / 2147483648.0),
        _ => {}
    }

    if source_rate != target_rate && source_rate > 0 {
        // Simple linear resampling
        let ratio = source_rate as f64 / target_rate as f64;
        let new_len = (samples.len() as f64 / ratio) as usize;
        let mut resampled = Vec::with_capacity(new_len);
        for i in 0..new_len {
            let src_idx = (i as f64 * ratio) as usize;
            if src_idx < samples.len() {
                resampled.push(samples[src_idx]);
            }
        }
        resampled
    } else {
        samples
    }
}

fn extract_mono_samples(b: &symphonia::core::audio::AudioBuffer<f32>, out: &mut Vec<f32>) {
    let num_channels = b.spec().channels.count();
    let num_frames = b.frames();
    out.reserve(num_frames);

    for f in 0..num_frames {
        let mut sum = 0.0;
        for c in 0..num_channels {
            sum += b.chan(c)[f];
        }
        out.push(sum / num_channels as f32);
    }
}

fn extract_mono_samples_converted<T>(
    b: &symphonia::core::audio::AudioBuffer<T>,
    out: &mut Vec<f32>,
    convert: impl Fn(T) -> f32,
) where
    T: symphonia::core::sample::Sample,
{
    let num_channels = b.spec().channels.count();
    let num_frames = b.frames();
    out.reserve(num_frames);

    for f in 0..num_frames {
        let mut sum = 0.0;
        for c in 0..num_channels {
            sum += convert(b.chan(c)[f]);
        }
        out.push(sum / num_channels as f32);
    }
}
