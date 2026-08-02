use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AudioChunk {
    pub chunk_id: String,
    pub record_id: String,
    pub start_ms: u64,
    pub end_ms: u64,
    pub samples: Vec<f32>,
    pub sample_rate: u32,
}

pub struct VadSegmenter {
    target_chunk_seconds: u32,
    sample_rate: u32,
    energy_threshold: f32,
}

impl VadSegmenter {
    pub fn new(target_chunk_seconds: u32, sample_rate: u32) -> Self {
        Self {
            target_chunk_seconds,
            sample_rate,
            energy_threshold: 0.01,
        }
    }

    /// Segment PCM audio into fixed 20-30s chunks with VAD boundary adjustments.
    pub fn segment_audio(&self, record_id: &str, pcm_samples: &[f32]) -> Vec<AudioChunk> {
        let chunk_size = (self.target_chunk_seconds as usize) * (self.sample_rate as usize);
        if pcm_samples.is_empty() {
            return Vec::new();
        }

        let mut chunks = Vec::new();
        let total_samples = pcm_samples.len();
        let mut start_idx = 0;

        while start_idx < total_samples {
            let mut end_idx = (start_idx + chunk_size).min(total_samples);

            // Fine-tune chunk boundary to nearest low-energy point (silence)
            if end_idx < total_samples {
                let search_window_start = end_idx.saturating_sub(self.sample_rate as usize * 3);
                let search_window_end = (end_idx + self.sample_rate as usize * 3).min(total_samples);

                let mut min_energy = f32::MAX;
                let mut best_cut = end_idx;

                for cut in (search_window_start..search_window_end).step_by(160) {
                    let frame_end = (cut + 160).min(total_samples);
                    let energy: f32 = pcm_samples[cut..frame_end].iter().map(|s| s * s).sum();
                    if energy < min_energy {
                        min_energy = energy;
                        best_cut = cut;
                    }
                }

                if min_energy < self.energy_threshold * 160.0 {
                    end_idx = best_cut;
                }
            }

            let start_ms = ((start_idx as f64 / self.sample_rate as f64) * 1000.0) as u64;
            let end_ms = ((end_idx as f64 / self.sample_rate as f64) * 1000.0) as u64;
            let chunk_id = format!("{}#{}-{}", record_id, start_ms, end_ms);

            chunks.push(AudioChunk {
                chunk_id,
                record_id: record_id.to_string(),
                start_ms,
                end_ms,
                samples: pcm_samples[start_idx..end_idx].to_vec(),
                sample_rate: self.sample_rate,
            });

            start_idx = end_idx;
        }

        chunks
    }
}
