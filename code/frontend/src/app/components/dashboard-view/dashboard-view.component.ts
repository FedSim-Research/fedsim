import { CommonModule } from '@angular/common';
import { Component, Input, computed, inject } from '@angular/core';
import { DomSanitizer, SafeResourceUrl } from '@angular/platform-browser';
import { SimulationRunResponse } from '../../services/graph-api.service';
import { FrameworkJobsService } from '../../services/framework-jobs.service';
import { DashboardRunsService } from '../../services/dashboard-runs.service';

type ComparableMetrics = {
  accuracy: number | null;
  loss: number | null;
};

type ArchitectureMetrics = {
  architecture: 'hierarchical' | 'spyker';
  metrics: ComparableMetrics;
};

type ArchitectureEmbed = {
  architecture: 'hierarchical' | 'spyker';
  src: SafeResourceUrl;
};

@Component({
  selector: 'app-dashboard-view',
  standalone: true,
  imports: [CommonModule],
  templateUrl: './dashboard-view.component.html',
  styleUrl: './dashboard-view.component.css',
})
export class DashboardViewComponent {
  private sanitizer = inject(DomSanitizer);
  private frameworkJobsService = inject(FrameworkJobsService);
  private runsService = inject(DashboardRunsService);

  private grafanaBaseUrl = this.resolveGrafanaBaseUrl();
  private grafanaUrlCache = new Map<string, SafeResourceUrl>();
  private readonly defaultRangeMs = 15 * 60 * 1000;
  private readonly iframeRefreshIntervalMs = 30 * 1000;

  @Input() public sidebarOpen = true;

  public pollingSupported = this.runsService.pollingSupported;
  public selectedRun = this.runsService.selectedRun;
  public compareRuns = this.runsService.compareRuns;
  public runStats = this.runsService.runStats;
  public runs = this.runsService.runs;

  public frameworkJobs = this.frameworkJobsService.jobs;
  public recentJobs = computed(() => this.frameworkJobs().slice(0, 8));

  public telemetryPanels = [
    { title: 'Cluster Utilization', uid: 'rayDefaultDashboard', panelId: 41, height: 250 },
    { title: 'All Actors by State', uid: 'rayDefaultDashboard', panelId: 35, height: 250 },
    { title: 'Node CPU Usage', uid: 'rayDefaultDashboard', panelId: 2, height: 250 },
    { title: 'Node Memory Usage', uid: 'rayDefaultDashboard', panelId: 4, height: 250 },
    { title: 'Node GPU Usage', uid: 'rayDefaultDashboard', panelId: 8, height: 250 },
    { title: 'Tasks by State', uid: 'rayDefaultDashboard', panelId: 26, height: 280 },
  ] as const;

  public telemetryEmbeds = computed(() => {
    const run = this.selectedRun();
    const range = this.runTimeRange(run);
    const runId = this.toGrafanaRunIdParam(run?.run_id ?? '');
    const architecture = this.toGrafanaArchitectureParam(run?.architecture ? String(run.architecture) : '');
    return this.telemetryPanels.map((panel) => ({
      ...panel,
      src: this.getGrafanaPanelUrl({
        uid: panel.uid,
        panelId: panel.panelId,
        rangeFrom: range.from,
        rangeTo: range.to,
        runId,
        architecture,
      }),
    }));
  });

  public modelQualityTrendEmbed = computed(() => {
    const run = this.selectedRun();
    const range = this.runTimeRange(run);
    const runId = this.toGrafanaRunIdParam(run?.run_id ?? '');
    const architecture = this.toGrafanaArchitectureParam(run?.architecture ? String(run.architecture) : '');
    return this.getGrafanaPanelUrl({
      uid: 'fedsimFrontendDashboard',
      panelId: 1008,
      rangeFrom: range.from,
      rangeTo: range.to,
      runId,
      architecture,
    });
  });

  public modelQualityTrendEmbedsForBoth = computed<ArchitectureEmbed[]>(() => {
    const run = this.selectedRun();
    if (!run || String(run.architecture) !== 'both') {
      return [];
    }
    const range = this.runTimeRange(run);
    const runId = this.toGrafanaRunIdParam(run.run_id ?? '');
    return (['hierarchical', 'spyker'] as const).map((architecture) => ({
      architecture,
      src: this.getGrafanaPanelUrl({
        uid: 'fedsimFrontendDashboard',
        panelId: 1008,
        rangeFrom: range.from,
        rangeTo: range.to,
        runId,
        architecture: this.toGrafanaArchitectureParam(architecture),
      }),
    }));
  });

  public modelQualitySnapshot = computed<{ url: string } | null>(() => {
    const run = this.selectedRun();
    if (!run) {
      return null;
    }
    if (run.accuracy_loss_snapshot_url) {
      return { url: run.accuracy_loss_snapshot_url };
    }
    return null;
  });

  public modelQualitySnapshotsByArchitecture = computed<Array<{ architecture: 'hierarchical' | 'spyker'; url: string }>>(() => {
    const run = this.selectedRun();
    if (!run || !run.accuracy_loss_snapshot_urls_by_architecture) {
      return [];
    }
    return (['hierarchical', 'spyker'] as const)
      .map((arch) => ({
        architecture: arch,
        url: run.accuracy_loss_snapshot_urls_by_architecture?.[arch] ?? '',
      }))
      .filter((item) => item.url);
  });

  public getStatusClass(status: SimulationRunResponse['status']): string {
    return `status-pill status-pill--${status}`;
  }

  public formatEpoch(epochMs: number | null | undefined): string {
    if (epochMs === null || epochMs === undefined) {
      return '-';
    }
    const value = new Date(epochMs);
    if (Number.isNaN(value.getTime())) {
      return '-';
    }
    return value.toLocaleString();
  }

  public formatDuration(seconds: number | null | undefined): string {
    if (seconds === null || seconds === undefined) {
      return '-';
    }
    return `${seconds.toFixed(2)}s`;
  }

  public formatProgress(run: SimulationRunResponse): string {
    const progress = this.getProgressPercent(run);
    return progress === null ? '-' : `${progress.toFixed(1)}%`;
  }

  public getRunMetrics(run: SimulationRunResponse): ComparableMetrics {
    if (run.evaluation) {
      return {
        accuracy: run.evaluation.accuracy ?? null,
        loss: run.evaluation.avg_loss ?? null,
      };
    }

    if (run.results_by_architecture) {
      const parts = Object.values(run.results_by_architecture);
      if (parts.length > 0) {
        const accuracies = parts
          .map((entry) => entry.evaluation?.accuracy)
          .filter((value): value is number => typeof value === 'number');
        const losses = parts
          .map((entry) => entry.evaluation?.avg_loss)
          .filter((value): value is number => typeof value === 'number');
        return {
          accuracy: accuracies.length ? accuracies.reduce((sum, value) => sum + value, 0) / accuracies.length : null,
          loss: losses.length ? losses.reduce((sum, value) => sum + value, 0) / losses.length : null,
        };
      }
    }

    return { accuracy: null, loss: null };
  }

  public isCombinedRun(run: SimulationRunResponse): boolean {
    return String(run.architecture) === 'both' && !!run.results_by_architecture;
  }

  public getCombinedRunMetrics(run: SimulationRunResponse): ArchitectureMetrics[] {
    const byArchitecture = run.results_by_architecture;
    if (!byArchitecture) {
      return [];
    }

    return (['hierarchical', 'spyker'] as const).map((architecture) => ({
      architecture,
      metrics: {
        accuracy: byArchitecture[architecture]?.evaluation?.accuracy ?? null,
        loss: byArchitecture[architecture]?.evaluation?.avg_loss ?? null,
      },
    }));
  }

  public architectureLabel(architecture: 'hierarchical' | 'spyker' | 'both'): string {
    if (architecture === 'hierarchical') {
      return 'hierarchical';
    }
    if (architecture === 'spyker') {
      return 'Spyker';
    }
    return 'Both';
  }

  public normalizeArchitecture(value: string | null | undefined): 'hierarchical' | 'spyker' | 'both' {
    if (value === 'hierfl') {
      return 'hierarchical';
    }
    if (value === 'hierarchical' || value === 'spyker' || value === 'both') {
      return value;
    }
    return 'spyker';
  }

  public formatPercent(value: number | null): string {
    if (value === null) {
      return '-';
    }
    return `${(value * 100).toFixed(2)}%`;
  }

  public formatLoss(value: number | null): string {
    if (value === null) {
      return '-';
    }
    return value.toFixed(4);
  }

  public getCombinedGraphIds(run: SimulationRunResponse): { hierarchical: number | null; spyker: number | null } {
    const metadata = run.run_metadata as Record<string, unknown> | null | undefined;
    const combinedPayload = (metadata?.['combined_payload'] as Record<string, unknown> | undefined) ?? {};
    const hierarchical = combinedPayload['hierarchical'] as Record<string, unknown> | undefined;
    const spyker = combinedPayload['spyker'] as Record<string, unknown> | undefined;
    const hierarchicalGraphId = typeof hierarchical?.['graph_id'] === 'number' ? (hierarchical['graph_id'] as number) : null;
    const spykerGraphId = typeof spyker?.['graph_id'] === 'number' ? (spyker['graph_id'] as number) : null;
    return { hierarchical: hierarchicalGraphId, spyker: spykerGraphId };
  }

  public exportRunToCsv(run: SimulationRunResponse): void {
    const apiBase = (window as any).FEDSIM_API_BASE_URL as string | undefined;
    const baseUrl = apiBase || '/api';
    const csvUrl = `${baseUrl}/runs/${encodeURIComponent(run.run_id)}/export/csv`;
    
    const link = document.createElement('a');
    link.href = csvUrl;
    link.download = `run_${run.run_id}.csv`;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  }

  public downloadRunLogs(run: SimulationRunResponse): void {
    const apiBase = (window as any).FEDSIM_API_BASE_URL as string | undefined;
    const baseUrl = apiBase || '/api';
    const logsUrl = `${baseUrl}/runs/${encodeURIComponent(run.run_id)}/logs`;

    const link = document.createElement('a');
    link.href = logsUrl;
    link.download = `run_${run.run_id}.log`;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  }

  private getProgressPercent(run: SimulationRunResponse): number | null {
    const currentRaw = run.current_sim_time;
    const limitRaw = run.run_time_limit;

    const current = currentRaw === null || currentRaw === undefined ? Number.NaN : Number(currentRaw);
    const limit = limitRaw === null || limitRaw === undefined ? Number.NaN : Number(limitRaw);

    if (!Number.isFinite(current)) {
      return null;
    }
    if (!Number.isFinite(limit) || limit <= 0) {
      return null;
    }

    const percent = (current / limit) * 100;
    return Math.max(0, Math.min(100, percent));
  }

  private runTimeRange(run: SimulationRunResponse | null): { from: number; to: number } {
    // Keep iframe URL changes on a fixed cadence so embeds refresh every 30 seconds.
    const now = Math.floor(Date.now() / this.iframeRefreshIntervalMs) * this.iframeRefreshIntervalMs;
    const queuedAt = run?.queued_at ? new Date(run.queued_at).getTime() : NaN;
    const startedAt = run?.started_at ? new Date(run.started_at).getTime() : NaN;
    const finishedAt = run?.finished_at ? new Date(run.finished_at).getTime() : NaN;

    const fromCandidate = Number.isFinite(startedAt)
      ? startedAt
      : Number.isFinite(queuedAt)
      ? queuedAt
      : now - this.defaultRangeMs;
    const toCandidate = Number.isFinite(finishedAt) ? finishedAt : now;
    const fromSafe = Number.isFinite(fromCandidate) ? fromCandidate : now - this.defaultRangeMs;
    const toSafe = Number.isFinite(toCandidate) ? toCandidate : now;

    return {
      from: Math.min(fromSafe, toSafe),
      to: Math.max(fromSafe + 1000, toSafe),
    };
  }

  private getGrafanaPanelUrl(args: {
    uid: string;
    panelId: number;
    rangeFrom: number;
    rangeTo: number;
    runId: string;
    architecture: string;
  }): SafeResourceUrl {
    const cacheKey = JSON.stringify(args);
    const cached = this.grafanaUrlCache.get(cacheKey);
    if (cached) {
      return cached;
    }
    const runId = args.runId ? encodeURIComponent(args.runId) : '';
    const architecture = args.architecture ? encodeURIComponent(args.architecture) : '';
    const url =
      `${this.grafanaBaseUrl}/d-solo/${args.uid}/_` +
      `?orgId=1&from=${Math.trunc(args.rangeFrom)}&to=${Math.trunc(args.rangeTo)}&timezone=browser` +
      `&panelId=${args.panelId}&theme=dark&kiosk` +
      `&var-run_id=${runId}&var-architecture=${architecture}`;
    const safe = this.sanitizer.bypassSecurityTrustResourceUrl(url);
    this.grafanaUrlCache.set(cacheKey, safe);
    return safe;
  }

  private toGrafanaArchitectureParam(value: string): string {
    if (value === 'hierfl') {
      return 'hierarchical';
    }
    if (value === 'hierarchical') {
      return 'hierarchical';
    }
    if (value === 'both') {
      return 'spyker|hierarchical';
    }
    return value;
  }

  private toGrafanaRunIdParam(value: string): string {
    const trimmed = value.trim();
    if (!trimmed) {
      return '';
    }
    const baseRunId = trimmed.split(':', 1)[0];
    return baseRunId.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  }

  private toEpoch(value: string | null | undefined): number {
    if (!value) {
      return Number.NaN;
    }
    return new Date(value).getTime();
  }

  private resolveGrafanaBaseUrl(): string {
    const win = window as any;
    const configured = win.FEDSIM_GRAFANA_BASE_URL as string | undefined;
    if (typeof configured === 'string' && configured.trim()) {
      return configured.trim().replace(/\/$/, '');
    }

    const apiBase = win.FEDSIM_API_BASE_URL as string | undefined;
    if (apiBase === '/api') {
      return `${window.location.origin}/grafana`;
    }

    return 'http://localhost:3000';
  }
}
