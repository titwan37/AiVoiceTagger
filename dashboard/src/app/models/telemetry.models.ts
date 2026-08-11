// ──────────────────────────────────────────────────────────────────────────────
// AiVoiceTagger Supervisor Dashboard — Core Domain Models
// Mirrors Rust-side models.rs enums and structs for telemetry payloads.
// ──────────────────────────────────────────────────────────────────────────────

/** Pipeline state machine stages (mirrors Rust RecordState enum). */
export type PipelineStage =
  | 'DISCOVERED'
  | 'QUEUED'
  | 'DECODED'
  | 'TRIAGED_HIGH'
  | 'TRIAGED_LOW'
  | 'TRANSCRIBED'
  | 'NLP_DONE'
  | 'EXPORTED'
  | 'DONE'
  | 'DEAD_LETTER'
  | 'FAILED'
  | 'RETRY';

/** Audio Quality Index grade (mirrors Rust QualityGrade enum). */
export type QualityGrade = 'GOOD' | 'DEGRADED' | 'UNUSABLE';

/** Health status of a worker node derived from heartbeat freshness. */
export type NodeHealth = 'HEALTHY' | 'STALLED' | 'OFFLINE';

/** Status of the Python NLP sidecar IPC process. */
export type SidecarStatus = 'ACTIVE' | 'RESTARTING' | 'BACKPRESSURE_PAUSED' | 'OFFLINE';

/** WebSocket connection state. */
export type ConnectionStatus = 'CONNECTED' | 'RECONNECTING' | 'DISCONNECTED';

/** AQI count breakdown for global metrics. */
export interface AqiBreakdown {
  good: number;
  degraded: number;
  unusable: number;
}

/** Record counts per pipeline stage for the global funnel visualization. */
export interface PipelineStageCounts {
  discovered: number;
  queued: number;
  decoded: number;
  triaged_high?: number;
  triaged_low?: number;
  transcribed: number;
  nlp_done: number;
  exported: number;
  done: number;
  dead_letter: number;
  failed: number;
  retry: number;
}

export interface WindowStat {
  completed: number;
  audio_sec: number;
  good: number;
  degraded: number;
  unusable: number;
  real_time_factor: number;
}

export interface TimeWindowStats {
  '1h': WindowStat;
  '4h': WindowStat;
  '12h': WindowStat;
  'all': WindowStat;
}

/** Resource utilization metrics for a single worker node. */
export interface ResourceMetrics {
  cpu_percent: number;
  rss_memory_mb: number;
  ipc_messages_per_sec: number;
}

/** Per-worker node telemetry snapshot. */
export interface NodeTelemetry {
  worker_id: string;
  cpu_affinity: string;
  health: NodeHealth;
  active_file: string;
  current_stage: PipelineStage;
  chunk_progress_percent: number;
  loaded_model: string;
  sidecar_status: SidecarStatus;
  resources: ResourceMetrics;
  lease_expires_at: string;
  last_heartbeat: string;
  records_processed: number;
  current_aqi: QualityGrade;
  processing_goal?: string;
  goal_description?: string;
  expected_output?: string;
}

/** Aggregated global telemetry metrics. */
export interface EvidenceStats {
  triaged_high_count: number;
  recordstrike_count: number;
  high_pattern_match_count: number;
  avg_intensity: number;
  legal_categories: {
    harcelement_moral: number;
    menaces_violences: number;
    contrainte_domestique: number;
    obstruction_preuve: number;
  };
}

export interface GlobalMetrics {
  total_discovered: number;
  total_queued: number;
  total_done: number;
  audio_duration_processed_sec: number;
  wall_clock_elapsed_sec: number;
  real_time_factor: number;
  aqi_breakdown: AqiBreakdown;
  dead_letter_count: number;
  failure_count: number;
  pipeline_stage_counts: PipelineStageCounts;
  time_windows?: TimeWindowStats;
  evidence_stats?: EvidenceStats;
}

export interface TranscriptEntry {
  record_id: string;
  name: string;
  directory: string;
  duration_seconds: number;
  speech_count: number;
  story: string;
  is_degraded: boolean;
  state: string;
  updated_at: string;
  verbatim?: Record<string, number>;
}

export interface DeadLetterEntry {
  id: number;
  record_id: string;
  chunk_id?: string;
  stage: string;
  error: string;
  context_json?: string;
  created_at: string;
}

export interface TelemetryDelta {
  type: 'NODE_UPDATE' | 'TRANSCRIPT_NEW' | 'DEAD_LETTER_NEW' | 'GLOBAL_METRIC';
  payload: any;
}

/** Root telemetry payload received from WebSocket / REST API. */
export interface TelemetryPayload {
  timestamp: string;
  global: GlobalMetrics;
  nodes: NodeTelemetry[];
  transcripts?: TranscriptEntry[];
  dead_letters?: DeadLetterEntry[];
  is_paused?: boolean;
}
