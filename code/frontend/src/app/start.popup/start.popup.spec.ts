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
});
