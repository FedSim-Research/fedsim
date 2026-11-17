import { MessageService } from 'primeng/api';
import { signal } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { ɵComponentEventBusService, ɵNodeAccessorService } from 'ngx-vflow';
import { ClientNode } from './client-node/client-node';
import { createGraphNode } from './node-factory';

describe('createGraphNode', () => {
  it('stores canvas points as plain coordinates', () => {
    // Like DOMPoint: coordinates are prototype getters, invisible to spreading.
    class CanvasPoint {
      get x() { return 12; }
      get y() { return 34; }
    }
    const node = createGraphNode({ id: 'n', kind: 'ClientNode', architecture: 'hierfl', point: new CanvasPoint(), config: {} });

    expect({ ...node.point }).toEqual({ x: 12, y: 34 });
    expect(JSON.parse(JSON.stringify(node.point))).toEqual({ x: 12, y: 34 });
  });
});

describe('node architecture', () => {
  it('resolves a HierFL node to hierfl', () => {
    // ngx-vflow hands the component a dynamic node whose data is a signal.
    TestBed.configureTestingModule({
      providers: [
        MessageService,
        ɵComponentEventBusService,
        { provide: ɵNodeAccessorService, useValue: { model: () => ({ selected: signal(false), preselected: signal(false) }) } },
      ],
    });
    TestBed.overrideComponent(ClientNode, { set: { template: '', imports: [] } }); // only the logic is under test
    const node = createGraphNode({ id: 'n', kind: 'ClientNode', architecture: 'hierfl', point: { x: 0, y: 0 }, config: {} });
    const fixture = TestBed.createComponent(ClientNode);
    fixture.componentRef.setInput('node', { ...node, data: signal((node as { data: unknown }).data) });

    expect(fixture.componentInstance.environment()).toBe('hierfl');
  });
});
