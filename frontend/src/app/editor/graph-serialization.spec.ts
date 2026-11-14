import { StaticEdge, StaticNode } from 'ngx-vflow';
import { toVflowGraph } from './graph-serialization';

describe('toVflowGraph', () => {
  const nodes = [
    { id: 's', point: { x: 1, y: 2 }, type: 'default', data: { type: 'ServerNode', config: { name: 'S' }, selected: true, backendId: 's' } },
    { id: 'c', point: { x: 3, y: 4 }, type: 'default', data: { type: 'ClientNode', config: {} } },
  ] as unknown as StaticNode[];

  it('sends config and metrics without view state', () => {
    const edges = [{ id: 'e', source: 's', target: 'c', data: { metrics: { pingMs: 4.4 }, selected: true } }] as StaticEdge[];
    const graph = toVflowGraph('hierfl', nodes, edges);

    expect(graph.nodes[0]).toEqual({
      id: 's', point: { x: 1, y: 2 }, type: 'ServerNode',
      data: { type: 'ServerNode', config: { name: 'S' }, environment: 'hierfl', fromJson: true, selected: false },
    });
    expect(graph.edges[0].config?.pingMs).toBe(4);
  });

  it('drops edges whose nodes are not part of the payload', () => {
    const edges = [{ id: 'e', source: 's', target: 'gone' }] as StaticEdge[];
    expect(toVflowGraph('hierfl', nodes, edges).edges).toEqual([]);
  });
});
