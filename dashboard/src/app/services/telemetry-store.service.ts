import { Injectable, computed, effect, inject, signal } from '@angular/core';
import { MonitoringWebSocketService } from './monitoring-websocket.service';
import {
  GlobalMetrics, NodeTelemetry, TelemetryPayload, TelemetryDelta, TranscriptEntry, DeadLetterEntry,
  ConnectionStatus, PipelineStage, QualityGrade, AqiBreakdown, PipelineStageCounts
} from '../models/telemetry.models';

const EMPTY_AQI: AqiBreakdown = { good: 0, degraded: 0, unusable: 0 };
const EMPTY_STAGE_COUNTS: PipelineStageCounts = {
  discovered: 0, queued: 0, decoded: 0, transcribed: 0,
  nlp_done: 0, exported: 0, done: 0, dead_letter: 0, failed: 0, retry: 0,
};
const EMPTY_GLOBAL: GlobalMetrics = {
  total_discovered: 0, total_queued: 0, total_done: 0,
  audio_duration_processed_sec: 0, wall_clock_elapsed_sec: 0,
  real_time_factor: 0, aqi_breakdown: EMPTY_AQI,
  dead_letter_count: 0, failure_count: 0,
  pipeline_stage_counts: EMPTY_STAGE_COUNTS,
};

const MAX_TRANSCRIPTS_MEMORY = 100;
const MAX_DEAD_LETTERS_MEMORY = 50;

@Injectable({ providedIn: 'root' })
export class TelemetryStore {
  private ws = inject(MonitoringWebSocketService);

  // ─── Writable Signals ───────────────────────────────────────────────────────
  readonly globalMetrics = signal<GlobalMetrics>(EMPTY_GLOBAL);
  readonly nodes = signal<NodeTelemetry[]>([]);
  readonly transcripts = signal<TranscriptEntry[]>([]);
  readonly deadLetters = signal<DeadLetterEntry[]>([]);
  readonly isPaused = signal<boolean>(false);
  readonly isPausing = signal<boolean>(false);
  readonly lastCommandStatus = signal<string>('');
  readonly connectionStatus = signal<ConnectionStatus>('DISCONNECTED');
  readonly lastUpdateTimestamp = signal<string>('');

  // Filter state
  readonly searchFilter = signal<string>('');
  readonly stageFilter = signal<PipelineStage | 'ALL'>('ALL');
  readonly aqiFilter = signal<QualityGrade | 'ALL'>('ALL');
  readonly transcriptSearch = signal<string>('');
  readonly timeWindowFilter = signal<'1h' | '4h' | '12h' | 'all'>('all');

  // ─── Computed Signals (zero-cost derived) ───────────────────────────────────
  readonly activeNodeCount = computed(() =>
    this.nodes().filter(n => n.health === 'HEALTHY').length
  );

  readonly stalledNodeCount = computed(() =>
    this.nodes().filter(n => n.health === 'STALLED').length
  );

  readonly offlineNodeCount = computed(() =>
    this.nodes().filter(n => n.health === 'OFFLINE').length
  );

  readonly activeWindowStat = computed(() => {
    const tw = this.globalMetrics().time_windows;
    const key = this.timeWindowFilter();
    if (tw && tw[key]) {
      return tw[key];
    }
    const g = this.globalMetrics();
    return {
      completed: g.total_done,
      audio_sec: g.audio_duration_processed_sec,
      good: g.aqi_breakdown.good,
      degraded: g.aqi_breakdown.degraded,
      unusable: g.aqi_breakdown.unusable,
      real_time_factor: g.wall_clock_elapsed_sec > 0 ? g.audio_duration_processed_sec / g.wall_clock_elapsed_sec : 0
    };
  });

  readonly realTimeFactor = computed(() => {
    return this.activeWindowStat().real_time_factor;
  });

  readonly degradedRatio = computed(() => {
    const stat = this.activeWindowStat();
    const total = stat.good + stat.degraded + stat.unusable;
    return total > 0 ? stat.degraded / total : 0;
  });

  readonly filteredNodes = computed(() => {
    let result = this.nodes();

    const search = this.searchFilter().toLowerCase().trim();
    if (search) {
      result = result.filter(n =>
        n.worker_id.toLowerCase().includes(search) ||
        n.active_file.toLowerCase().includes(search) ||
        n.loaded_model.toLowerCase().includes(search)
      );
    }

    const stage = this.stageFilter();
    if (stage !== 'ALL') {
      result = result.filter(n => n.current_stage === stage);
    }

    const aqi = this.aqiFilter();
    if (aqi !== 'ALL') {
      result = result.filter(n => n.current_aqi === aqi);
    }

    return result;
  });

  readonly filteredTranscripts = computed(() => {
    const q = this.transcriptSearch().toLowerCase().trim();
    if (!q) return this.transcripts();
    return this.transcripts().filter(t =>
      t.name.toLowerCase().includes(q) ||
      t.story.toLowerCase().includes(q) ||
      t.record_id.toLowerCase().includes(q)
    );
  });

  readonly audioDurationFormatted = computed(() => {
    const sec = this.activeWindowStat().audio_sec;
    const h = Math.floor(sec / 3600);
    const m = Math.floor((sec % 3600) / 60);
    const s = Math.floor(sec % 60);
    return `${h.toString().padStart(2, '0')}:${m.toString().padStart(2, '0')}:${s.toString().padStart(2, '0')}`;
  });

  constructor() {
    // Subscribe to WebSocket / REST messages with stream exception shielding
    this.ws.messages$.subscribe(payload => {
      try {
        if (!payload) return;
        
        // Handle Delta vs Full Snapshot
        if ('type' in payload && 'payload' in payload) {
          this.applyDelta(payload as unknown as TelemetryDelta);
        } else {
          this.hydrateFullSnapshot(payload);
        }
        
        this.connectionStatus.set('CONNECTED');
      } catch (err) {
        console.error('[TelemetryStore] Error processing incoming telemetry payload:', err);
      }
    });

    // Effect: warn on stale heartbeats
    effect(() => {
      const now = Date.now();
      for (const node of this.nodes()) {
        const lastBeat = new Date(node.last_heartbeat).getTime();
        const ageMs = now - lastBeat;
        if (ageMs > 60_000 && node.health !== 'OFFLINE') {
          console.warn(`[TelemetryStore] Node "${node.worker_id}" heartbeat stale: ${Math.floor(ageMs / 1000)}s ago`);
        }
      }
    });
  }

  // ─── Full Snapshot & Delta Engine ──────────────────────────────────────────
  private hydrateFullSnapshot(payload: TelemetryPayload): void {
    if (payload.global) this.globalMetrics.set(payload.global);
    if (payload.nodes) this.nodes.set(payload.nodes);
    
    if (payload.transcripts) {
      this.transcripts.set(payload.transcripts.slice(0, MAX_TRANSCRIPTS_MEMORY));
    }
    
    if (payload.dead_letters) {
      this.deadLetters.set(payload.dead_letters.slice(0, MAX_DEAD_LETTERS_MEMORY));
    }
    
    if (payload.is_paused !== undefined) {
      this.isPaused.set(payload.is_paused);
    }
    
    if (payload.timestamp) {
      this.lastUpdateTimestamp.set(payload.timestamp);
    }
  }

  applyDelta(delta: TelemetryDelta): void {
    switch (delta.type) {
      case 'NODE_UPDATE':
        this.nodes.update(nodes => {
          const idx = nodes.findIndex(n => n.worker_id === delta.payload.worker_id);
          if (idx !== -1) {
            const updated = [...nodes];
            updated[idx] = { ...updated[idx], ...delta.payload };
            return updated;
          }
          return [...nodes, delta.payload];
        });
        break;

      case 'TRANSCRIPT_NEW':
        this.transcripts.update(list => [delta.payload, ...list].slice(0, MAX_TRANSCRIPTS_MEMORY));
        break;

      case 'DEAD_LETTER_NEW':
        this.deadLetters.update(list => [delta.payload, ...list].slice(0, MAX_DEAD_LETTERS_MEMORY));
        break;

      case 'GLOBAL_METRIC':
        this.globalMetrics.set(delta.payload);
        break;
    }
  }

  // ─── Filter & Control Actions ───────────────────────────────────────────────
  setSearchFilter(value: string): void {
    this.searchFilter.set(value);
  }

  setStageFilter(value: PipelineStage | 'ALL'): void {
    this.stageFilter.set(value);
  }

  setAqiFilter(value: QualityGrade | 'ALL'): void {
    this.aqiFilter.set(value);
  }

  setTranscriptSearch(query: string): void {
    this.transcriptSearch.set(query);
  }

  setTimeWindowFilter(windowKey: '1h' | '4h' | '12h' | 'all'): void {
    this.timeWindowFilter.set(windowKey);
  }

  async retryRecord(recordId: string): Promise<boolean> {
    this.lastCommandStatus.set(`⏳ Sending retry command for record ${recordId}...`);
    const res = await this.ws.sendCommand('retry', { record_id: recordId });
    if (res.status === 'ok') {
      this.deadLetters.update(list => list.filter(item => item.record_id !== recordId));
      this.lastCommandStatus.set(`✅ Record ${recordId} re-queued successfully!`);
      setTimeout(() => this.lastCommandStatus.set(''), 5000);
      return true;
    } else {
      this.lastCommandStatus.set(`❌ Failed to retry record ${recordId}: ${res.message || 'Server Error'}`);
      return false;
    }
  }

  async togglePause(): Promise<void> {
    this.isPausing.set(true);
    const targetState = !this.isPaused() ? 'pause' : 'resume';
    this.lastCommandStatus.set(`⏳ Sending ${targetState} command to pipeline...`);

    const res = await this.ws.sendCommand('pause', {});
    this.isPausing.set(false);

    if (res.status === 'ok' && res.is_paused !== undefined) {
      this.isPaused.set(res.is_paused);
      const actionText = res.is_paused ? 'PAUSED' : 'RESUMED';
      this.lastCommandStatus.set(`✅ Ingestion successfully ${actionText}`);
      setTimeout(() => this.lastCommandStatus.set(''), 5000);
    } else {
      this.lastCommandStatus.set(`❌ Failed to toggle ingestion state: ${res.message || 'Server Error'}`);
    }
  }
}
