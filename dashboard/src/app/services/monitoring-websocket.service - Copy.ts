import { Injectable, NgZone, inject } from '@angular/core';
import { Observable, Subject, interval, map, timer, EMPTY } from 'rxjs';
import { webSocket, WebSocketSubject } from 'rxjs/webSocket';
import { retry, switchMap, catchError, takeUntil } from 'rxjs/operators';
import { environment } from '../../environments/environment';
import {
  TelemetryPayload, GlobalMetrics, NodeTelemetry, NodeHealth,
  SidecarStatus, QualityGrade, PipelineStage, PipelineStageCounts, AqiBreakdown
} from '../models/telemetry.models';

// In monitoring-websocket.service.ts
interface TelemetryDelta {
  type: 'NODE_UPDATE' | 'TRANSCRIPT_NEW' | 'GLOBAL_METRIC';
  payload: any;
}


@Injectable({ providedIn: 'root' })
export class MonitoringWebSocketService {
  private zone = inject(NgZone);
  private destroy$ = new Subject<void>();
  private messagesSubject = new Subject<TelemetryPayload>();

  /** Observable stream of telemetry payloads. */
  readonly messages$: Observable<TelemetryPayload> = this.messagesSubject.asObservable();

  private wsSubject: WebSocketSubject<TelemetryPayload> | null = null;
  private reconnectAttempts = 0;
  private readonly MAX_BACKOFF_MS = 30_000;

  constructor() {
    if (environment.useMockData) {
      this.startMockStream();
    } else {
      // Use resilient HTTP polling as the primary data transport
      this.startHttpPolling();

      // Only connect WebSocket if explicitly configured and non-empty
      if (environment.wsUrl) {
        this.connectWebSocket();
      }
    }
  }

  private startHttpPolling(): void {
    interval(environment.mockIntervalMs || 2000).pipe(
      takeUntil(this.destroy$),
      switchMap(() =>
        fetch(`${environment.apiUrl}/api/telemetry`)
          .then(res => {
            if (!res.ok) throw new Error(`HTTP ${res.status}`);
            return res.json();
          })
          .catch(err => {
            console.error('[HttpPolling] Fetch error:', err);
            return null;
          })
      )
    ).subscribe(payload => {
      if (payload) {
        // Guarantee NgZone execution so Signals/Change Detection update immediately
        this.zone.run(() => this.messagesSubject.next(payload));
      }
    });
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
      console.error(`[Command] Error sending control command '${endpoint}':`, err);
      return { status: 'error', message: String(err) };
    }
  }

  // ─── Mock Data Generator ────────────────────────────────────────────────────
  private startMockStream(): void {
    const models = ['ggml-small-q8_0.bin', 'ggml-large-v3-q5_0.bin', 'ggml-medium-q8_0.bin'];
    const stages: PipelineStage[] = ['DISCOVERED', 'QUEUED', 'DECODED', 'TRANSCRIBED', 'NLP_DONE', 'EXPORTED', 'DONE'];
    const files = [
      'REC_2024-03-15_09h42.mp3', 'REC_2024-03-15_10h15.mp3', 'REC_2024-03-15_11h30.mp3',
      'REC_2024-03-16_08h00.mp3', 'REC_2024-03-16_14h22.mp3', 'REC_2024-03-17_16h45.mp3',
    ];

    let tickCount = 0;

    interval(environment.mockIntervalMs).pipe(takeUntil(this.destroy$)).subscribe(() => {
      tickCount++;

      const nodeCount = 3;
      const nodes: NodeTelemetry[] = [];

      for (let i = 1; i <= nodeCount; i++) {
        const stageIdx = Math.min(Math.floor(Math.random() * stages.length), stages.length - 1);
        const health: NodeHealth = i === 3 && tickCount % 15 === 0 ? 'STALLED' : 'HEALTHY';
        const progress = Math.min(100, Math.floor(Math.random() * 100));

        nodes.push({
          worker_id: `node-${i}`,
          cpu_affinity: `${(i - 1) * 6}-${i * 6 - 1}`,
          health,
          active_file: files[Math.floor(Math.random() * files.length)],
          current_stage: stages[stageIdx],
          chunk_progress_percent: progress,
          loaded_model: i === 2 && progress < 30 ? models[1] : models[0],
          sidecar_status: health === 'STALLED' ? 'BACKPRESSURE_PAUSED' : 'ACTIVE',
          resources: {
            cpu_percent: Math.round(30 + Math.random() * 60),
            rss_memory_mb: Math.round(400 + Math.random() * 600),
            ipc_messages_per_sec: Math.round(5 + Math.random() * 25),
          },
          lease_expires_at: new Date(Date.now() + 300_000).toISOString(),
          last_heartbeat: new Date(Date.now() - Math.floor(Math.random() * (health === 'STALLED' ? 90_000 : 15_000))).toISOString(),
          records_processed: Math.floor(tickCount * (3 + Math.random() * 2)),
          current_aqi: (['GOOD', 'GOOD', 'GOOD', 'DEGRADED', 'UNUSABLE'] as QualityGrade[])[Math.floor(Math.random() * 5)],
        });
      }

      const totalDone = Math.floor(tickCount * 3.2);
      const totalDiscovered = 6539;
      const audioDuration = totalDone * 185;
      const wallClock = tickCount * (environment.mockIntervalMs / 1000);

      const aqi: AqiBreakdown = {
        good: Math.floor(totalDone * 0.72),
        degraded: Math.floor(totalDone * 0.21),
        unusable: Math.floor(totalDone * 0.07),
      };

      const stageCounts: PipelineStageCounts = {
        discovered: totalDiscovered - totalDone - 45,
        queued: 12,
        decoded: 5,
        transcribed: 8,
        nlp_done: 4,
        exported: 3,
        done: totalDone,
        dead_letter: Math.floor(totalDone * 0.005),
        failed: Math.floor(totalDone * 0.002),
        retry: 2,
      };

      const global: GlobalMetrics = {
        total_discovered: totalDiscovered,
        total_queued: stageCounts.queued,
        total_done: totalDone,
        audio_duration_processed_sec: audioDuration,
        wall_clock_elapsed_sec: wallClock,
        real_time_factor: wallClock > 0 ? audioDuration / wallClock : 0,
        aqi_breakdown: aqi,
        dead_letter_count: stageCounts.dead_letter,
        failure_count: stageCounts.failed,
        pipeline_stage_counts: stageCounts,
      };

      const payload: TelemetryPayload = {
        timestamp: new Date().toISOString(),
        global,
        nodes,
      };

      this.messagesSubject.next(payload);
    });
  }

  // ─── Real WebSocket Connection ──────────────────────────────────────────────
  private connectWebSocket(): void {

    // IMPORTANT
    // If you add a real WebSocket server later (e.g., FastAPI / websockets), 
    // ensure errors do NOT call messagesSubject.complete()
    console.log("wsUrl", environment.wsUrl)
    // this.zone.runOutsideAngular(() => {
    //   this.wsSubject = webSocket<TelemetryPayload>(environment.wsUrl);
    //   this.wsSubject.pipe(
    //     catchError(err => {
    //       console.error('[WebSocket] Connection error:', err);
    //       return EMPTY;
    //     }),
    //     takeUntil(this.destroy$),
    //   ).subscribe({
    //     next: payload => this.zone.run(() => this.messagesSubject.next(payload)),
    //     complete: () => this.scheduleReconnect(),
    //   });
    // });
  }

  private scheduleReconnect(): void {
    this.reconnectAttempts++;
    const delay = Math.min(1000 * Math.pow(2, this.reconnectAttempts), this.MAX_BACKOFF_MS);
    console.warn(`[WebSocket] Reconnecting in ${delay}ms (attempt #${this.reconnectAttempts})`);
    timer(delay).pipe(takeUntil(this.destroy$)).subscribe(() => this.connectWebSocket());
  }

  disconnect(): void {
    this.destroy$.next();
    this.destroy$.complete();
    // this.wsSubject?.complete();
  }
}
