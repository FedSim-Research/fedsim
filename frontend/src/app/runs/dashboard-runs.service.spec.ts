import { TestBed } from '@angular/core/testing';
import { GraphApiService } from '../api/graph-api.service';
import { DashboardRunsService } from './dashboard-runs.service';

describe('DashboardRunsService polling', () => {
  const listRuns = vi.fn().mockResolvedValue([]);

  beforeEach(() => {
    vi.useFakeTimers();
    listRuns.mockClear();
    TestBed.configureTestingModule({
      providers: [{ provide: GraphApiService, useValue: { listRuns } }],
    });
  });

  afterEach(() => vi.useRealTimers());

  it('keeps polling while another consumer is still active', async () => {
    const service = TestBed.inject(DashboardRunsService);
    service.startPolling();
    service.startPolling();
    service.stopPolling();
    listRuns.mockClear();

    await vi.advanceTimersByTimeAsync(4000);
    expect(listRuns).toHaveBeenCalledTimes(1);

    service.stopPolling();
    await vi.advanceTimersByTimeAsync(8000);
    expect(listRuns).toHaveBeenCalledTimes(1);
  });
});
