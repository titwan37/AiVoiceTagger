import { Injectable, NgZone, inject } from '@angular/core';
import { Observable, Subject, interval } from 'rxjs';
import { takeUntil } from 'rxjs/operators';
import { environment } from '../../environments/environment';
import {
  TelemetryPayload, GlobalMetrics, NodeTelemetry, NodeHealth,
  QualityGrade, PipelineStage, PipelineStageCounts, AqiBreakdown,
  TranscriptEntry, DeadLetterEntry
} from '../models/telemetry.models';

@Injectable({ providedIn: 'root' })
export class MonitoringWebSocketService {
  private zone = inject(NgZone);
  private destroy$ = new Subject<void>();
  private messagesSubject = new Subject<TelemetryPayload>();
  private isPaused = false;

  readonly messages$: Observable<TelemetryPayload> = this.messagesSubject.asObservable();

  constructor() {
    if (environment.useMockData) {
      this.startMockStream();
    } else {
      this.startHttpPolling();
    }
  }

  private startHttpPolling(): void {
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
            this.zone.run(() => this.messagesSubject.next(payload));
          }
        })
        .catch(err => {
          console.error('[HttpPolling] Fetch error:', err);
        });
    });
  }

  private startMockStream(): void {
    const models = ['ggml-whisper-large-v3.bin', 'ggml-whisper-medium-q8_0.bin', 'ggml-whisper-small.bin'];
    const stages: PipelineStage[] = ['DISCOVERED', 'QUEUED', 'DECODED', 'TRANSCRIBED', 'NLP_DONE', 'EXPORTED', 'DONE'];
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
        story: 'Industrial automated triage verified. Speech quality grade GOOD with clear formant envelope and zero clipping.',
        speech_count: 14,
        is_degraded: false,
        state: 'TRIAGED_HIGH',
        updated_at: new Date().toISOString()
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
        updated_at: new Date(Date.now() - 15000).toISOString()
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
        updated_at: new Date(Date.now() - 35000).toISOString()
      }
    ];

    const deadLettersSeed: DeadLetterEntry[] = [
      {
        id: 1,
        record_id: 'dlq-4019-f',
        chunk_id: 'chk-01',
        stage: 'DECODED',
        error: 'FFmpeg lock-free frame decoder: invalid sync byte at offset 0x004F2A (CRC32 mismatch)',
        context_json: '{"source":"nas://archive/corrupt_header_2024_02.mp3","retry_count":1}',
        created_at: new Date(Date.now() - 120000).toISOString()
      },
      {
        id: 2,
        record_id: 'dlq-4022-k',
        chunk_id: 'chk-04',
        stage: 'TRANSCRIBED',
        error: 'Whisper inference sidecar backpressure timeout (>45000ms) during large-v3 tensor allocation',
        context_json: '{"source":"edge://pc2/buffer/timeout_gpu_vram_spike.flac","retry_count":2}',
        created_at: new Date(Date.now() - 340000).toISOString()
      }
    ];

    let tickCount = 18;

    interval(environment.mockIntervalMs || 2000).pipe(
      takeUntil(this.destroy$)
    ).subscribe(() => {
      if (!this.isPaused) {
        tickCount++;
      }

      const nodeCount = 3;
      const nodes: NodeTelemetry[] = [
        {
          worker_id: 'pc1-master-worker',
          cpu_affinity: '0-5 (NUMA 0)',
          health: 'HEALTHY',
          active_file: files[tickCount % files.length],
          current_stage: this.isPaused ? 'QUEUED' : stages[(tickCount + 1) % stages.length],
          chunk_progress_percent: this.isPaused ? 45 : (tickCount * 17) % 100,
          loaded_model: models[0],
          sidecar_status: 'ACTIVE',
          resources: {
            cpu_percent: this.isPaused ? 8 : Math.round(42 + Math.sin(tickCount) * 15),
            rss_memory_mb: 840 + Math.round(Math.cos(tickCount) * 40),
            ipc_messages_per_sec: this.isPaused ? 0 : Math.round(28 + Math.random() * 12),
          },
          lease_expires_at: new Date(Date.now() + 300_000).toISOString(),
          last_heartbeat: new Date().toISOString(),
          records_processed: 2410 + tickCount * 2,
          current_aqi: 'GOOD'
        },
        {
          worker_id: 'pc2-secondary-worker',
          cpu_affinity: '6-11 (NUMA 1)',
          health: 'HEALTHY',
          active_file: files[(tickCount + 3) % files.length],
          current_stage: this.isPaused ? 'QUEUED' : stages[(tickCount + 3) % stages.length],
          chunk_progress_percent: this.isPaused ? 60 : (tickCount * 23) % 100,
          loaded_model: models[1],
          sidecar_status: 'ACTIVE',
          resources: {
            cpu_percent: this.isPaused ? 5 : Math.round(38 + Math.cos(tickCount) * 12),
            rss_memory_mb: 610 + Math.round(Math.sin(tickCount) * 30),
            ipc_messages_per_sec: this.isPaused ? 0 : Math.round(22 + Math.random() * 8),
          },
          lease_expires_at: new Date(Date.now() + 300_000).toISOString(),
          last_heartbeat: new Date().toISOString(),
          records_processed: 1980 + tickCount,
          current_aqi: (tickCount % 5 === 0) ? 'DEGRADED' : 'GOOD'
        },
        {
          worker_id: 'edge-sidecar-worker',
          cpu_affinity: '12-15 (Edge)',
          health: 'HEALTHY',
          active_file: files[(tickCount + 5) % files.length],
          current_stage: this.isPaused ? 'QUEUED' : stages[(tickCount + 5) % stages.length],
          chunk_progress_percent: this.isPaused ? 30 : (tickCount * 11) % 100,
          loaded_model: models[2],
          sidecar_status: 'ACTIVE',
          resources: {
            cpu_percent: this.isPaused ? 4 : Math.round(24 + Math.random() * 10),
            rss_memory_mb: 420 + Math.round(Math.random() * 20),
            ipc_messages_per_sec: this.isPaused ? 0 : Math.round(15 + Math.random() * 5),
          },
          lease_expires_at: new Date(Date.now() + 300_000).toISOString(),
          last_heartbeat: new Date().toISOString(),
          records_processed: 1140 + tickCount,
          current_aqi: 'GOOD'
        }
      ];

      const totalDiscovered = 6539;
      const totalDone = 5530 + Math.floor(tickCount * 2.5);
      const audioDuration = totalDone * 192; // avg ~192 sec per file
      const wallClock = tickCount * 2;

      const aqi: AqiBreakdown = {
        good: Math.floor(totalDone * 0.76),
        degraded: Math.floor(totalDone * 0.18),
        unusable: Math.floor(totalDone * 0.06),
      };

      const stageCounts: PipelineStageCounts = {
        discovered: Math.max(0, totalDiscovered - totalDone - 24),
        queued: this.isPaused ? 45 : 8,
        decoded: this.isPaused ? 0 : 4,
        transcribed: this.isPaused ? 0 : 6,
        nlp_done: this.isPaused ? 0 : 3,
        exported: this.isPaused ? 0 : 2,
        done: totalDone,
        dead_letter: deadLettersSeed.length,
        failed: 3,
        retry: 1,
      };

      const global: GlobalMetrics = {
        total_discovered: totalDiscovered,
        total_queued: stageCounts.queued,
        total_done: totalDone,
        audio_duration_processed_sec: audioDuration,
        wall_clock_elapsed_sec: wallClock,
        real_time_factor: 14.8, // 14.8x real-time factor
        aqi_breakdown: aqi,
        dead_letter_count: stageCounts.dead_letter,
        failure_count: stageCounts.failed,
        pipeline_stage_counts: stageCounts,
        time_windows: {
          '1h': { completed: 420, audio_sec: 420 * 190, good: 330, degraded: 70, unusable: 20, real_time_factor: 15.2 },
          '4h': { completed: 1680, audio_sec: 1680 * 190, good: 1310, degraded: 280, unusable: 90, real_time_factor: 14.9 },
          '12h': { completed: 4100, audio_sec: 4100 * 190, good: 3180, degraded: 710, unusable: 210, real_time_factor: 14.8 },
          'all': { completed: totalDone, audio_sec: audioDuration, good: aqi.good, degraded: aqi.degraded, unusable: aqi.unusable, real_time_factor: 14.8 }
        }
      };

      const payload: TelemetryPayload = {
        timestamp: new Date().toISOString(),
        global,
        nodes,
        transcripts: transcriptsSeed,
        dead_letters: deadLettersSeed,
        is_paused: this.isPaused
      };

      this.zone.run(() => this.messagesSubject.next(payload));
    });
  }

  async sendCommand(endpoint: string, payload: any = {}): Promise<any> {
    if (environment.useMockData) {
      if (endpoint === 'pause') {
        this.isPaused = !this.isPaused;
        return { status: 'ok', is_paused: this.isPaused };
      }
      if (endpoint === 'retry') {
        return { status: 'ok', message: `Record ${payload.record_id || 'ID'} re-queued successfully` };
      }
      return { status: 'ok' };
    }

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