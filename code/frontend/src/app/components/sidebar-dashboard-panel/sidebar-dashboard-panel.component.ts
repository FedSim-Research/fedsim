import { CommonModule } from '@angular/common';
import { Component, OnDestroy, OnInit, computed, inject } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { ConfirmationService, MessageService } from 'primeng/api';
import { ConfirmDialogModule } from 'primeng/confirmdialog';
import { DashboardRunsService } from '../../services/dashboard-runs.service';
import { SimulationRunResponse } from '../../services/graph-api.service';

@Component({
  selector: 'app-sidebar-dashboard-panel',
  standalone: true,
  imports: [CommonModule, FormsModule, ConfirmDialogModule],
  templateUrl: './sidebar-dashboard-panel.component.html',
  styleUrl: './sidebar-dashboard-panel.component.css',
})
export class SidebarDashboardPanelComponent implements OnInit, OnDestroy {
  private runsService = inject(DashboardRunsService);
  private confirmationService = inject(ConfirmationService);
  private messageService = inject(MessageService);

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

  public canDeleteRun(run: SimulationRunResponse): boolean {
    return run.status === 'completed' || run.status === 'failed';
  }

  public async deleteRun(run: SimulationRunResponse, event: Event): Promise<void> {
    event.stopPropagation();
    if (!this.canDeleteRun(run)) {
      return;
    }
    this.confirmationService.confirm({
      header: 'Delete run',
      message: `Are you sure you want to delete ${run.run_id}?`,
      icon: 'pi pi-trash',
      acceptLabel: 'Yes',
      rejectLabel: 'No',
      acceptButtonStyleClass: 'cta-option cta-option--confirm p-button-danger',
      rejectButtonStyleClass: 'cta-option cta-option--cancel p-button-text',
      accept: async () => {
        try {
          await this.runsService.deleteRun(run.run_id);
          this.messageService.add({
            severity: 'success',
            summary: 'Run deleted',
            detail: `Run ${run.run_id} was removed from the database.`,
            life: 3500,
          });
        } catch (error) {
          this.messageService.add({
            severity: 'error',
            summary: 'Delete failed',
            detail: error instanceof Error ? error.message : 'Failed to delete run.',
            life: 4500,
          });
        }
      },
    });
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

  public formatProgress(run: SimulationRunResponse): string {
    const currentRaw = run.current_sim_time;
    const limitRaw = run.run_time_limit;

    const current = currentRaw === null || currentRaw === undefined ? Number.NaN : Number(currentRaw);
    const limit = limitRaw === null || limitRaw === undefined ? Number.NaN : Number(limitRaw);

    if (!Number.isFinite(current)) {
      return '-';
    }
    if (!Number.isFinite(limit) || limit <= 0) {
      return '-';
    }
    const percentage = Math.max(0, Math.min(100, (current / limit) * 100));
    return `${percentage.toFixed(1)}%`;
  }
}
