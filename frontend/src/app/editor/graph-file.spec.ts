import { StaticEdge, StaticNode } from 'ngx-vflow';
import { parseGraphFile, toGraphFile } from './graph-file';

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

describe('parseGraphFile', () => {
  let counter = 0;
  const createId = () => `new-${++counter}`;
  beforeEach(() => (counter = 0));

  it('assigns fresh ids and drops backend ids from legacy exports', () => {
    const legacy = {
      nodes: [
        { id: 'old-s', point: { x: 1, y: 2 }, data: { type: 'ServerNode', config: { name: 'S' }, backendId: 'old-s' } },
        { id: 'old-c', point: { x: 3, y: 4 }, data: { type: 'ClientNode', config: {}, backendId: 'old-c' } },
      ],
      edges: [{ id: '17', source: 'old-s', target: 'old-c', data: { backendId: 17, metrics: { pingMs: 9 } } }],
    };

    const graph = parseGraphFile(legacy, createId);

    expect(graph.nodes.map((n) => n.id)).toEqual(['new-1', 'new-2']);
    expect(graph.edges[0]).toMatchObject({ id: 'new-3', source: 'new-1', target: 'new-2' });
    expect(graph.edges[0].metrics.pingMs).toBe(9);
    expect(JSON.stringify(graph)).not.toContain('backendId');
  });

  it('round-trips an export', () => {
    const exported = toGraphFile('hierfl', [
      { id: 'a', point: { x: 0, y: 0 }, type: 'default', data: { type: 'ClientNode', config: { count: 3 } } },
    ] as unknown as StaticNode[], []);
    expect(parseGraphFile(JSON.parse(JSON.stringify(exported)), createId).nodes[0]).toEqual({
      id: 'new-1', point: { x: 0, y: 0 }, kind: 'ClientNode', config: { count: 3 },
    });
  });

  it.each([
    [{}, 'node list'],
    [{ nodes: [{ data: { type: 'Laptop' } }] }, 'unknown type'],
    [{ nodes: [], edges: [{ source: 'x', target: 'y' }] }, 'missing node'],
  ])('rejects malformed files (%#)', (raw, message) => {
    expect(() => parseGraphFile(raw, createId)).toThrow(message);
  });
});
