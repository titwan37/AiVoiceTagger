import { Component, inject } from '@angular/core';
import { CommonModule, DecimalPipe } from '@angular/common';
import { AqiBadgeComponent } from '../aqi-badge/aqi-badge.component';
import { TelemetryStore } from '../../services/telemetry-store.service';
import { WhisperModelVariant } from '../../models/telemetry.models';

@Component({
  selector: 'app-global-banner',
  standalone: true,
  imports: [
    CommonModule,
    DecimalPipe,
    AqiBadgeComponent
  ],
  templateUrl: './global-banner.component.html',
  styleUrls: ['./global-banner.component.scss']
})
export class GlobalBannerComponent {
  store = inject(TelemetryStore);

  readonly modelOptions: { id: WhisperModelVariant; label: string; desc: string }[] = [
    { id: 'whisper-large-v3', label: 'Whisper Large v3 (FP16)', desc: 'Enterprise Forensic Accuracy • 14.2 GB VRAM' },
    { id: 'whisper-medium-q8_0', label: 'Whisper Medium (Q8_0)', desc: 'High-Throughput Balanced • 7.8 GB VRAM' },
    { id: 'whisper-small-q5_0', label: 'Whisper Small (Q5_0)', desc: 'Ultra-Fast Low-Latency • 3.2 GB VRAM' },
  ];

  onModelChange(event: Event): void {
    const value = (event.target as HTMLSelectElement).value as WhisperModelVariant;
    this.store.hotSwapModel(value);
  }

  onTriggerFailover(): void {
    if (this.store.isFailoverActive()) {
      this.store.recoverFailover();
    } else {
      this.store.simulateFailover();
    }
  }

  onOpenTwoPhaseCommit(): void {
    this.store.openTwoPhaseCommitModal();
  }

  generateMarkdownReport(): void {
    const metrics = this.store.globalMetrics();
    const nodes = this.store.nodes();
    const deadLetters = this.store.deadLetters().slice(0, 10);
    const transcripts = this.store.transcripts().slice(0, 5);
    const nowStr = new Date().toLocaleString();

    let md = `# AiVoiceTagger System Status Report\n\n`;
    md += `**Generated on:** ${nowStr}\n`;
    md += `**Connection Status:** \`${this.store.connectionStatus()}\` | **Ingestion Status:** \`${this.store.isPaused() ? 'PAUSED' : 'RUNNING'}\`  \n\n`;
    md += `---\n\n`;

    // 1. Global Metrics Summary
    const activeWin = this.store.timeWindowFilter().toUpperCase();
    const winStat = this.store.activeWindowStat();
    md += `## 📊 Global Metrics Summary (${activeWin})\n\n`;
    md += `| Metric | Value |\n`;
    md += `| :--- | :--- |\n`;
    md += `| **Discovered Records** | ${metrics.total_discovered} |\n`;
    md += `| **Queued Records** | ${metrics.total_queued} |\n`;
    md += `| **Completed Records (${activeWin})** | ${winStat.completed} |\n`;
    md += `| **Audio Duration Processed** | ${this.store.audioDurationFormatted()} |\n`;
    md += `| **Real-Time Factor (RTF)** | ${this.store.realTimeFactor().toFixed(1)}x |\n`;
    md += `| **Cluster Total VRAM Allocated** | ${(this.store.clusterTotalVramAllocatedMb() / 1024).toFixed(1)} GB |\n`;
    md += `| **Total Active CUDA Streams** | ${this.store.clusterTotalCudaStreams()} |\n`;
    md += `| **cuBLAS GEMM Throughput** | ${this.store.clusterGemmThroughputAudioSec()} audio/sec |\n`;
    md += `| **AQI Good / Degraded / Unusable** | ${winStat.good} / ${winStat.degraded} / ${winStat.unusable} |\n`;
    md += `| **Dead Letters / Failures** | ${metrics.dead_letter_count} / ${metrics.failure_count} |\n\n`;

    // 2. Worker Node Health
    md += `## 📡 Worker Node Health & GPU Accelerators\n\n`;
    if (nodes.length === 0) {
      md += `*No worker nodes active.*\n\n`;
    } else {
      md += `| Worker ID | Health | VRAM (GB) | CUDA Streams | Temp | Current Stage |\n`;
      md += `| :--- | :--- | :--- | :--- | :--- | :--- |\n`;
      for (const n of nodes) {
        const vramGb = n.gpu ? (n.gpu.vram_allocated_mb / 1024).toFixed(1) : 'N/A';
        const streams = n.gpu ? n.gpu.cuda_streams_active : 'N/A';
        const temp = n.gpu ? `${n.gpu.gpu_temp_celsius}°C` : 'N/A';
        md += `| \`${n.worker_id}\` | **${n.health}** | ${vramGb} GB | ${streams} | ${temp} | \`${n.current_stage}\` |\n`;
      }
      md += `\n`;
    }

    const timestamp = new Date().toISOString().replace(/[:.]/g, '').slice(0, 15);
    this.downloadFile(md, `AiVoiceTagger_Forensic_Report_${timestamp}.md`);
  }

  private downloadFile(content: string, filename: string): void {
    const blob = new Blob([content], { type: 'text/markdown;charset=utf-8;' });
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    a.click();
    window.URL.revokeObjectURL(url);
  }
}
