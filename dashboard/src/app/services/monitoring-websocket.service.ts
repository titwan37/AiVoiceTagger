import { Injectable, NgZone, inject } from '@angular/core';
import { Observable, Subject, interval } from 'rxjs';
import { switchMap, takeUntil } from 'rxjs/operators';
import { environment } from '../../environments/environment';
import { TelemetryPayload } from '../models/telemetry.models';

@Injectable({ providedIn: 'root' })
export class MonitoringWebSocketService {
  private zone = inject(NgZone);
  private destroy$ = new Subject<void>();
  private messagesSubject = new Subject<TelemetryPayload>();

  readonly messages$: Observable<TelemetryPayload> = this.messagesSubject.asObservable();

  constructor() {
    if (environment.useMockData) {
      // Mock mode
    } else {
      // ONLY start HTTP polling to prevent stream death
      this.startHttpPolling();
    }
  }

  private startHttpPolling(): void {
    interval(environment.mockIntervalMs || 2000).pipe(
      takeUntil(this.destroy$)
    ).subscribe(() => {
      fetch(`${environment.apiUrl}/api/telemetry`)
        .then(res => {
          if (!res.ok) throw new Error(`HTTP ${res.status}`);
          return res.json();
        })
        .then(payload => {
          if (payload) {
            this.zone.run(() => this.messagesSubject.next(payload));
          }
        })
        .catch(err => {
          console.error('[HttpPolling] Fetch error:', err);
        });
    });
  }

  async sendCommand(endpoint: string, payload: any = {}): Promise<any> {
    try {
      const res = await fetch(`${environment.apiUrl}/api/control/${endpoint}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });
      return await res.json();
    } catch (err) {
      return { status: 'error', message: String(err) };
    }
  }

  disconnect(): void {
    this.destroy$.next();
    this.destroy$.complete();
  }
}