import { StaticEdge, StaticNode } from 'ngx-vflow';
import { computed, signal } from '@angular/core';
import { FlowRenderer } from './flow-renderer';

describe('FlowRenderer', () => {
  it('preserves a drag position while node data changes', () => {
    const renderer = new FlowRenderer();
    const input: StaticNode<any> = {
      id: 'client', type: 'html-template', point: { x: 10, y: 20 },
      data: { config: { name: 'Before' } },
    };
    const inputs = signal([input]);
    const renderedNodes = computed(() => renderer.nodes(inputs()));
    const rendered = renderedNodes()[0];
    rendered.point.set({ x: 50, y: 60 });
    expect(input.point).toEqual({ x: 10, y: 20 });
    const updated = { ...input, data: { config: { name: 'After' } } };

    inputs.set([updated]);
    expect(renderedNodes()[0]).toBe(rendered);
    expect(rendered.point()).toEqual({ x: 50, y: 60 });
    expect('data' in rendered && rendered.data?.()).toEqual(updated.data);

    inputs.set([{ ...updated, point: { x: 100, y: 200 } }]);
    renderedNodes();
    expect(rendered.point()).toEqual({ x: 100, y: 200 });
  });

  it('updates edge signals without replacing the rendered edge', () => {
    const renderer = new FlowRenderer();
    const input: StaticEdge<any> = {
      id: 'link', source: 'server', target: 'client', data: { latency: 10 }, selected: false,
    };
    const rendered = renderer.edges([input])[0];
    const updated = { ...input, data: { latency: 20 }, selected: true };

    expect(renderer.edges([updated])[0]).toBe(rendered);
    expect(rendered.data?.()).toEqual({ latency: 20 });
    expect(rendered.selected?.()).toBe(true);
    rendered.selected?.set(false);
    expect(updated.selected).toBe(true);
  });

  it('discards removed nodes before reusing their IDs', () => {
    const renderer = new FlowRenderer();
    const input: StaticNode = { id: 'node', type: 'default', point: { x: 0, y: 0 } };
    const first = renderer.nodes([input])[0];
    expect(renderer.nodes([])).toEqual([]);
    expect(renderer.nodes([input])[0]).not.toBe(first);
  });
});
