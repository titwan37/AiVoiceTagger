import { Component, input, output, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { TwoPhaseCommitVerification } from '../../models/telemetry.models';

@Component({
  selector: 'app-two-phase-commit-modal',
  standalone: true,
  imports: [CommonModule],
  templateUrl: './two-phase-commit-modal.component.html',
  styleUrl: './two-phase-commit-modal.component.scss',
})
export class TwoPhaseCommitModalComponent {
  verification = input<TwoPhaseCommitVerification | undefined>();
  closed = output<void>();

  isRecalculating = signal<boolean>(false);
  verificationHash = signal<string>('a872bf901ca9f872b849e7a82910d54c87123bf0182479e018a7c645e81249b2');
  pageCount = signal<number>(1420);

  close(): void {
    this.closed.emit();
  }

  recalculateLedger(): void {
    this.isRecalculating.set(true);
    setTimeout(() => {
      // Generate refreshed random hex SHA-256 hash
      const randomHex = Array.from({ length: 64 }, () =>
        Math.floor(Math.random() * 16).toString(16)
      ).join('');
      this.verificationHash.set(randomHex);
      this.pageCount.update(c => c + 8);
      this.isRecalculating.set(false);
    }, 1200);
  }
}
