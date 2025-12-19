import { ComponentFixture, TestBed } from '@angular/core/testing';

import { SuperServerNode } from './super-server-node';

describe('SuperServerNode', () => {
  let component: SuperServerNode;
  let fixture: ComponentFixture<SuperServerNode>;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [SuperServerNode]
    })
    .compileComponents();

    fixture = TestBed.createComponent(SuperServerNode);
    component = fixture.componentInstance;
    await fixture.whenStable();
  });

  it('should create', () => {
    expect(component).toBeTruthy();
  });
});
