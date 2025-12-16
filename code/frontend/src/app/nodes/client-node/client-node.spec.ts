import { ComponentFixture, TestBed } from '@angular/core/testing';

import { ClientNode } from './client-node';

describe('ClientNode', () => {
  let component: ClientNode;
  let fixture: ComponentFixture<ClientNode>;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [ClientNode]
    })
    .compileComponents();

    fixture = TestBed.createComponent(ClientNode);
    component = fixture.componentInstance;
    await fixture.whenStable();
  });

  it('should create', () => {
    expect(component).toBeTruthy();
  });
});
