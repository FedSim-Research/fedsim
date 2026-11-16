import { HttpErrorResponse } from '@angular/common/http';
import { Injectable, computed, inject, signal } from '@angular/core';
import { GraphApiService, SimulationRunResponse } from '../api/graph-api.service';
import { Architecture, parseRunArchitecture } from '../domain/topology';

@Injectable({ providedIn: 'root' })
export class DashboardRunsService {
  private graphApi = inject(GraphApiService);
  private pollHandle: ReturnType<typeof setInterval> | null = null;
  private pollConsumers = 0;
  private refreshInFlight: Promise<void> | null = null;

  public loading = signal(false);
  public error = signal<string | null>(null);
  public pollingSupported = signal(true);

  public runs = signal<SimulationRunResponse[]>([]);
  public selectedRunId = signal<string | null>(null);
  public compareRunIds = signal<string[]>([]);

  public filterArchitecture = signal<'all' | Architecture | 'both'>('all');
  public filterStatus = signal<'all' | 'queued' | 'running' | 'completed' | 'failed'>('all');
  public searchText = signal('');

  public selectedRun = computed(() => {
    const selected = this.selectedRunId();
    if (!selected) {
      return null;
    }
    return this.runs().find((run) => run.run_id === selected) ?? null;
  });

  public compareRuns = computed(() => {
    const selectedIds = this.compareRunIds();
    return this.runs().filter((run) => selectedIds.includes(run.run_id)).slice(0, 2);
  });

  public runStats = computed(() => {
    const all = this.runs();
    const completed = all.filter((run) => run.status === 'completed').length;
    const failed = all.filter((run) => run.status === 'failed').length;
    const queued = all.filter((run) => run.status === 'queued').length;
    const running = all.filter((run) => run.status === 'running').length;
    return {
      total: all.length,
      queued,
      running,
      completed,
      failed,
    };
  });

  public filteredRuns = computed(() => {
    const architecture = this.filterArchitecture();
    const status = this.filterStatus();
    const search = this.searchText().trim().toLowerCase();

    return this.runs().filter((run) => {
      if (architecture !== 'all' && parseRunArchitecture(run.architecture) !== architecture) {
        return false;
      }
      if (status !== 'all' && run.status !== status) {
        return false;
      }
      if (!search) {
        return true;
      }
      const haystack = [
        run.run_id,
        String(run.architecture ?? ''),
        String(run.graph_id ?? ''),
        String(run.status ?? ''),
      ]
        .join(' ')
        .toLowerCase();
      return haystack.includes(search);
    });
  });

  /** Each consumer that starts polling must call `stopPolling` once when it goes away. */
  public startPolling(): void {
    this.pollConsumers += 1;
    if (this.pollHandle) {
      return;
    }
    void this.refreshRuns();
    this.pollHandle = setInterval(() => {
      if (!this.pollingSupported()) {
        return;
      }
      void this.refreshRuns();
    }, 4000);
  }

  public stopPolling(): void {
    this.pollConsumers = Math.max(0, this.pollConsumers - 1);
    if (this.pollConsumers === 0 && this.pollHandle) {
      clearInterval(this.pollHandle);
      this.pollHandle = null;
    }
  }

  public refreshRuns(): Promise<void> {
    if (this.refreshInFlight) return this.refreshInFlight;
    this.refreshInFlight = this.loadRuns().finally(() => { this.refreshInFlight = null; });
    return this.refreshInFlight;
  }

  private async loadRuns(): Promise<void> {
    this.loading.set(true);
    if (this.pollingSupported()) {
      this.error.set(null);
    }
    try {
      const list = await this.graphApi.listRuns();
      this.pollingSupported.set(true);
      this.runs.set(list);
      if (!this.selectedRunId() && list.length > 0) {
        this.selectedRunId.set(list[0].run_id);
      }
      if (this.selectedRunId() && !list.some((run) => run.run_id === this.selectedRunId())) {
        this.selectedRunId.set(list[0]?.run_id ?? null);
      }
      this.compareRunIds.set(this.compareRunIds().filter((id) => list.some((run) => run.run_id === id)));
    } catch (err) {
      if (err instanceof HttpErrorResponse && err.status === 404) {
        this.pollingSupported.set(false);
        this.error.set('Run tracking endpoint (/runs) is not available in the current backend. Auto-refresh is paused.');
      } else {
        this.error.set('Could not load runs from backend.');
      }
    } finally {
      this.loading.set(false);
    }
  }

  public async deleteRun(runId: string): Promise<void> {
    await this.graphApi.deleteRun(runId);
    // A request started before deletion can still contain the deleted run.
    await this.refreshInFlight;
    await this.refreshRuns();
  }

  public async retryRunTracking(): Promise<void> {
    this.pollingSupported.set(true);
    await this.refreshRuns();
  }

  public selectRun(runId: string): void {
    this.selectedRunId.set(runId);
  }

  public toggleCompare(runId: string): void {
    const current = this.compareRunIds();
    if (current.includes(runId)) {
      this.compareRunIds.set(current.filter((id) => id !== runId));
      return;
    }
    if (current.length >= 2) {
      this.compareRunIds.set([current[1], runId]);
      return;
    }
    this.compareRunIds.set([...current, runId]);
  }

  public isCompared(runId: string): boolean {
    return this.compareRunIds().includes(runId);
  }

  public clearCompare(): void {
    this.compareRunIds.set([]);
  }
}
