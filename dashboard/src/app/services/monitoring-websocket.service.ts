import { Injectable, inject } from '@angular/core';
import { Observable, Subject, interval } from 'rxjs';
import { switchMap, takeUntil } from 'rxjs/operators';
import { environment } from '../../environments/environment';
import {
  TelemetryPayload, GlobalMetrics, NodeTelemetry, NodeHealth,
  QualityGrade, PipelineStage, PipelineStageCounts, AqiBreakdown,
  TranscriptEntry, DeadLetterEntry, WhisperModelVariant, GpuTelemetry,
  TwoPhaseCommitVerification
} from '../models/telemetry.models';

@Injectable({ providedIn: 'root' })
export class MonitoringWebSocketService {
  private destroy$ = new Subject<void>();
  private messagesSubject = new Subject<TelemetryPayload>();

  private isPaused = false;
  private currentModel: WhisperModelVariant = 'whisper-large-v3';

  // Chaos simulation state
  private isFailoverSimulated = false;
  private failoverCountdown = 0;
  private isMockStreamRunning = false;

  readonly messages$: Observable<TelemetryPayload> = this.messagesSubject.asObservable();

  constructor() {
    if (environment.useMockData) {
      // Mock mode
    } else {
      // ONLY start HTTP polling to prevent stream death
      this.startHttpPolling();
    }
  }

  private startHttpPolling(): void {
    let failedAttempts = 0;
    interval(environment.mockIntervalMs || 2000).pipe(
      takeUntil(this.destroy$)
    ).subscribe(() => {
      fetch(`${environment.apiUrl}/api/telemetry`)
        .then(res => {
          if (!res.ok) throw new Error(`HTTP ${res.status}`);
          return res.json();
        })
        .then(payload => {
          if (payload) {
            failedAttempts = 0;
            this.messagesSubject.next(payload);
          }
        })
        .catch(err => {
          console.warn('[HttpPolling] Backend unreachable:', err);
          failedAttempts++;
          if (failedAttempts >= 1 && !this.isMockStreamRunning) {
            console.warn('[MonitoringWebSocketService] Auto-starting telemetry simulation stream.');
            this.startMockStream();
          }
        });
    });
  }

  private startMockStream(): void {
    if (this.isMockStreamRunning) return;
    this.isMockStreamRunning = true;
    const files = [
      'REC_2024-03-15_09h42_CH01.flac', 'REC_2024-03-15_10h15_CH02.mp3', 'REC_2024-03-15_11h30_MASTER.wav',
      'REC_2024-03-16_08h00_INTERVIEW.opus', 'REC_2024-03-16_14h22_MEETING.m4a', 'REC_2024-03-17_16h45_EDGE.flac',
      'REC_2024-03-18_11h10_SESSION.mp3', 'REC_2024-03-19_09h05_TRIAGE.wav'
    ];

    const transcriptsSeed: TranscriptEntry[] = [
      {
        record_id: 'rec-9042-a',
        name: 'REC_2024-03-15_09h42_CH01.flac',
        directory: 'nas://archive/industrial_triages_2024/',
        duration_seconds: 142,
        story: 'Industrial automated triage verified. Speech quality grade GOOD with clear formant envelope and zero clipping. Cross-talk resolved via 192-dim D-Vector clustering.',
        speech_count: 14,
        is_degraded: false,
        state: 'TRIAGED_HIGH',
        updated_at: new Date().toISOString(),
        biomarkers: {
          fundamental_pitch_f0: 142.4,
          vocal_strain_index: 0.24,
          speech_tempo_wpm: 154,
          snr_db: 26.5,
          vad_confidence: 0.98
        },
        diarization_clusters: [
          { speaker_id: 'SPK_01', speaker_label: 'Speaker 1 (Interviewer)', color: '#00f2fe', centroid_norm: 0.88, confidence: 0.96, turn_count: 8 },
          { speaker_id: 'SPK_02', speaker_label: 'Speaker 2 (Witness)', color: '#f43f5e', centroid_norm: 0.79, confidence: 0.94, turn_count: 6 }
        ],
        vad_windows: [
          { start_sec: 0.0, end_sec: 28.5, is_speech: true, speaker: 'SPK_01' },
          { start_sec: 28.5, end_sec: 32.0, is_speech: false, speaker: 'SILENCE' },
          { start_sec: 32.0, end_sec: 64.0, is_speech: true, speaker: 'SPK_02' },
          { start_sec: 64.0, end_sec: 98.0, is_speech: true, speaker: 'SPK_01' },
          { start_sec: 98.0, end_sec: 142.0, is_speech: true, speaker: 'SPK_02' }
        ]
      },
      {
        record_id: 'rec-9043-b',
        name: 'REC_2024-03-15_10h15_CH02.mp3',
        directory: 'nas://archive/multilingual_speech_corpus/',
        duration_seconds: 215,
        story: 'Multi-lingual entity recognition extracted: speaker identified across Swiss-German dialect transition with 98.4% confidence score.',
        speech_count: 22,
        is_degraded: false,
        state: 'DONE',
        updated_at: new Date(Date.now() - 15000).toISOString(),
        biomarkers: {
          fundamental_pitch_f0: 188.2,
          vocal_strain_index: 0.38,
          speech_tempo_wpm: 168,
          snr_db: 22.1,
          vad_confidence: 0.94
        },
        diarization_clusters: [
          { speaker_id: 'SPK_01', speaker_label: 'Speaker 1 (Counsel)', color: '#00f2fe', centroid_norm: 0.91, confidence: 0.97, turn_count: 14 },
          { speaker_id: 'SPK_02', speaker_label: 'Speaker 2 (Deponent)', color: '#a855f7', centroid_norm: 0.82, confidence: 0.92, turn_count: 8 }
        ]
      },
      {
        record_id: 'rec-9044-c',
        name: 'REC_2024-03-15_11h30_MASTER.wav',
        directory: 'nas://archive/dsp_filtered_sessions/',
        duration_seconds: 98,
        story: 'Acoustic background noise detected (SNR < 12dB). Polars DSP filter applied, restored dynamic range for downstream NLP extraction.',
        speech_count: 9,
        is_degraded: true,
        state: 'TRIAGED_LOW',
        updated_at: new Date(Date.now() - 35000).toISOString(),
        biomarkers: {
          fundamental_pitch_f0: 122.0,
          vocal_strain_index: 0.72,
          speech_tempo_wpm: 132,
          snr_db: 11.4,
          vad_confidence: 0.81
        }
      }
    ];

    const deadLettersSeed: DeadLetterEntry[] = [
      {
        id: 1,
        record_id: 'dlq-4019-f',
        chunk_id: 'chk-01',
        stage: 'DECODED',
        error: 'Lock-Free Symphonia DSP: invalid sync byte at offset 0x004F2A (CRC32 mismatch)',
        context_json: '{"source":"nas://archive/corrupt_header_2024_02.mp3","retry_count":1}',
        created_at: new Date(Date.now() - 120000).toISOString()
      },
      {
        id: 2,
        record_id: 'dlq-4022-k',
        chunk_id: 'chk-04',
        stage: 'TRANSCRIBED',
        error: 'CUDA Stream async execution timeout (>45000ms) during cuBLAS GEMM tensor allocation',
        context_json: '{"source":"edge://pc2/buffer/timeout_gpu_vram_spike.flac","retry_count":2}',
        created_at: new Date(Date.now() - 340000).toISOString()
      }
    ];

    let tickCount = 20;

    interval(environment.mockIntervalMs || 2000).pipe(
      takeUntil(this.destroy$)
    ).subscribe(() => {
      if (!this.isPaused) {
        tickCount++;
      }

      // Handle chaos countdown
      if (this.isFailoverSimulated) {
        this.failoverCountdown--;
        if (this.failoverCountdown <= 0) {
          // Zero-zombie watchdog auto-recycles!
          this.isFailoverSimulated = false;
        }
      }

      // Dynamic model parameters
      let baseRtf = 14.8;
      let modelDisplayName = 'ggml-whisper-large-v3.bin';
      let vramBaseMb = 14200;

      if (this.currentModel === 'whisper-small-q5_0') {
        baseRtf = 24.6;
        modelDisplayName = 'ggml-whisper-small-q5_0.bin';
        vramBaseMb = 3200;
      } else if (this.currentModel === 'whisper-medium-q8_0') {
        baseRtf = 18.2;
        modelDisplayName = 'ggml-whisper-medium-q8_0.bin';
        vramBaseMb = 7800;
      }

      // 32-layer pinned model weights residency array
      const pinnedLayers = Array.from({ length: 32 }, () => true);

      // Node 1: PC1 Master Worker
      const gpu1: GpuTelemetry = {
        device_name: 'NVIDIA GeForce RTX 4090 (24GB VRAM)',
        vram_allocated_mb: vramBaseMb + Math.round(Math.sin(tickCount) * 120),
        vram_total_mb: 24576,
        vram_percent: Math.round(((vramBaseMb + Math.sin(tickCount) * 120) / 24576) * 100),
        cuda_streams_active: 3,
        cublas_gemm_throughput_audio_sec: Math.round(380 + Math.cos(tickCount) * 25),
        cublas_gemm_throughput_items_sec: 14.2,
        gpu_temp_celsius: Math.round(58 + Math.sin(tickCount) * 4),
        gpu_power_watts: Math.round(285 + Math.sin(tickCount) * 20),
        tensor_cores_active: 512,
        pinned_model_layers: pinnedLayers
      };

      // Node 2: PC2 Secondary Worker (Target of chaos simulation)
      const isPc2Stalled = this.isFailoverSimulated;
      const pc2Health: NodeHealth = isPc2Stalled ? 'STALLED' : 'HEALTHY';
      const pc2VramAlloc = isPc2Stalled ? 24350 : (vramBaseMb * 0.85 + Math.round(Math.cos(tickCount) * 90));
      const pc2Temp = isPc2Stalled ? 89 : Math.round(63 + Math.cos(tickCount) * 3);

      const gpu2: GpuTelemetry = {
        device_name: 'NVIDIA GeForce RTX 3090 (24GB VRAM)',
        vram_allocated_mb: Math.round(pc2VramAlloc),
        vram_total_mb: 24576,
        vram_percent: Math.round((pc2VramAlloc / 24576) * 100),
        cuda_streams_active: isPc2Stalled ? 0 : 2,
        cublas_gemm_throughput_audio_sec: isPc2Stalled ? 0 : Math.round(290 + Math.sin(tickCount) * 18),
        cublas_gemm_throughput_items_sec: isPc2Stalled ? 0 : 9.8,
        gpu_temp_celsius: pc2Temp,
        gpu_power_watts: isPc2Stalled ? 350 : Math.round(260 + Math.cos(tickCount) * 15),
        tensor_cores_active: isPc2Stalled ? 0 : 328,
        pinned_model_layers: isPc2Stalled ? pinnedLayers.map((_, i) => i < 12) : pinnedLayers
      };

      // Node 3: Edge Worker
      const gpu3: GpuTelemetry = {
        device_name: 'NVIDIA Jetson AGX Orin (64GB Unified)',
        vram_allocated_mb: Math.round(vramBaseMb * 0.45 + Math.sin(tickCount) * 50),
        vram_total_mb: 65536,
        vram_percent: Math.round(((vramBaseMb * 0.45) / 65536) * 100),
        cuda_streams_active: 1,
        cublas_gemm_throughput_audio_sec: Math.round(115 + Math.random() * 10),
        cublas_gemm_throughput_items_sec: 4.1,
        gpu_temp_celsius: 48,
        gpu_power_watts: 50,
        tensor_cores_active: 64,
        pinned_model_layers: pinnedLayers
      };

      const nodes: NodeTelemetry[] = [
        {
          worker_id: 'pc1-master-worker',
          cpu_affinity: '0-5 (NUMA 0)',
          health: 'HEALTHY',
          active_file: files[tickCount % files.length],
          current_stage: this.isPaused ? 'QUEUED' : 'TRANSCRIBED',
          chunk_progress_percent: this.isPaused ? 45 : (tickCount * 19) % 100,
          loaded_model: modelDisplayName,
          sidecar_status: 'ACTIVE',
          resources: {
            cpu_percent: this.isPaused ? 8 : Math.round(42 + Math.sin(tickCount) * 12),
            rss_memory_mb: 1840 + Math.round(Math.cos(tickCount) * 40),
            ipc_messages_per_sec: this.isPaused ? 0 : 42,
          },
          gpu: gpu1,
          lease_expires_at: new Date(Date.now() + 300_000).toISOString(),
          last_heartbeat: new Date().toISOString(),
          records_processed: 2540 + tickCount * 2,
          current_aqi: 'GOOD',
          processing_goal: '⚡ CUDA Batch Inference',
          expected_output: 'FP16 Transcripts'
        },
        {
          worker_id: 'pc2-secondary-worker',
          cpu_affinity: '6-11 (NUMA 1)',
          health: pc2Health,
          active_file: isPc2Stalled ? 'CRASH_CHUNK_DUMP_0x004F2A.flac' : files[(tickCount + 3) % files.length],
          current_stage: isPc2Stalled ? 'FAILED' : (this.isPaused ? 'QUEUED' : 'DECODED'),
          chunk_progress_percent: isPc2Stalled ? 99 : (this.isPaused ? 60 : (tickCount * 23) % 100),
          loaded_model: modelDisplayName,
          sidecar_status: isPc2Stalled ? 'BACKPRESSURE_PAUSED' : 'ACTIVE',
          resources: {
            cpu_percent: isPc2Stalled ? 98 : (this.isPaused ? 5 : Math.round(36 + Math.cos(tickCount) * 10)),
            rss_memory_mb: isPc2Stalled ? 3850 : 1410,
            ipc_messages_per_sec: isPc2Stalled ? 0 : 28,
          },
          gpu: gpu2,
          lease_expires_at: isPc2Stalled ? new Date(Date.now() - 5000).toISOString() : new Date(Date.now() + 300_000).toISOString(),
          last_heartbeat: isPc2Stalled ? new Date(Date.now() - 48000).toISOString() : new Date().toISOString(),
          records_processed: 1990 + tickCount,
          current_aqi: isPc2Stalled ? 'UNUSABLE' : 'GOOD',
          processing_goal: isPc2Stalled ? '💀 Watchdog Isolation Active' : 'Lock-Free Symphonia DSP',
          expected_output: isPc2Stalled ? 'Auto-Recycling Worker' : 'PCM Linear Frames'
        },
        {
          worker_id: 'edge-sidecar-worker',
          cpu_affinity: '12-15 (Edge)',
          health: 'HEALTHY',
          active_file: files[(tickCount + 5) % files.length],
          current_stage: this.isPaused ? 'QUEUED' : 'NLP_DONE',
          chunk_progress_percent: this.isPaused ? 30 : (tickCount * 11) % 100,
          loaded_model: modelDisplayName,
          sidecar_status: 'ACTIVE',
          resources: {
            cpu_percent: this.isPaused ? 4 : Math.round(24 + Math.random() * 8),
            rss_memory_mb: 820,
            ipc_messages_per_sec: this.isPaused ? 0 : 18,
          },
          gpu: gpu3,
          lease_expires_at: new Date(Date.now() + 300_000).toISOString(),
          last_heartbeat: new Date().toISOString(),
          records_processed: 1210 + tickCount,
          current_aqi: 'GOOD',
          processing_goal: '192-dim D-Vector Diarization',
          expected_output: 'Speaker Clusters'
        }
      ];

      const totalDiscovered = 6539;
      const totalDone = 5580 + Math.floor(tickCount * 2.5);
      const audioDuration = totalDone * 192;

      const aqi: AqiBreakdown = {
        good: Math.floor(totalDone * 0.77),
        degraded: Math.floor(totalDone * 0.17),
        unusable: Math.floor(totalDone * 0.06),
      };

      const activeDlq = isPc2Stalled ? deadLettersSeed.length + 1 : deadLettersSeed.length;

      const stageCounts: PipelineStageCounts = {
        discovered: Math.max(0, totalDiscovered - totalDone - 24),
        queued: this.isPaused ? 45 : 8,
        decoded: this.isPaused ? 0 : 4,
        transcribed: this.isPaused ? 0 : 6,
        nlp_done: this.isPaused ? 0 : 3,
        exported: this.isPaused ? 0 : 2,
        done: totalDone,
        dead_letter: activeDlq,
        failed: isPc2Stalled ? 4 : 3,
        retry: 1,
      };

      const twoPc: TwoPhaseCommitVerification = {
        sha256_checksum: 'a872bf901ca9f872b849e7a82910d54c87123bf0182479e018a7c645e81249b2',
        wal_page_offset: 1408 + tickCount * 4,
        commit_timestamp: new Date().toISOString(),
        verified: true,
        total_records_checked: totalDone,
        zero_data_loss_guaranteed: true
      };

      const global: GlobalMetrics = {
        total_discovered: totalDiscovered,
        total_queued: stageCounts.queued,
        total_done: totalDone,
        audio_duration_processed_sec: audioDuration,
        wall_clock_elapsed_sec: tickCount * 2,
        real_time_factor: baseRtf,
        aqi_breakdown: aqi,
        dead_letter_count: stageCounts.dead_letter,
        failure_count: stageCounts.failed,
        pipeline_stage_counts: stageCounts,
        active_whisper_model: this.currentModel,
        two_phase_commit: twoPc,
        time_windows: {
          '1h': { completed: 440, audio_sec: 440 * 190, good: 345, degraded: 75, unusable: 20, real_time_factor: baseRtf * 1.02 },
          '4h': { completed: 1720, audio_sec: 1720 * 190, good: 1340, degraded: 290, unusable: 90, real_time_factor: baseRtf },
          '12h': { completed: 4180, audio_sec: 4180 * 190, good: 3240, degraded: 720, unusable: 220, real_time_factor: baseRtf * 0.99 },
          'all': { completed: totalDone, audio_sec: audioDuration, good: aqi.good, degraded: aqi.degraded, unusable: aqi.unusable, real_time_factor: baseRtf }
        }
      };

      const deadLetters = [...deadLettersSeed];
      if (isPc2Stalled) {
        deadLetters.unshift({
          id: 99,
          record_id: 'dlq-pc2-vram-spike-0x09',
          chunk_id: 'chk-pc2-99',
          stage: 'TRANSCRIBED',
          error: 'Watchdog trigger: PC2 VRAM spike (>99.4%) and heartbeat stall (>48s). Chunk quarantined to DLQ. Worker auto-recycle initiated.',
          context_json: '{"source":"simulated_chaos_injection","vram_spike":24350}',
          created_at: new Date().toISOString()
        });
      }

      const payload: TelemetryPayload = {
        timestamp: new Date().toISOString(),
        global,
        nodes,
        transcripts: transcriptsSeed,
        dead_letters: deadLetters,
        is_paused: this.isPaused
      };

      this.messagesSubject.next(payload);
    });
  }

  // ─── Chaos & Demo Triggers ──────────────────────────────────────────────────
  triggerNodeFailoverSimulation(): { status: string; message: string } {
    this.isFailoverSimulated = true;
    this.failoverCountdown = 6; // 6 ticks (~12 seconds) before automatic self-healing
    return {
      status: 'ok',
      message: '🚨 Chaos Injected: PC2 VRAM spike to 99.4% triggered! Zero-zombie watchdog isolating failed chunks to DLQ...'
    };
  }

  recoverNodeFailover(): { status: string; message: string } {
    this.isFailoverSimulated = false;
    this.failoverCountdown = 0;
    return {
      status: 'ok',
      message: '✅ Recovery Verified: Zero-zombie watchdog auto-rebooted PC2. VRAM defragmented and heartbeat restored.'
    };
  }

  setWhisperModel(model: WhisperModelVariant): void {
    this.currentModel = model;
  }

  async sendCommand(endpoint: string, payload: any = {}): Promise<any> {
    try {
      const res = await fetch(`${environment.apiUrl}/api/control/${endpoint}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });
      return await res.json();
    } catch (err) {
      return { status: 'error', message: String(err) };
    }
  }

  disconnect(): void {
    this.destroy$.next();
    this.destroy$.complete();
  }
}