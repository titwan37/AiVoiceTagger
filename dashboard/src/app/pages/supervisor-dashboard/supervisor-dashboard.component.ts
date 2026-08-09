import { Component, inject, signal } from '@angular/core';
import { CommonModule, DatePipe } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { TelemetryStore } from '../../services/telemetry-store.service';
import { GlobalBannerComponent } from '../../components/global-banner/global-banner.component';
import { NodeStatusCardComponent } from '../../components/node-status-card/node-status-card.component';
import { PipelineStageBarComponent } from '../../components/pipeline-stage-bar/pipeline-stage-bar.component';
import { DeadLetterExplorerComponent } from '../../components/dead-letter-explorer/dead-letter-explorer.component';
import { InventoryOverviewComponent } from '../../components/inventory-overview/inventory-overview.component';
import { PipelineStage, QualityGrade } from '../../models/telemetry.models';

@Component({
  selector: 'app-supervisor-dashboard',
  standalone: true,
  imports: [
    CommonModule,
    DatePipe,
    FormsModule,
    GlobalBannerComponent,
    NodeStatusCardComponent,
    PipelineStageBarComponent,
    DeadLetterExplorerComponent,
    InventoryOverviewComponent,
  ],
  templateUrl: './supervisor-dashboard.component.html',
  styleUrl: './supervisor-dashboard.component.scss',
})
export class SupervisorDashboardComponent {
  store = inject(TelemetryStore);

  activeTab = signal<'nodes' | 'dead_letters' | 'transcripts' | 'inventory'>('nodes');

  readonly stages: (PipelineStage | 'ALL')[] = [
    'ALL', 'DISCOVERED', 'QUEUED', 'DECODED', 'TRANSCRIBED', 'NLP_DONE', 'EXPORTED', 'DONE', 'DEAD_LETTER', 'FAILED',
  ];

  readonly aqiOptions: (QualityGrade | 'ALL')[] = ['ALL', 'GOOD', 'DEGRADED', 'UNUSABLE'];

  setTab(tab: 'nodes' | 'dead_letters' | 'transcripts' | 'inventory'): void {
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

  onTranscriptSearch(event: Event): void {
    const value = (event.target as HTMLInputElement).value;
    this.store.setTranscriptSearch(value);
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
