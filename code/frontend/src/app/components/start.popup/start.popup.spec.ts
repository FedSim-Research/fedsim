import { ComponentFixture, TestBed } from '@angular/core/testing';

import { StartPopup } from './start.popup';

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
});
