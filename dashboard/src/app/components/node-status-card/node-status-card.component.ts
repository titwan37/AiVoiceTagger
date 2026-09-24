import { Component, input, OnInit, OnDestroy, computed, signal } from '@angular/core';
import { CommonModule, DecimalPipe } from '@angular/common';
import { NodeTelemetry, GpuTelemetry } from '../../models/telemetry.models';
import { AqiBadgeComponent } from '../aqi-badge/aqi-badge.component';

export interface VuLedSegment {
  active: boolean;
  type: 'green' | 'yellow' | 'red';
  isPeakHold?: boolean;
}

@Component({
  selector: 'app-node-status-card',
  standalone: true,
  imports: [CommonModule, AqiBadgeComponent],
  templateUrl: './node-status-card.component.html',
  styleUrl: './node-status-card.component.scss',
})
export class NodeStatusCardComponent implements OnInit, OnDestroy {
  node = input.required<NodeTelemetry>();
  readonly Math = Math;

  heartbeatAge = signal<string>('');
  leaseRemaining = signal<string>('');

  // ─── Real-Time DSP Audio VU Meter & FFT Spectrum Signals ───
  leftPercent = signal<number>(0);
  rightPercent = signal<number>(0);
  leftDb = signal<string>('-60.0');
  rightDb = signal<string>('-60.0');
  leftClip = signal<boolean>(false);
  rightClip = signal<boolean>(false);
  fftBands = signal<number[]>([15, 10, 25, 40, 30, 20, 12, 8]);

  readonly fftFrequencies = ['60Hz', '150Hz', '400Hz', '1kHz', '2.5kHz', '6kHz', '12kHz', '16kHz'];

  private intervalId: any;
  private animFrameId: any;
  private lastAnimTime = 0;

  // Ballistic decay state variables
  private curL = 0;
  private curR = 0;
  private peakL = 0;
  private peakR = 0;
  private peakHoldTimerL = 0;
  private peakHoldTimerR = 0;
  private curFft = [10, 15, 25, 35, 20, 15, 10, 5];

  readonly healthClass = computed<string>(() => {
    switch (this.node().health) {
      case 'HEALTHY': return 'health-healthy';
      case 'STALLED': return 'health-stalled';
      case 'OFFLINE': return 'health-offline';
    }
  });

  readonly stageLabel = computed<string>(() => {
    return this.node().current_stage.replace(/_/g, ' ');
  });

  readonly modelShort = computed<string>(() => {
    const m = this.node().loaded_model;
    return m.replace('ggml-', '').replace('.bin', '');
  });

  readonly sidecarClass = computed<string>(() => {
    switch (this.node().sidecar_status) {
      case 'ACTIVE': return 'sidecar-active';
      case 'RESTARTING': return 'sidecar-restarting';
      case 'BACKPRESSURE_PAUSED': return 'sidecar-paused';
      case 'OFFLINE': return 'sidecar-offline';
    }
  });

  readonly gpu = computed<GpuTelemetry | undefined>(() => {
    return this.node().gpu;
  });

  readonly pinnedLayers = computed<boolean[]>(() => {
    return this.node().gpu?.pinned_model_layers || Array.from({ length: 32 }, () => true);
  });

  // Computed 20 LED segment arrays for Left and Right Stereo VU bars
  readonly ledsLeft = computed<VuLedSegment[]>(() => {
    const pct = this.leftPercent();
    const pkPct = (this.peakL / 100) * 20;
    return Array.from({ length: 20 }, (_, i) => {
      const segIndex = i + 1;
      const thresholdPct = (segIndex / 20) * 100;
      const active = pct >= thresholdPct - 2;
      const isPeakHold = Math.floor(pkPct) === i && this.peakL > 5;
      let type: 'green' | 'yellow' | 'red' = 'green';
      if (segIndex > 16) type = 'red';
      else if (segIndex > 12) type = 'yellow';
      return { active, type, isPeakHold };
    });
  });

  readonly ledsRight = computed<VuLedSegment[]>(() => {
    const pct = this.rightPercent();
    const pkPct = (this.peakR / 100) * 20;
    return Array.from({ length: 20 }, (_, i) => {
      const segIndex = i + 1;
      const thresholdPct = (segIndex / 20) * 100;
      const active = pct >= thresholdPct - 2;
      const isPeakHold = Math.floor(pkPct) === i && this.peakR > 5;
      let type: 'green' | 'yellow' | 'red' = 'green';
      if (segIndex > 16) type = 'red';
      else if (segIndex > 12) type = 'yellow';
      return { active, type, isPeakHold };
    });
  });

  ngOnInit(): void {
    this.updateTimers();
    this.intervalId = setInterval(() => this.updateTimers(), 1000);
    this.startVuAnimation();
  }

  ngOnDestroy(): void {
    if (this.intervalId) {
      clearInterval(this.intervalId);
    }
    if (this.animFrameId) {
      cancelAnimationFrame(this.animFrameId);
    }
  }

  private startVuAnimation(): void {
    const loop = (timestamp: number) => {
      if (!this.lastAnimTime) this.lastAnimTime = timestamp;
      const delta = Math.min((timestamp - this.lastAnimTime) / 1000, 0.1);
      this.lastAnimTime = timestamp;

      this.updateVuPhysics(timestamp, delta);
      this.animFrameId = requestAnimationFrame(loop);
    };
    this.animFrameId = requestAnimationFrame(loop);
  }

  private updateVuPhysics(t: number, dt: number): void {
    const n = this.node();
    const isProcessing = n.health === 'HEALTHY' && n.current_stage !== 'QUEUED' && n.current_stage !== 'DONE';

    let targetL = 0;
    let targetR = 0;
    const targetFft = [0, 0, 0, 0, 0, 0, 0, 0];

    if (isProcessing) {
      // Dynamic realistic acoustic signal simulation based on time & speech cadence
      const timeSec = t / 1000;
      const beatPulse = Math.sin(timeSec * 4.2) * Math.cos(timeSec * 2.1);
      const voiceCadence = Math.max(0, Math.sin(timeSec * 7.5) + Math.cos(timeSec * 13.1) * 0.5);

      // Add worker_id hash seed offset so different workers have distinct audio signatures
      const workerSeed = n.worker_id.charCodeAt(n.worker_id.length - 1) * 0.3;
      const noiseL = Math.random() * 15;
      const noiseR = Math.random() * 15;

      targetL = Math.min(96, Math.max(15, (voiceCadence * 55 + beatPulse * 20 + noiseL + workerSeed % 20)));
      targetR = Math.min(94, Math.max(12, (voiceCadence * 52 + beatPulse * 22 + noiseR + (workerSeed + 5) % 18)));

      // Occasional audio transient peak spikes
      if (Math.random() < 0.05) {
        targetL = Math.min(100, targetL + 25);
        targetR = Math.min(100, targetR + 22);
      }

      // FFT 8-Band spectral distribution (Sub, Bass, Low-Mid, Mid, High-Mid, Presence, Brilliance, Air)
      targetFft[0] = Math.min(100, targetL * 0.7 + Math.sin(timeSec * 3) * 20); // 60Hz
      targetFft[1] = Math.min(100, targetL * 0.85 + Math.cos(timeSec * 5) * 15); // 150Hz
      targetFft[2] = Math.min(100, targetL * 0.95 + Math.sin(timeSec * 9) * 20); // 400Hz (Vocal pitch)
      targetFft[3] = Math.min(100, targetL * 0.9 + Math.cos(timeSec * 11) * 15); // 1kHz (Formants)
      targetFft[4] = Math.min(100, targetL * 0.75 + Math.sin(timeSec * 14) * 18); // 2.5kHz
      targetFft[5] = Math.min(100, targetL * 0.55 + Math.cos(timeSec * 17) * 12); // 6kHz
      targetFft[6] = Math.min(100, targetL * 0.35 + Math.sin(timeSec * 21) * 10); // 12kHz
      targetFft[7] = Math.min(100, targetL * 0.2 + Math.random() * 10);          // 16kHz
    } else {
      // Idle noise floor
      targetL = 4;
      targetR = 3;
      targetFft.fill(2);
    }

    // Ballistic smoothing (Instant attack, smooth exponential decay)
    if (targetL > this.curL) {
      this.curL = this.curL * 0.3 + targetL * 0.7; // Fast attack
    } else {
      this.curL = Math.max(0, this.curL - dt * 110); // Smooth decay
    }

    if (targetR > this.curR) {
      this.curR = this.curR * 0.3 + targetR * 0.7;
    } else {
      this.curR = Math.max(0, this.curR - dt * 110);
    }

    // Peak Hold Physics
    if (this.curL > this.peakL) {
      this.peakL = this.curL;
      this.peakHoldTimerL = 0.6; // Hold peak for 600ms
    } else {
      this.peakHoldTimerL -= dt;
      if (this.peakHoldTimerL <= 0) {
        this.peakL = Math.max(0, this.peakL - dt * 90);
      }
    }

    if (this.curR > this.peakR) {
      this.peakR = this.curR;
      this.peakHoldTimerR = 0.6;
    } else {
      this.peakHoldTimerR -= dt;
      if (this.peakHoldTimerR <= 0) {
        this.peakR = Math.max(0, this.peakR - dt * 90);
      }
    }

    // Smooth FFT spectrum decay
    for (let i = 0; i < 8; i++) {
      if (targetFft[i] > this.curFft[i]) {
        this.curFft[i] = this.curFft[i] * 0.35 + targetFft[i] * 0.65;
      } else {
        this.curFft[i] = Math.max(0, this.curFft[i] - dt * 120);
      }
    }

    // Convert % to dB readouts (-60dB to 0dB scale)
    const dbL_val = this.curL > 1 ? -60 + (this.curL / 100) * 60 : -60.0;
    const dbR_val = this.curR > 1 ? -60 + (this.curR / 100) * 60 : -60.0;

    this.leftPercent.set(Math.round(this.curL));
    this.rightPercent.set(Math.round(this.curR));
    this.leftDb.set(dbL_val.toFixed(1));
    this.rightDb.set(dbR_val.toFixed(1));
    this.leftClip.set(this.curL >= 96);
    this.rightClip.set(this.curR >= 96);
    this.fftBands.set([...this.curFft]);
  }

  private updateTimers(): void {
    const now = Date.now();
    const n = this.node();

    const beatAge = Math.floor((now - new Date(n.last_heartbeat).getTime()) / 1000);
    this.heartbeatAge.set(beatAge < 60 ? `${beatAge}s ago` : `${Math.floor(beatAge / 60)}m ${beatAge % 60}s ago`);

    const leaseLeft = Math.max(0, Math.floor((new Date(n.lease_expires_at).getTime() - now) / 1000));
    const lm = Math.floor(leaseLeft / 60);
    const ls = leaseLeft % 60;
    this.leaseRemaining.set(`${lm}:${ls.toString().padStart(2, '0')}`);
  }
}
