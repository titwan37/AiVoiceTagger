import { Component, input } from '@angular/core';
import { QualityGrade } from '../../models/telemetry.models';

@Component({
  selector: 'app-aqi-badge',
  standalone: true,
  templateUrl: './aqi-badge.component.html',
  styleUrl: './aqi-badge.component.scss',
})
export class AqiBadgeComponent {
  grade = input.required<QualityGrade>();
  count = input<number | null>(null);
  showLabel = input<boolean>(true);

  get cssClass(): string {
    return `aqi-badge aqi-${this.grade().toLowerCase()}`;
  }

  get icon(): string {
    switch (this.grade()) {
      case 'GOOD': return '✓';
      case 'DEGRADED': return '⚠';
      case 'UNUSABLE': return '✕';
    }
  }

  get label(): string {
    return this.grade().charAt(0) + this.grade().slice(1).toLowerCase();
  }
}
