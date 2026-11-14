import { TestBed } from '@angular/core/testing';
import { SecurityContext, signal } from '@angular/core';
import { DomSanitizer } from '@angular/platform-browser';
import { SimulationRunResponse } from '../../api/graph-api.service';
import { DashboardRunsService } from '../dashboard-runs.service';
import { FrameworkJobsService } from '../framework-jobs.service';
import { DashboardViewComponent } from './dashboard-view';
import { ThemeService } from '../../shared/theme.service';

describe('Dashboard server evaluation results', () => {
  const selectedRun = signal<SimulationRunResponse | null>(null);

  beforeEach(async () => {
    document.body.classList.remove('light-mode');
    selectedRun.set(null);
    await TestBed.configureTestingModule({
      imports: [DashboardViewComponent],
      providers: [
        { provide: FrameworkJobsService, useValue: { jobs: signal([]) } },
        { provide: DashboardRunsService, useValue: {
          selectedRun, pollingSupported: signal(true), compareRuns: signal([]),
          runs: signal([]), runStats: signal({ total: 0, queued: 0, running: 0, completed: 0, failed: 0 }),
        } },
      ],
    }).compileComponents();
  });

  afterEach(() => document.body.classList.remove('light-mode'));

  it('updates embedded dashboards when the shared theme changes', () => {
    selectedRun.set({ run_id: 'theme-run', status: 'completed', architecture: 'hierfl',
      started_at: '2026-11-14T10:00:00Z', finished_at: '2026-11-14T10:01:00Z' });
    const fixture = TestBed.createComponent(DashboardViewComponent);
    const sanitizer = TestBed.inject(DomSanitizer);
    const theme = TestBed.inject(ThemeService);
    const darkUrl = fixture.componentInstance.modelQualityTrendEmbed();
    expect(sanitizer.sanitize(SecurityContext.RESOURCE_URL, darkUrl)).toContain('&theme=dark&');
    theme.toggle();
    const lightUrl = fixture.componentInstance.modelQualityTrendEmbed();
    expect(sanitizer.sanitize(SecurityContext.RESOURCE_URL, lightUrl)).toContain('&theme=light&');
    expect(lightUrl).not.toBe(darkUrl);
    theme.toggle();
    expect(fixture.componentInstance.modelQualityTrendEmbed()).toBe(darkUrl);
  });

  const serverEvaluation = (accuracy: number) => ({
    accuracy, avg_loss: 1.5, aggregation: 'server_macro_mean', server_count: 2,
    per_server: { A: { accuracy: 0.8, avg_loss: 1 }, B: { accuracy: 0.4, avg_loss: 2 } },
  });

  it('renders both server metrics and identifies their macro mean', () => {
    selectedRun.set({ run_id: 'new', status: 'completed', architecture: 'spyker', seed: 17,
      evaluation: serverEvaluation(0.6) });
    const fixture = TestBed.createComponent(DashboardViewComponent);
    fixture.detectChanges();
    const element = fixture.nativeElement as HTMLElement;
    expect(element.querySelectorAll('.server-results tbody tr').length).toBe(2);
    expect(element.textContent).toContain('Mean across servers');
    expect(element.querySelector('.server-results')?.textContent).toContain('80.00%');
    expect(element.querySelector('.server-results')?.textContent).toContain('40.00%');
  });

  it.each(['hierfl', 'hierarchical'])('keeps architecture summaries and duplicate seeds for the %s key', (hierarchyKey) => {
    const summary = (mean: number) => ({ evaluated_repetitions: 2, mean_accuracy: mean,
      variance_accuracy: 0, mean_avg_loss: 1.5, variance_avg_loss: 0 });
    const run: SimulationRunResponse = { run_id: 'paired', status: 'completed', architecture: 'both',
      results_by_architecture: {
        [hierarchyKey]: { evaluation_summary: summary(0.9) },
        spyker: { evaluation_summary: summary(0.65), runs: [
          { seed: 17, repetition_index: 1, evaluation: serverEvaluation(0.6) },
          { seed: 17, repetition_index: 2, evaluation: serverEvaluation(0.7) },
        ] },
      },
      run_metadata: { combined_payload: { [hierarchyKey]: { graph_id: 1 }, spyker: { graph_id: 2 } } },
      accuracy_loss_snapshot_urls_by_architecture: { [hierarchyKey]: 'hierarchy-snapshot', spyker: 'spyker-snapshot' },
    };
    selectedRun.set(run);
    const fixture = TestBed.createComponent(DashboardViewComponent);
    fixture.detectChanges();
    expect(fixture.componentInstance.getCombinedRunMetrics(run).map((entry) => entry.metrics.accuracy))
      .toEqual([0.9, 0.65]);
    expect(fixture.nativeElement.querySelectorAll('.server-results tbody tr').length).toBe(4);
    expect(fixture.componentInstance.getCombinedGraphIds(run)).toEqual({ hierarchical: 1, spyker: 2 });
    expect(fixture.componentInstance.modelQualitySnapshotsByArchitecture().map((entry) => entry.url))
      .toEqual(['hierarchy-snapshot', 'spyker-snapshot']);
    expect(fixture.nativeElement.textContent).toContain('Mean across servers and repetitions');
  });

  it('shows legacy metrics without inventing a server scope', () => {
    const run: SimulationRunResponse = { run_id: 'legacy', status: 'completed', architecture: 'spyker',
      evaluation: { accuracy: 0.7, avg_loss: 0.9 } };
    selectedRun.set(run);
    const fixture = TestBed.createComponent(DashboardViewComponent);
    fixture.detectChanges();
    expect(fixture.componentInstance.getRunMetrics(run).accuracy).toBe(0.7);
    expect(fixture.nativeElement.querySelector('.server-results')).toBeNull();
    expect(fixture.nativeElement.textContent).toContain('Recorded model');
  });
});
