import { Component, inject } from '@angular/core';
import { CommonModule, DecimalPipe } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { InventoryStore } from '../../services/inventory-store.service';

@Component({
  selector: 'app-inventory-overview',
  standalone: true,
  imports: [CommonModule, DecimalPipe, FormsModule],
  templateUrl: './inventory-overview.component.html',
  styleUrls: ['./inventory-overview.component.css']
})
export class InventoryOverviewComponent {
  store = inject(InventoryStore);

  onSearch(event: Event): void {
    const val = (event.target as HTMLInputElement).value;
    this.store.setSearchQuery(val);
  }

  onCodecChange(event: Event): void {
    const val = (event.target as HTMLSelectElement).value;
    this.store.setCodecFilter(val);
  }

  onAssignmentChange(event: Event): void {
    const val = (event.target as HTMLSelectElement).value;
    this.store.setAssignmentFilter(val);
  }

  getAssignmentBadgeClass(assigned: string): string {
    switch (assigned) {
      case 'PC1': return 'badge-pc1';
      case 'PC2': return 'badge-pc2';
      case 'BOTH': return 'badge-both';
      case 'NONE': return 'badge-orphan';
      default: return 'badge-default';
    }
  }
}
