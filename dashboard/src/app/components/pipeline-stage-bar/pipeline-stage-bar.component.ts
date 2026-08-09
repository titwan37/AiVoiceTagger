import { Component, input } from '@angular/core';
import { PipelineStageCounts } from '../../models/telemetry.models';

interface StageSegment {
  label: string;
  count: number;
  percent: number;
  cssClass: string;
}

@Component({
  selector: 'app-pipeline-stage-bar',
  standalone: true,
  templateUrl: './pipeline-stage-bar.component.html',
  styleUrl: './pipeline-stage-bar.component.scss',
})
export class PipelineStageBarComponent {
  counts = input.required<PipelineStageCounts>();

  get segments(): StageSegment[] {
    const c = this.counts();
    const entries: [string, number, string][] = [
      ['Discovered', c.discovered || 0, 'stage-discovered'],
      ['Queued', c.queued || 0, 'stage-queued'],
      ['Decoded', c.decoded || 0, 'stage-decoded'],
      ['Triaged High', c.triaged_high || 0, 'stage-triaged-high'],
      ['Triaged Low', c.triaged_low || 0, 'stage-triaged-low'],
      ['Transcribed', c.transcribed || 0, 'stage-transcribed'],
      ['NLP Done', c.nlp_done || 0, 'stage-nlp'],
      ['Exported', c.exported || 0, 'stage-exported'],
      ['Done', c.done || 0, 'stage-done'],
      ['Retry', c.retry || 0, 'stage-retry'],
      ['Failed', c.failed || 0, 'stage-failed'],
      ['Dead Letter', c.dead_letter || 0, 'stage-dead'],
    ];
    const total = entries.reduce((sum, [, count]) => sum + count, 0);
    return entries
      .filter(([, count]) => count > 0)
      .map(([label, count, cssClass]) => ({
        label,
        count,
        percent: total > 0 ? (count / total) * 100 : 0,
        cssClass,
      }));
  }
}
