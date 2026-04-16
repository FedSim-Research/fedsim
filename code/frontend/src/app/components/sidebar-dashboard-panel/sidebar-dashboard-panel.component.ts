import { CommonModule } from '@angular/common';
import { Component, OnDestroy, OnInit, computed, inject } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { DashboardRunsService } from '../../services/dashboard-runs.service';
import { SimulationRunResponse } from '../../services/graph-api.service';

@Component({
  selector: 'app-sidebar-dashboard-panel',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './sidebar-dashboard-panel.component.html',
  styleUrl: './sidebar-dashboard-panel.component.css',
})
export class SidebarDashboardPanelComponent implements OnInit, OnDestroy {
  private runsService = inject(DashboardRunsService);

  public loading = this.runsService.loading;
  public error = this.runsService.error;
  public pollingSupported = this.runsService.pollingSupported;

  public filterArchitecture = this.runsService.filterArchitecture;
  public filterStatus = this.runsService.filterStatus;
  public searchText = this.runsService.searchText;

  public selectedRunId = this.runsService.selectedRunId;
  public filteredRuns = this.runsService.filteredRuns;
  public compareRunIds = this.runsService.compareRunIds;

  public compareCount = computed(() => this.compareRunIds().length);

  public ngOnInit(): void {
    this.runsService.startPolling();
  }

  public ngOnDestroy(): void {
    this.runsService.stopPolling();
  }

  public selectRun(runId: string): void {
    this.runsService.selectRun(runId);
  }

  public toggleCompare(runId: string): void {
    this.runsService.toggleCompare(runId);
  }

  public isCompared(runId: string): boolean {
    return this.runsService.isCompared(runId);
  }

  public clearCompare(): void {
    this.runsService.clearCompare();
  }

  public async refreshRuns(): Promise<void> {
    await this.runsService.refreshRuns();
  }

  public async retryRunTracking(): Promise<void> {
    await this.runsService.retryRunTracking();
  }

  public getStatusClass(status: SimulationRunResponse['status']): string {
    return `status-pill status-pill--${status}`;
  }

  public formatDate(iso: string | null | undefined): string {
    if (!iso) {
      return '-';
    }
    const value = new Date(iso);
    if (Number.isNaN(value.getTime())) {
      return '-';
    }
    return value.toLocaleString();
  }
}
