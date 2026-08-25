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
    setInterval(() => {
      this.fetchInventory();
    }, 5000);
  }

  async fetchInventory(): Promise<void> {
    this.isLoading.set(true);
    this.error.set(null);
    if (environment.useMockData) {
      const mockData: InventoryPayload = {
        partition_balance: {
          master_count: 6539,
          pc1_count: 3270,
          pc2_count: 3269,
          overlap_count: 0,
          orphan_count: 0,
          pc1_percent: 50.01,
          pc2_percent: 49.99,
          total_size_gb: 348.6
        },
        partition_triage: {
          'PC1': {
            total: 3270,
            triaged_high: 2450,
            triaged_low: 580,
            done: 2890,
            in_progress: 120,
            remaining: 260,
            processed_total: 3010,
            processed_pct: 92.0,
            remaining_pct: 8.0
          },
          'PC2': {
            total: 3269,
            triaged_high: 2380,
            triaged_low: 640,
            done: 2640,
            in_progress: 180,
            remaining: 449,
            processed_total: 2820,
            processed_pct: 86.3,
            remaining_pct: 13.7
          }
        },
        codec_breakdown: [
          { codec: 'FLAC (24-bit 48kHz)', count: 2840, size_gb: 194.2 },
          { codec: 'MP3 (320kbps CBR)', count: 2120, size_gb: 84.8 },
          { codec: 'WAV (16-bit PCM)', count: 980, size_gb: 52.4 },
          { codec: 'Opus (Voice HD)', count: 599, size_gb: 17.2 }
        ],
        naming_patterns: {
          'REC_YYYY-MM-DD_HHhMM_*.wav': 3420,
          'INTERVIEW_*.flac': 1860,
          'MEETING_*.opus': 1259
        },
        top_folders: [
          { directory: 'nas://archive/industrial_triages_2024/', count: 2840, size_gb: 162.4 },
          { directory: 'nas://archive/multilingual_speech_corpus/', count: 2100, size_gb: 120.1 },
          { directory: 'nas://archive/dsp_filtered_sessions/', count: 1599, size_gb: 66.1 }
        ],
        records: [
          { record_id: 'rec-001', name: 'REC_2024-03-15_09h42_CH01.flac', directory: 'nas://archive/industrial_triages_2024/', codec: 'FLAC', length_bytes: 42800000, assigned_to: 'PC1' },
          { record_id: 'rec-002', name: 'REC_2024-03-15_10h15_CH02.mp3', directory: 'nas://archive/multilingual_speech_corpus/', codec: 'MP3', length_bytes: 18400000, assigned_to: 'PC2' },
          { record_id: 'rec-003', name: 'REC_2024-03-15_11h30_MASTER.wav', directory: 'nas://archive/dsp_filtered_sessions/', codec: 'WAV', length_bytes: 65200000, assigned_to: 'PC1' },
          { record_id: 'rec-004', name: 'REC_2024-03-16_08h00_INTERVIEW.opus', directory: 'nas://archive/industrial_triages_2024/', codec: 'Opus', length_bytes: 8900000, assigned_to: 'PC2' }
        ]
      };
      this.inventoryData.set(mockData);
      this.isLoading.set(false);
      return;
    }

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
