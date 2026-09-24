import { Component, input, signal, computed } from '@angular/core';
import { CommonModule } from '@angular/common';
import { PipelineStageCounts } from '../../models/telemetry.models';

export interface DagNodeInfo {
  id: string;
  title: string;
  subtitle: string;
  layer: string;
  count: number;
  status: 'ACTIVE' | 'PROCESSING' | 'IDLE' | 'ALERT';
  detail: string;
}

@Component({
  selector: 'app-pipeline-funnel-dag',
  standalone: true,
  imports: [CommonModule],
  templateUrl: './pipeline-funnel-dag.component.html',
  styleUrl: './pipeline-funnel-dag.component.scss',
})
export class PipelineFunnelDagComponent {
  counts = input.required<PipelineStageCounts>();
  isPaused = input<boolean>(false);
  isFailover = input<boolean>(false);

  selectedNodeId = signal<string>('cuda');

  readonly nodes = computed<DagNodeInfo[]>(() => {
    const c = this.counts();
    const paused = this.isPaused();
    const failover = this.isFailover();

    return [
      {
        id: 'nas',
        title: '\\\\SyNAS\\Records',
        subtitle: 'SMB Ingestion Pool',
        layer: 'Storage Mount',
        count: c.discovered || 0,
        status: paused ? 'IDLE' : 'ACTIVE',
        detail: 'Continuous lock-free directory crawler scanning network storage shares with CRC32 file manifest validation.'
      },
      {
        id: 'manifest',
        title: 'Manifest Partition',
        subtitle: 'Collision Layer 1',
        layer: 'Deterministic Shard',
        count: c.queued || 0,
        status: paused ? 'IDLE' : 'ACTIVE',
        detail: 'Zero-lock partition hash routing tasks across worker nodes to prevent concurrent chunk ingestion collisions.'
      },
      {
        id: 'symphonia',
        title: 'Symphonia DSP',
        subtitle: 'Collision Layer 2',
        layer: 'Lock-Free Ring Buffer',
        count: (c.decoded || 0) + (c.triaged_high || 0) + (c.triaged_low || 0),
        status: paused ? 'IDLE' : 'PROCESSING',
        detail: 'High-throughput Rust audio decoding into SIMD-accelerated PCM frames with Silero VAD silence-stripping.'
      },
      {
        id: 'cuda',
        title: 'CUDA Tensor Core Batching',
        subtitle: 'Collision Layer 3',
        layer: 'cuBLAS GEMM Pipeline',
        count: c.transcribed || 0,
        status: failover ? 'ALERT' : (paused ? 'IDLE' : 'ACTIVE'),
        detail: '32-layer pinned FP16 Whisper weights in VRAM running multi-stream asynchronous batch inference.'
      },
      {
        id: 'twopc',
        title: '2PC SQLite WAL Commit',
        subtitle: 'Acid Durability',
        layer: 'Atomic Ledger',
        count: c.done || 0,
        status: 'ACTIVE',
        detail: 'Two-Phase Commit state machine validating atomic SHA-256 block ledger before finalizing records.'
      },
      {
        id: 'dead_letter',
        title: 'Watchdog Quarantine (DLQ)',
        subtitle: 'Zero-Zombie Auto-Recycle',
        layer: 'Quarantine Layer',
        count: c.dead_letter || 0,
        status: failover ? 'ALERT' : 'ACTIVE',
        detail: 'Quarantine buffer isolating crashed audio chunks and VRAM spike events for zero-loss automatic watchdog recovery.'
      }
    ];
  });

  readonly selectedNode = computed(() => {
    return this.nodes().find(n => n.id === this.selectedNodeId()) || this.nodes()[3];
  });

  selectNode(id: string): void {
    this.selectedNodeId.set(id);
  }
}
