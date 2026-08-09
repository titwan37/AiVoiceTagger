import { Injectable, computed, signal } from '@angular/core';
import { environment } from '../../environments/environment';

export interface PartitionBalance {
  master_count: number;
  pc1_count: number;
  pc2_count: number;
  overlap_count: number;
  orphan_count: number;
  pc1_percent: number;
  pc2_percent: number;
  total_size_gb: number;
}

export interface CodecStat {
  codec: string;
  count: number;
  size_gb: number;
}

export interface FolderStat {
  directory: string;
  count: number;
  size_gb: number;
}

export interface InventoryRecord {
  record_id: string;
  name: string;
  directory: string;
  codec: string;
  length_bytes: number;
  assigned_to: 'PC1' | 'PC2' | 'BOTH' | 'NONE';
}

export interface PartitionTriageStat {
  total: number;
  triaged_high: number;
  triaged_low: number;
  done: number;
  in_progress: number;
  remaining: number;
  processed_total: number;
  processed_pct: number;
  remaining_pct: number;
}

export interface InventoryPayload {
  partition_balance: PartitionBalance;
  partition_triage?: Record<string, PartitionTriageStat>;
  codec_breakdown: CodecStat[];
  naming_patterns: Record<string, number>;
  top_folders: FolderStat[];
  records: InventoryRecord[];
}

const EMPTY_BALANCE: PartitionBalance = {
  master_count: 0,
  pc1_count: 0,
  pc2_count: 0,
  overlap_count: 0,
  orphan_count: 0,
  pc1_percent: 0,
  pc2_percent: 0,
  total_size_gb: 0
};

@Injectable({ providedIn: 'root' })
export class InventoryStore {
  readonly inventoryData = signal<InventoryPayload | null>(null);
  readonly isLoading = signal<boolean>(false);
  readonly error = signal<string | null>(null);

  // Filters
  readonly searchQuery = signal<string>('');
  readonly codecFilter = signal<string>('ALL');
  readonly assignmentFilter = signal<string>('ALL');

  // Computed Signals
  readonly balance = computed(() => this.inventoryData()?.partition_balance || EMPTY_BALANCE);
  readonly partitionTriage = computed(() => this.inventoryData()?.partition_triage || {});
  readonly codecStats = computed(() => this.inventoryData()?.codec_breakdown || []);
  readonly namingPatterns = computed(() => this.inventoryData()?.naming_patterns || {});
  readonly topFolders = computed(() => this.inventoryData()?.top_folders || []);
  readonly records = computed(() => this.inventoryData()?.records || []);

  readonly filteredRecords = computed(() => {
    let list = this.records();
    const query = this.searchQuery().toLowerCase().trim();
    const codec = this.codecFilter();
    const assign = this.assignmentFilter();

    if (query) {
      list = list.filter(r =>
        r.name.toLowerCase().includes(query) ||
        r.directory.toLowerCase().includes(query) ||
        r.record_id.toLowerCase().includes(query)
      );
    }

    if (codec !== 'ALL') {
      list = list.filter(r => r.codec.toLowerCase() === codec.toLowerCase());
    }

    if (assign !== 'ALL') {
      list = list.filter(r => r.assigned_to === assign);
    }

    return list;
  });

  constructor() {
    this.fetchInventory();
  }

  async fetchInventory(): Promise<void> {
    this.isLoading.set(true);
    this.error.set(null);
    try {
      const res = await fetch(`${environment.apiUrl}/api/inventory`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data: InventoryPayload = await res.json();
      this.inventoryData.set(data);
    } catch (err) {
      console.error('[InventoryStore] Error fetching inventory intelligence:', err);
      this.error.set(String(err));
    } finally {
      this.isLoading.set(false);
    }
  }

  setSearchQuery(q: string): void {
    this.searchQuery.set(q);
  }

  setCodecFilter(codec: string): void {
    this.codecFilter.set(codec);
  }

  setAssignmentFilter(assignment: string): void {
    this.assignmentFilter.set(assignment);
  }
}
