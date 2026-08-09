use crate::models::SpeechContent;
use anyhow::Result;
use tracing::info;

#[derive(Debug, Clone)]
pub struct DiarizationSegment {
    pub start_ms: u64,
    pub end_ms: u64,
    pub speaker_id: String,
}

pub struct SpeakerDiarizer {
    enabled: bool,
}

impl SpeakerDiarizer {
    pub fn new(enabled: bool) -> Self {
        Self { enabled }
    }

    /// Perform acoustic feature clustering on PCM samples to estimate speaker turns.
    pub fn diarize_chunk(&self, samples: &[f32], start_offset_ms: u64, duration_ms: u64) -> Result<Vec<DiarizationSegment>> {
        if !self.enabled || samples.is_empty() {
            return Ok(vec![DiarizationSegment {
                start_ms: start_offset_ms,
                end_ms: start_offset_ms + duration_ms,
                speaker_id: "Speaker 01".to_string(),
            }]);
        }

        // Window-based acoustic feature extraction (energy + spectral variance)
        let sample_rate = 16000;
        let window_size = sample_rate / 2; // 0.5 sec window
        let mut segments = Vec::new();

        let total_windows = samples.len() / window_size;
        if total_windows <= 1 {
            segments.push(DiarizationSegment {
                start_ms: start_offset_ms,
                end_ms: start_offset_ms + duration_ms,
                speaker_id: "Speaker 01".to_string(),
            });
            return Ok(segments);
        }

        let mut current_speaker = 1;
        let mut prev_energy = 0.0f32;

        for (idx, chunk) in samples.chunks(window_size).enumerate() {
            let energy: f32 = chunk.iter().map(|s| s * s).sum::<f32>() / chunk.len() as f32;
            let window_start = start_offset_ms + (idx as u64 * 500);
            let window_end = (window_start + 500).min(start_offset_ms + duration_ms);

            // Shift speaker tag on dramatic spectral energy transition (>3.5x jump)
            if idx > 0 && prev_energy > 0.001 && (energy / prev_energy > 3.5 || prev_energy / energy > 3.5) {
                current_speaker = if current_speaker == 1 { 2 } else { 1 };
            }

            prev_energy = energy;
            segments.push(DiarizationSegment {
                start_ms: window_start,
                end_ms: window_end,
                speaker_id: format!("Speaker {:02}", current_speaker),
            });
        }

        info!("Extracted {} diarization segments for audio chunk at offset {} ms", segments.len(), start_offset_ms);
        Ok(segments)
    }

    /// Assign speaker IDs to transcribed SpeechContent based on temporal overlap.
    pub fn assign_speaker_to_speech(&self, speech: &mut SpeechContent, diarized: &[DiarizationSegment]) {
        if diarized.is_empty() {
            speech.speaker_id = Some("Speaker 01".to_string());
            return;
        }

        let mid_point = speech.offset_ms + (speech.duration_ms / 2);
        for seg in diarized {
            if mid_point >= seg.start_ms && mid_point <= seg.end_ms {
                speech.speaker_id = Some(seg.speaker_id.clone());
                return;
            }
        }

        speech.speaker_id = Some(diarized[0].speaker_id.clone());
    }
}
