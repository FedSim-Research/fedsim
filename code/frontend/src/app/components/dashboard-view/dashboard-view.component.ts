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
  architecture: 'hierfl' | 'spyker';
  metrics: ComparableMetrics;
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

  private grafanaBaseUrl = ((window as any).FEDSIM_GRAFANA_BASE_URL as string | undefined) ?? 'http://localhost:3000';
  private grafanaUrlCache = new Map<string, SafeResourceUrl>();
  private readonly defaultRangeMs = 15 * 60 * 1000;

  @Input() public sidebarOpen = true;

  public pollingSupported = this.runsService.pollingSupported;
  public selectedRun = this.runsService.selectedRun;
  public compareRuns = this.runsService.compareRuns;
  public runStats = this.runsService.runStats;

  public frameworkJobs = this.frameworkJobsService.jobs;
  public recentJobs = computed(() => this.frameworkJobs().slice(0, 8));

  public telemetryPanels = [
    { title: 'Cluster Utilization', uid: 'rayDefaultDashboard', panelId: 41, height: 250 },
    { title: 'Ray OOM Kills', uid: 'rayDefaultDashboard', panelId: 44, height: 250 },
    { title: 'Node CPU Usage', uid: 'rayDefaultDashboard', panelId: 2, height: 250 },
    { title: 'Node Memory Usage', uid: 'rayDefaultDashboard', panelId: 4, height: 250 },
    { title: 'Node GPU Usage', uid: 'rayDefaultDashboard', panelId: 8, height: 250 },
    { title: 'Tasks by State', uid: 'rayDefaultDashboard', panelId: 26, height: 280 },
  ] as const;

  public telemetryEmbeds = computed(() => {
    const run = this.selectedRun();
    const range = this.runTimeRange(run);
    const runId = run?.run_id ?? '';
    const architecture = run?.architecture ? String(run.architecture) : '';
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
    const runId = run?.run_id ?? '';
    const architecture = run?.architecture ? String(run.architecture) : '';
    return this.getGrafanaPanelUrl({
      uid: 'fedsimFrontendDashboard',
      panelId: 1007,
      rangeFrom: range.from,
      rangeTo: range.to,
      runId,
      architecture,
    });
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

    return (['hierfl', 'spyker'] as const).map((architecture) => ({
      architecture,
      metrics: {
        accuracy: byArchitecture[architecture]?.evaluation?.accuracy ?? null,
        loss: byArchitecture[architecture]?.evaluation?.avg_loss ?? null,
      },
    }));
  }

  public architectureLabel(architecture: 'hierfl' | 'spyker'): string {
    return architecture === 'hierfl' ? 'HierFL' : 'Spyker';
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

  private runTimeRange(run: SimulationRunResponse | null): { from: number; to: number } {
    const now = Date.now();
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
}
