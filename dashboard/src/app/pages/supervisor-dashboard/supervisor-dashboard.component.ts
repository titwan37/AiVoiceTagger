import { Component, inject, signal } from '@angular/core';
import { CommonModule, DatePipe } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { TelemetryStore } from '../../services/telemetry-store.service';
import { GlobalBannerComponent } from '../../components/global-banner/global-banner.component';
import { NodeStatusCardComponent } from '../../components/node-status-card/node-status-card.component';
import { PipelineFunnelDagComponent } from '../../components/pipeline-funnel-dag/pipeline-funnel-dag.component';
import { WaveformDiarizationComponent } from '../../components/waveform-diarization/waveform-diarization.component';
import { TwoPhaseCommitModalComponent } from '../../components/two-phase-commit-modal/two-phase-commit-modal.component';
import { DeadLetterExplorerComponent } from '../../components/dead-letter-explorer/dead-letter-explorer.component';
import { InventoryOverviewComponent } from '../../components/inventory-overview/inventory-overview.component';
import { PipelineStage, QualityGrade } from '../../models/telemetry.models';
import { ForensicVisualizerComponent } from '../../visualizer/forensic-visualizer.component';

@Component({
  selector: 'app-supervisor-dashboard',
  standalone: true,
  imports: [
    CommonModule,
    DatePipe,
    FormsModule,
    GlobalBannerComponent,
    NodeStatusCardComponent,
    PipelineFunnelDagComponent,
    WaveformDiarizationComponent,
    TwoPhaseCommitModalComponent,
    DeadLetterExplorerComponent,
    InventoryOverviewComponent,
    ForensicVisualizerComponent,
  ],
  templateUrl: './supervisor-dashboard.component.html',
  styleUrl: './supervisor-dashboard.component.scss',
})
export class SupervisorDashboardComponent {
  store = inject(TelemetryStore);

  activeTab = signal<'nodes' | 'dead_letters' | 'transcripts' | 'inventory' | 'visualizer'>('nodes');

  readonly stages: (PipelineStage | 'ALL')[] = [
    'ALL', 'DISCOVERED', 'QUEUED', 'DECODED', 'TRANSCRIBED', 'NLP_DONE', 'EXPORTED', 'DONE', 'DEAD_LETTER', 'FAILED',
  ];

  readonly aqiOptions: (QualityGrade | 'ALL')[] = ['ALL', 'GOOD', 'DEGRADED', 'UNUSABLE'];

  setTab(tab: 'nodes' | 'dead_letters' | 'transcripts' | 'inventory' | 'visualizer'): void {
    this.activeTab.set(tab);
  }

  onSearchChange(event: Event): void {
    const value = (event.target as HTMLInputElement).value;
    this.store.setSearchFilter(value);
  }

  onStageChange(event: Event): void {
    const value = (event.target as HTMLSelectElement).value as PipelineStage | 'ALL';
    this.store.setStageFilter(value);
  }

  onAqiChange(event: Event): void {
    const value = (event.target as HTMLSelectElement).value as QualityGrade | 'ALL';
    this.store.setAqiFilter(value);
  }

  async onRetryDeadLetter(recordId: string): Promise<void> {
    const ok = await this.store.retryRecord(recordId);
    if (ok) {
      console.log(`[Dashboard] Record ${recordId} re-queued successfully.`);
    }
  }

  async onTogglePause(): Promise<void> {
    await this.store.togglePause();
  }
}
