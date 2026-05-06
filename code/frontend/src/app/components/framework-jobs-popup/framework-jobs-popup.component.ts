import { CommonModule } from '@angular/common';
import { Component, OnDestroy, OnInit, computed, inject, signal } from '@angular/core';
import { DashboardRunsService } from '../../services/dashboard-runs.service';
import { SimulationRunResponse } from '../../services/graph-api.service';

@Component({
  selector: 'app-framework-jobs-popup',
  standalone: true,
  imports: [CommonModule],
  templateUrl: './framework-jobs-popup.component.html',
  styleUrl: './framework-jobs-popup.component.css',
})
export class FrameworkJobsPopupComponent implements OnInit, OnDestroy {
  private runsService = inject(DashboardRunsService);
  public isOpen = signal(false);
  public activeRuns = computed(() =>
    this.runsService.runs().filter((run) => run.status === 'queued' || run.status === 'running')
  );
  public runningCount = computed(() =>
    this.activeRuns().filter((run) => run.status === 'running').length
  );
  public queuedCount = computed(() =>
    this.activeRuns().filter((run) => run.status === 'queued').length
  );

  public ngOnInit(): void {
    this.runsService.startPolling();
  }

  public ngOnDestroy(): void {
    this.runsService.stopPolling();
  }

  public toggle(): void {
    this.isOpen.update((value) => !value);
  }

  public formatRunProgress(run: SimulationRunResponse): string {
    const progress = this.getProgressPercent(run);
    return progress === null ? '-' : `${progress.toFixed(1)}%`;
  }

  public formatRunTitle(run: SimulationRunResponse): string {
    const architecture = String(run.architecture ?? 'unknown').toUpperCase();
    const graphId = run.graph_id ?? '-';
    return `${architecture} run · graph ${graphId}`;
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
}
