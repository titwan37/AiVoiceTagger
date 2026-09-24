import { Component, ElementRef, ViewChild, AfterViewInit, OnDestroy, OnInit, signal, effect } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import React from 'react';
import { createRoot, Root } from 'react-dom/client';
import { ForensicVisualizer3D, DialogueSegmentNode } from './ForensicVisualizer3D';
import { environment } from '../../environments/environment';

@Component({
  selector: 'app-forensic-visualizer',
  standalone: true,
  imports: [CommonModule, FormsModule],
  template: `
    <div class="visualizer-container" style="display: flex; flex-direction: column; gap: 16px; background: #111827; padding: 20px; border-radius: 12px; border: 1px solid #1f2937;">
      <!-- Controls Toolbar -->
      <div class="toolbar" style="display: flex; justify-content: space-between; align-items: center; background: #1f2937; padding: 12px 20px; border-radius: 8px; border: 1px solid #374151;">
        <div style="display: flex; align-items: center; gap: 16px;">
          <label style="display: flex; align-items: center; gap: 8px; cursor: pointer; font-size: 0.85rem; color: #d1d5db; font-weight: 500; user-select: none;">
            <input 
              type="checkbox" 
              [checked]="anonymize()" 
              (change)="toggleAnonymize()"
              style="width: 16px; height: 16px; accent-color: #a855f7; cursor: pointer;"
            />
            <span>Anonymize Speaker Names</span>
          </label>
        </div>
        <div style="display: flex; align-items: center; gap: 12px;">
          <button 
            (click)="loadData()" 
            [disabled]="loading()"
            style="background: #374151; color: white; border: 1px solid #4b5563; padding: 6px 14px; border-radius: 6px; font-size: 0.8rem; font-weight: 600; cursor: pointer; transition: all 0.2s; display: inline-flex; align-items: center; gap: 6px;"
          >
            <span>{{ loading() ? '🔄 Loading...' : '🔁 Refresh Data' }}</span>
          </button>
          <span style="font-size: 0.75rem; color: #9ca3af; font-family: monospace;">
            Nodes: {{ nodesCount() }}
          </span>
        </div>
      </div>

      <!-- Error view if any -->
      <div *ngIf="error()" style="background: #7f1d1d; border: 1px solid #b91c1c; color: #fca5a5; padding: 12px 16px; border-radius: 8px; font-size: 0.85rem;">
        ⚠️ {{ error() }}
      </div>

      <!-- React Mounting Point -->
      <div #reactContainer class="react-visualizer-root" style="width: 100%; height: 800px; position: relative;"></div>
    </div>
  `
})
export class ForensicVisualizerComponent implements OnInit, AfterViewInit, OnDestroy {
  @ViewChild('reactContainer', { static: true }) reactContainer!: ElementRef<HTMLDivElement>;
  
  private reactRoot: Root | null = null;
  
  loading = signal<boolean>(false);
  anonymize = signal<boolean>(false);
  nodesCount = signal<number>(0);
  error = signal<string>('');
  private currentData: DialogueSegmentNode[] = [];

  constructor() {
    effect(() => {
      // Trigger reloading when anonymize state changes
      this.loadData();
    });
  }

  ngOnInit(): void {}

  ngAfterViewInit(): void {
    // Render initially in case effect ran before view initialized
    if (this.currentData.length > 0) {
      this.renderReactComponent();
    }
  }

  async loadData(): Promise<void> {
    this.loading.set(true);
    this.error.set('');
    
    try {
      const url = `${environment.apiUrl}/api/post_analytics/3d?anonymized=${this.anonymize()}`;
      const response = await fetch(url);
      if (!response.ok) {
        throw new Error(`Failed to fetch 3D constellation: HTTP ${response.status}`);
      }
      
      const payload = await response.json();
      if (payload.error) {
        throw new Error(payload.error);
      }
      
      this.currentData = payload.nodes || [];
      this.nodesCount.set(this.currentData.length);
      this.renderReactComponent();
    } catch (err: any) {
      console.error('[ForensicVisualizer] Error loading UMAP/constellation payload:', err);
      this.error.set(err.message || String(err));
      this.nodesCount.set(0);
      this.currentData = [];
      this.renderReactComponent();
    } finally {
      this.loading.set(false);
    }
  }

  toggleAnonymize(): void {
    this.anonymize.update(val => !val);
  }

  private renderReactComponent(): void {
    if (!this.reactContainer) return;
    
    try {
      if (!this.reactRoot) {
        this.reactRoot = createRoot(this.reactContainer.nativeElement);
      }
      
      this.reactRoot.render(
        React.createElement(ForensicVisualizer3D, { data: this.currentData })
      );
    } catch (err) {
      console.error('[ForensicVisualizer] Error rendering React tree:', err);
      this.error.set(`React render error: ${String(err)}`);
    }
  }

  ngOnDestroy(): void {
    if (this.reactRoot) {
      try {
        this.reactRoot.unmount();
      } catch (err) {
        console.error('[ForensicVisualizer] Error unmounting React root:', err);
      }
      this.reactRoot = null;
    }
  }
}
