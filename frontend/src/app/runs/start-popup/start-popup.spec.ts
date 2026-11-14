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
    const fixture = TestBed.createComponent(StartPopup);
    fixture.componentInstance.hierflGraphId = 3;
    fixture.detectChanges();

    const settings = fixture.componentInstance.hierflSettings as Record<string, unknown>;
    expect(settings['epochs']).toBe(1);
    expect(settings['lr']).toBe(0.01);
    expect(settings['batchSize']).toBe(32);
    expect(settings['injected']).toBeUndefined();
  });
});
