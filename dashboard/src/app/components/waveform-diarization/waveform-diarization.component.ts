import {
  Component, input, ElementRef, viewChild, AfterViewInit, OnDestroy, signal, computed
} from '@angular/core';
import { CommonModule, DatePipe } from '@angular/common';
import { TranscriptEntry, DiarizationCluster, AcousticBiomarkers, VadWindow } from '../../models/telemetry.models';

@Component({
  selector: 'app-waveform-diarization',
  standalone: true,
  imports: [CommonModule, DatePipe],
  templateUrl: './waveform-diarization.component.html',
  styleUrl: './waveform-diarization.component.scss',
})
export class WaveformDiarizationComponent implements AfterViewInit, OnDestroy {
  transcripts = input.required<TranscriptEntry[]>();
  selectedRecordId = signal<string>('');

  canvasRef = viewChild<ElementRef<HTMLCanvasElement>>('waveformCanvas');

  private animationFrameId: number | null = null;
  private phase = 0;

  readonly activeEntry = computed<TranscriptEntry | null>(() => {
    const list = this.transcripts();
    if (list.length === 0) return null;
    const selected = this.selectedRecordId();
    if (selected) {
      const found = list.find(t => t.record_id === selected);
      if (found) return found;
    }
    return list[0];
  });

  readonly biomarkers = computed<AcousticBiomarkers>(() => {
    const entry = this.activeEntry();
    return entry?.biomarkers || {
      fundamental_pitch_f0: 142.4,
      vocal_strain_index: 0.28,
      speech_tempo_wpm: 156,
      snr_db: 24.8,
      vad_confidence: 0.96
    };
  });

  readonly diarizationClusters = computed<DiarizationCluster[]>(() => {
    const entry = this.activeEntry();
    return entry?.diarization_clusters || [
      { speaker_id: 'SPK_01', speaker_label: 'Speaker 1', color: '#00f2fe', centroid_norm: 0.88, confidence: 0.96, turn_count: 8 },
      { speaker_id: 'SPK_02', speaker_label: 'Speaker 2', color: '#f43f5e', centroid_norm: 0.79, confidence: 0.94, turn_count: 6 }
    ];
  });

  readonly vadWindows = computed<VadWindow[]>(() => {
    const entry = this.activeEntry();
    return entry?.vad_windows || [
      { start_sec: 0, end_sec: 28, is_speech: true, speaker: 'SPK_01' },
      { start_sec: 28, end_sec: 32, is_speech: false, speaker: 'SILENCE' },
      { start_sec: 32, end_sec: 64, is_speech: true, speaker: 'SPK_02' },
      { start_sec: 64, end_sec: 98, is_speech: true, speaker: 'SPK_01' }
    ];
  });

  selectRecord(id: string): void {
    this.selectedRecordId.set(id);
  }

  ngAfterViewInit(): void {
    this.startCanvasRenderLoop();
  }

  ngOnDestroy(): void {
    if (this.animationFrameId !== null) {
      cancelAnimationFrame(this.animationFrameId);
    }
  }

  private startCanvasRenderLoop(): void {
    const canvas = this.canvasRef()?.nativeElement;
    if (!canvas) return;

    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    const render = () => {
      this.phase += 0.04;
      const width = canvas.width = canvas.parentElement?.clientWidth || 700;
      const height = canvas.height = 160;

      // 1. Background Grid & Deep Space base
      ctx.fillStyle = '#070a13';
      ctx.fillRect(0, 0, width, height);

      // Grid lines
      ctx.strokeStyle = 'rgba(56, 189, 248, 0.08)';
      ctx.lineWidth = 1;
      const step = 24;
      for (let x = 0; x < width; x += step) {
        ctx.beginPath();
        ctx.moveTo(x, 0);
        ctx.lineTo(x, height);
        ctx.stroke();
      }
      for (let y = 0; y < height; y += step) {
        ctx.beginPath();
        ctx.moveTo(0, y);
        ctx.lineTo(width, y);
        ctx.stroke();
      }

      // 2. Silero VAD frame zones (20-30s frames)
      const vadTotalSec = 120;
      const windows = this.vadWindows();
      for (const w of windows) {
        const x1 = (w.start_sec / vadTotalSec) * width;
        const x2 = (w.end_sec / vadTotalSec) * width;
        const wWidth = x2 - x1;

        if (w.is_speech) {
          ctx.fillStyle = w.speaker === 'SPK_01' ? 'rgba(0, 242, 254, 0.08)' : 'rgba(244, 63, 94, 0.08)';
          ctx.fillRect(x1, 0, wWidth, height);
          ctx.strokeStyle = w.speaker === 'SPK_01' ? 'rgba(0, 242, 254, 0.3)' : 'rgba(244, 63, 94, 0.3)';
          ctx.strokeRect(x1, 2, wWidth, height - 4);
        } else {
          // Silence stripped zone
          ctx.fillStyle = 'rgba(100, 116, 139, 0.06)';
          ctx.fillRect(x1, 0, wWidth, height);
        }
      }

      // 3. Audio Waveform Envelope (Cyan & Neon Blue gradient)
      const midY = height / 2;
      const grad = ctx.createLinearGradient(0, 0, width, 0);
      grad.addColorStop(0, '#00f2fe');
      grad.addColorStop(0.5, '#38bdf8');
      grad.addColorStop(1, '#a855f7');

      ctx.beginPath();
      ctx.strokeStyle = grad;
      ctx.lineWidth = 2.2;
      ctx.shadowColor = 'rgba(0, 242, 254, 0.6)';
      ctx.shadowBlur = 10;

      const bars = Math.floor(width / 4);
      for (let i = 0; i < bars; i++) {
        const x = i * 4;
        const normX = i / bars;
        
        // Multi-frequency harmonic envelope simulation
        const wave1 = Math.sin(normX * 18 + this.phase) * 0.45;
        const wave2 = Math.cos(normX * 36 - this.phase * 1.5) * 0.3;
        const wave3 = Math.sin(normX * 6 + this.phase * 0.7) * 0.25;
        const envelope = Math.abs(wave1 + wave2 + wave3);
        const amp = envelope * (height * 0.42);

        ctx.moveTo(x, midY - amp);
        ctx.lineTo(x, midY + amp);
      }
      ctx.stroke();
      ctx.shadowBlur = 0; // reset shadow

      // Center timeline cursor
      const playheadX = ((this.phase * 20) % width);
      ctx.strokeStyle = '#f59e0b';
      ctx.lineWidth = 2;
      ctx.beginPath();
      ctx.moveTo(playheadX, 0);
      ctx.lineTo(playheadX, height);
      ctx.stroke();

      this.animationFrameId = requestAnimationFrame(render);
    };

    render();
  }
}
