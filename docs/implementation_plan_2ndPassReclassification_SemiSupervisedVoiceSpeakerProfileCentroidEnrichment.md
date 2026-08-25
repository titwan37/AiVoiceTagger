# Semi-Supervised Speaker Profile Centroid Enrichment & Second-Pass Reclassification

Implement a self-training loop to enrich voice profile centroids using high-confidence segments and run a second-pass speaker identification on unidentified segments.

## User Review Required

> [!IMPORTANT]
> The self-training mechanism uses the cosine similarity threshold configured via `--threshold` (or `match_threshold`, which defaults to `0.66`) to identify high-confidence segments to enrich profiles. We weight the pseudo-labeled segments equally with the original seed samples, which updates the centroids without requiring a full re-enrollment of the disk files.

## Proposed Changes

### Voice Biometric Tagger

#### [MODIFY] [enroll_and_identify_speakers.py](file:///c:/Dev/AiVoiceTagger/scripts/enroll_and_identify_speakers.py)

- **Add `self_train_enrichment` method**:
  - Scan existing enrolled actors in `self.enrolled_vault`.
  - For each actor, query the database `speeches` table for up to `max_pseudo_samples` segments where `speaker_tag = actor` AND `speaker_confidence >= self_train_threshold` (e.g. `0.66`).
  - Retrieve the segments (audio files, start/end samples), load the PCM, and extract their SpeechBrain/PyTorch embeddings in batch on the GPU.
  - Calculate the new updated centroid using a weighted average of the original centroid (weight = original `sample_count`) and the newly extracted embeddings (weight = 1 per segment):
    $$\text{centroid}_{\text{new}} = \frac{\text{centroid}_{\text{original}} \times \text{count}_{\text{original}} + \sum \text{embeddings}_{\text{pseudo}}}{\text{count}_{\text{original}} + \text{count}_{\text{pseudo}}}$$
  - Normalize the updated centroid:
    $$\text{centroid}_{\text{new}} \leftarrow \frac{\text{centroid}_{\text{new}}}{\|\text{centroid}_{\text{new}}\|_2}$$
  - Commit the updated centroid to the `speaker_profiles` table (`embedding_blob` and `sample_count`).
  - Update `self.enrolled_vault` in-memory.

- **Add `--self-train` and CLI parameters**:
  - `--self-train`: Activates the profile enrichment process.
  - `--self-train-threshold`: Similarity threshold for selecting pseudo-labeled segments (default: `0.66`).
  - `--max-pseudo-samples`: Maximum number of pseudo-labeled segments to query per speaker profile (default: `50`).
  - `--reclassify-unmatched`: Run a second-pass identification on speeches that are currently marked as `SPEAKER_THIRD_PARTY` or `Speaker Unknown` or `None`.

- **Add `reclassify_unmatched_speeches` method**:
  - Query all records that contain at least one segment with `speaker_tag` matching a third-party/unknown tag.
  - For those records, load the audio file, slice PCM, and batch-evaluate matches against the newly enriched speaker centroids.
  - Commit updated matches, confidence scores, and biomarkers back to `speeches` table.

## Verification Plan

### Automated Tests
- Run `python scripts/enroll_and_identify_speakers.py --self-train --self-train-threshold 0.66 --limit 5` to test the self-training extraction, centroid recalculation, and database updates.

### Manual Verification
- Verify that `speaker_profiles` table contains the updated sample counts and blobs.
- Run the second pass: `python scripts/enroll_and_identify_speakers.py --reclassify-unmatched` and verify that previously unidentified `SPEAKER_THIRD_PARTY` segments are successfully resolved to enrolled actors.
