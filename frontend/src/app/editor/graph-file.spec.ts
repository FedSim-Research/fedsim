import { StaticEdge, StaticNode } from 'ngx-vflow';
import { toGraphFile } from './graph-file';

describe('toGraphFile', () => {
  it('exports topology and config without backend ids or view state', () => {
    const nodes = [{
      id: 'n1', point: { x: 1, y: 2 }, type: 'default',
      data: { type: 'ServerNode', config: { name: 'S' }, backendId: 'n1', selected: true, environment: 'hierfl' },
    }] as unknown as StaticNode[];
    const edges = [{
      id: '42', source: 'n1', target: 'n2',
      data: { backendId: 42, selected: true, metrics: { pingMs: 5, jitterMs: 1, packetloss: 0, packetlossStddev: 0 } },
    }] as unknown as StaticEdge[];

    const file = toGraphFile('hierfl', nodes, edges);

    expect(file.nodes[0]).toEqual({ id: 'n1', point: { x: 1, y: 2 }, data: { type: 'ServerNode', config: { name: 'S' } } });
    expect(file.edges[0].data).toEqual({ metrics: { pingMs: 5, jitterMs: 1, packetloss: 0, packetlossStddev: 0 } });
    expect(JSON.stringify(file)).not.toContain('backendId');
  });
});
