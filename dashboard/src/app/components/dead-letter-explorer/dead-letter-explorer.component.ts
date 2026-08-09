import { Component, Input, Output, EventEmitter, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { DeadLetterEntry } from '../../models/telemetry.models';

@Component({
  selector: 'app-dead-letter-explorer',
  standalone: true,
  imports: [CommonModule],
  templateUrl: './dead-letter-explorer.component.html',
  styleUrls: ['./dead-letter-explorer.component.css']
})
export class DeadLetterExplorerComponent {
  @Input({ required: true }) records: DeadLetterEntry[] = [];
  @Output() retryRequested = new EventEmitter<string>();

  expandedId = signal<number | null>(null);

  toggleExpand(id: number): void {
    if (this.expandedId() === id) {
      this.expandedId.set(null);
    } else {
      this.expandedId.set(id);
    }
  }

  onRetry(recordId: string, event: Event): void {
    event.stopPropagation();
    this.retryRequested.emit(recordId);
  }
}
