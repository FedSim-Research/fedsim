import { ComponentFixture, TestBed } from '@angular/core/testing';

import { StartPopup } from './start-popup';
import { GraphApiService } from '../../api/graph-api.service';

describe('StartPopup', () => {
  let component: StartPopup;
  let fixture: ComponentFixture<StartPopup>;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [StartPopup]
    })
    .compileComponents();

    fixture = TestBed.createComponent(StartPopup);
    component = fixture.componentInstance;
    await fixture.whenStable();
  });

  it('should create', () => {
    expect(component).toBeTruthy();
  });

  it('detects aggressive absolute feedback without changing the chosen parameters', () => {
    component.spykerSettings.lr = 0.01;
    component.spykerSettings.decayBeta = 0.05;
    expect(component.absoluteDecayRatio).toBe(5);
    expect(component.spykerSettings.decayBeta).toBe(0.05);
    component.spykerSettings.decayMode = 'relative';
    expect(component.absoluteDecayRatio).toBeNull();
    component.spykerSettings.decayMode = 'absolute';
    component.spykerSettings.lr = 0;
    expect(component.absoluteDecayRatio).toBeNull();
  });

  it('counts duplicate seeds as separate repetitions', () => {
    component.updateSeedSet('hierfl', '42,42');

    expect(component.hierflSettings.repetitions).toBe(2);
  });

  it('emits duplicate seeds on run when provided', () => {
    component.selectMode('hierfl');
    component.updateSeedSet('hierfl', '42,42');
    let payload: any = null;
    component.run.subscribe((value: any) => {
      payload = value;
    });

    component.onRun();

    expect(payload).not.toBeNull();
    expect(payload?.hierfl.simulationSettings.seedSet).toEqual([42, 42]);
    expect(payload?.hierfl.simulationSettings.repetitions).toBe(2);
  });

  const seedMessage = 'Seeds must be non-negative integers separated by commas or spaces, e.g. 42, 43, 44.';

  it('explains invalid seed sets and accepts valid ones', () => {
    for (const valid of ['42, 43', '7', '1 2;3']) {
      component.updateSeedSet('hierfl', valid);
      expect(component.seedSetError('hierfl')).toBeNull();
    }
    for (const invalid of ['42, x', '1.5', '-3', '', ' , ']) {
      component.updateSeedSet('spyker', invalid);
      expect(component.seedSetError('spyker')).toBe(seedMessage);
    }
  });

  it('does not emit run when a running architecture has an invalid seed set', () => {
    component.selectMode('both');
    component.updateSeedSet('spyker', '42, x');
    const emitted = vi.fn();
    component.run.subscribe(emitted);

    component.onRun();

    expect(emitted).not.toHaveBeenCalled();
  });

  it('stays on the HierFL step while its seed set is invalid', () => {
    component.selectMode('both');
    component.nextStep();
    component.updateSeedSet('hierfl', '42, x');

    component.nextFromHierfl();

    expect(component.activeStep).toBe(2);
  });

  it('ignores the invalid seed set of an architecture that does not run', () => {
    component.selectMode('spyker');
    component.updateSeedSet('hierfl', 'x');
    const emitted = vi.fn();
    component.run.subscribe(emitted);

    component.onRun();

    expect(emitted).toHaveBeenCalledTimes(1);
  });

  it('restores persisted settings without appending defaults', () => {
    (component as any).applyPersistedParams('hierfl', {
      settings: {
        dataset: 'custom-dataset',
        outputFilename: 'restored.pth',
        epochs: 3,
      },
    });

    expect(component.hierflSettings.dataset).toBe('custom-dataset');
    expect(component.hierflSettings.outputFilename).toBe('restored.pth');
    expect(component.hierflSettings.epochs).toBe(3);

    (component as any).applyPersistedParams('hierfl', {
      settings: { dataset: 'custom-dataset', outputFilename: 'restored.pth' },
    });
    expect(component.hierflSettings.dataset).toBe('custom-dataset');
    expect(component.hierflSettings.outputFilename).toBe('restored.pth');
  });
});

describe('StartPopup stored settings', () => {
  beforeEach(() => {
    localStorage.clear();
    TestBed.configureTestingModule({
      imports: [StartPopup],
      providers: [{ provide: GraphApiService, useValue: { getGraph: vi.fn().mockRejectedValue(new Error('offline')) } }],
    });
  });

  it('ignores stored values of the wrong type and unknown keys', () => {
    localStorage.setItem('fedsim.start-params.hierfl.3', JSON.stringify({
      settings: { epochs: 'many', lr: 0.01, batchSize: null, injected: '<b>x</b>' },
      updatedAt: 1,
    }));
    localStorage.setItem('fedsim.start-params.spyker.4', JSON.stringify({
      settings: { hIntra: 70, tcpRtoDelay: 9 },
      updatedAt: 1,
    }));
    const fixture = TestBed.createComponent(StartPopup);
    fixture.componentInstance.hierflGraphId = 3;
    fixture.componentInstance.spykerGraphId = 4;
    fixture.detectChanges();

    const settings = fixture.componentInstance.hierflSettings as Record<string, unknown>;
    expect(settings['epochs']).toBe(1);
    expect(settings['lr']).toBe(0.01);
    expect(settings['batchSize']).toBe(32);
    expect(settings['injected']).toBeUndefined();
    expect(fixture.componentInstance.spykerSettings.hIntra).toBe(70);
    expect(fixture.componentInstance.spykerSettings).not.toHaveProperty('tcpRtoDelay');
  });
});

describe('StartPopup backend sync', () => {
  let resolveGraph: (graph: { metadata: Record<string, unknown> }) => void;
  const api = { getGraph: vi.fn(), patchGraphMetadata: vi.fn() };

  function createPopup() {
    const fixture = TestBed.createComponent(StartPopup);
    fixture.componentInstance.hierflGraphId = 5;
    fixture.componentInstance.selectedMode = 'hierfl';
    fixture.detectChanges();
    return fixture;
  }

  beforeEach(() => {
    vi.useFakeTimers();
    localStorage.clear();
    api.getGraph.mockReset().mockReturnValue(new Promise((resolve) => { resolveGraph = resolve; }));
    api.patchGraphMetadata.mockReset().mockResolvedValue({});
    TestBed.configureTestingModule({
      imports: [StartPopup],
      providers: [{ provide: GraphApiService, useValue: api }],
    });
  });

  afterEach(() => vi.useRealTimers());

  it('still syncs a pending settings change when destroyed within the debounce window', async () => {
    const fixture = createPopup();
    await vi.advanceTimersByTimeAsync(500);
    api.patchGraphMetadata.mockClear();

    fixture.componentInstance.hierflSettings.epochs = 7;
    fixture.componentInstance.onSettingsChanged();
    fixture.destroy();
    await vi.advanceTimersByTimeAsync(500);

    expect(api.patchGraphMetadata).toHaveBeenCalledTimes(1);
    expect(api.patchGraphMetadata.mock.calls[0][0]).toBe(5);
    expect(api.patchGraphMetadata.mock.calls[0][1].patch.start_params.settings.epochs).toBe(7);
  });

  it('keeps the evaluate toggle when the backend answers late', async () => {
    const fixture = createPopup();
    fixture.componentInstance.onEvaluateAfterRunChanged(true);

    resolveGraph({ metadata: { start_params: { evaluateAfterRun: false, updatedAt: Date.now() + 1000 } } });
    await vi.advanceTimersByTimeAsync(0);

    expect(fixture.componentInstance.evaluateAfterRun).toBe(true);
    expect(localStorage.getItem('fedsim.start-params.hierfl.5')).toContain('"evaluateAfterRun":true');
  });

  it('ignores a backend answer that arrives after destroy', async () => {
    const fixture = createPopup();
    const stored = localStorage.getItem('fedsim.start-params.hierfl.5');
    fixture.destroy();

    resolveGraph({ metadata: { start_params: { settings: { epochs: 9 }, updatedAt: Date.now() + 1000 } } });
    await vi.advanceTimersByTimeAsync(0);

    expect(fixture.componentInstance.hierflSettings.epochs).toBe(1);
    expect(localStorage.getItem('fedsim.start-params.hierfl.5')).toBe(stored);
  });
});
