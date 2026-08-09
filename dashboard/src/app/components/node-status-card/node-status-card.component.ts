import { Component, input, OnInit, OnDestroy } from '@angular/core';
import { DecimalPipe } from '@angular/common';
import { NodeTelemetry } from '../../models/telemetry.models';
import { AqiBadgeComponent } from '../aqi-badge/aqi-badge.component';

@Component({
  selector: 'app-node-status-card',
  standalone: true,
  imports: [AqiBadgeComponent],
  templateUrl: './node-status-card.component.html',
  styleUrl: './node-status-card.component.scss',
})
export class NodeStatusCardComponent implements OnInit, OnDestroy {
  node = input.required<NodeTelemetry>();

  heartbeatAge = '';
  leaseRemaining = '';
  private intervalId: any;

  ngOnInit(): void {
    this.updateTimers();
    this.intervalId = setInterval(() => this.updateTimers(), 1000);
  }

  ngOnDestroy(): void {
    clearInterval(this.intervalId);
  }

  private updateTimers(): void {
    const now = Date.now();
    const n = this.node();

    // Heartbeat age
    const beatAge = Math.floor((now - new Date(n.last_heartbeat).getTime()) / 1000);
    this.heartbeatAge = beatAge < 60 ? `${beatAge}s ago` : `${Math.floor(beatAge / 60)}m ${beatAge % 60}s ago`;

    // Lease remaining
    const leaseLeft = Math.max(0, Math.floor((new Date(n.lease_expires_at).getTime() - now) / 1000));
    const lm = Math.floor(leaseLeft / 60);
    const ls = leaseLeft % 60;
    this.leaseRemaining = `${lm}:${ls.toString().padStart(2, '0')}`;
  }

  get healthClass(): string {
    switch (this.node().health) {
      case 'HEALTHY': return 'health-healthy';
      case 'STALLED': return 'health-stalled';
      case 'OFFLINE': return 'health-offline';
    }
  }

  get stageLabel(): string {
    return this.node().current_stage.replace(/_/g, ' ');
  }

  get modelShort(): string {
    const m = this.node().loaded_model;
    return m.replace('ggml-', '').replace('.bin', '');
  }

  get sidecarClass(): string {
    switch (this.node().sidecar_status) {
      case 'ACTIVE': return 'sidecar-active';
      case 'RESTARTING': return 'sidecar-restarting';
      case 'BACKPRESSURE_PAUSED': return 'sidecar-paused';
      case 'OFFLINE': return 'sidecar-offline';
    }
  }
}
