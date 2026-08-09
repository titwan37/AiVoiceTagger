import { Component, inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { AqiBadgeComponent } from '../aqi-badge/aqi-badge.component';
import { TelemetryStore } from '../../services/telemetry-store.service';

@Component({
  selector: 'app-global-banner',
  standalone: true,
  imports: [
    CommonModule,
    AqiBadgeComponent
  ],
  templateUrl: './global-banner.component.html',
  styleUrls: ['./global-banner.component.scss']
})
export class GlobalBannerComponent {
  store = inject(TelemetryStore);

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
    md += `| **AQI Good / Degraded / Unusable** | ${winStat.good} / ${winStat.degraded} / ${winStat.unusable} |\n`;
    md += `| **Dead Letters / Failures** | ${metrics.dead_letter_count} / ${metrics.failure_count} |\n\n`;

    // 2. Worker Node Health
    md += `## 📡 Worker Node Health\n\n`;
    if (nodes.length === 0) {
      md += `*No worker nodes active.*\n\n`;
    } else {
      md += `| Worker ID | Health Status | Current Stage | CPU % | RSS Memory (MB) | Active File | Lease Expiration |\n`;
      md += `| :--- | :--- | :--- | :--- | :--- | :--- | :--- |\n`;
      for (const n of nodes) {
        md += `| \`${n.worker_id}\` | **${n.health}** | \`${n.current_stage}\` | ${n.resources.cpu_percent}% | ${n.resources.rss_memory_mb} MB | \`${n.active_file}\` | ${n.lease_expires_at ? new Date(n.lease_expires_at).toLocaleTimeString() : 'N/A'} |\n`;
      }
      md += `\n`;
    }

    // 3. Pipeline Funnel
    md += `## 🔀 Pipeline Funnel Stage Distribution\n\n`;
    const counts = metrics.pipeline_stage_counts;
    md += `- **DISCOVERED**: ${counts.discovered || 0}\n`;
    md += `- **QUEUED**: ${counts.queued || 0}\n`;
    md += `- **DECODED**: ${counts.decoded || 0}\n`;
    md += `- **TRIAGED_HIGH**: ${counts.triaged_high || 0}\n`;
    md += `- **TRIAGED_LOW**: ${counts.triaged_low || 0}\n`;
    md += `- **TRANSCRIBED**: ${counts.transcribed || 0}\n`;
    md += `- **NLP_DONE**: ${counts.nlp_done || 0}\n`;
    md += `- **EXPORTED**: ${counts.exported || 0}\n`;
    md += `- **DONE**: ${counts.done || 0}\n`;
    md += `- **DEAD_LETTER**: ${counts.dead_letter || 0}\n\n`;

    // 4. Recent Dead Letters
    md += `## 💀 Recent Dead Letters (Top 10)\n\n`;
    if (deadLetters.length === 0) {
      md += `*Zero dead letter failures recorded.*\n\n`;
    } else {
      md += `| Record ID | Stage Failed | Error Message | Timestamp |\n`;
      md += `| :--- | :--- | :--- | :--- |\n`;
      for (const d of deadLetters) {
        md += `| \`${d.record_id}\` | \`${d.stage}\` | ${d.error.replace(/\n/g, ' ')} | ${d.created_at} |\n`;
      }
      md += `\n`;
    }

    // 5. Live Transcript Preview
    md += `## 📝 Live Transcripts Sample (Last 5)\n\n`;
    if (transcripts.length === 0) {
      md += `*No completed transcripts available yet.*\n\n`;
    } else {
      for (const t of transcripts) {
        md += `> **\`${t.name}\`** (${t.speech_count} speeches, ${t.is_degraded ? 'DEGRADED' : 'GOOD'}):  \n`;
        md += `> "${t.story.replace(/\n/g, ' ')}"\n\n`;
      }
    }

    const timestamp = new Date().toISOString().replace(/[:.]/g, '').slice(0, 15);
    this.downloadFile(md, `AiVoiceTagger_Report_${timestamp}.md`);
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
