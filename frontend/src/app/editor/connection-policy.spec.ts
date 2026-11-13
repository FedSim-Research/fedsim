import { StaticEdge, StaticNode } from 'ngx-vflow';
import { canConnect, normalizeConnection, orientServerLinks } from './connection-policy';

function node(id: string, type: string, x = 0): StaticNode {
  return { id, point: { x, y: 0 }, type: 'default', data: { type } } as unknown as StaticNode;
}

const nodes = [
  node('super', 'SuperServerNode'),
  node('left', 'ServerNode', 0),
  node('right', 'ServerNode', 100),
  node('client', 'ClientNode'),
];

describe('canConnect', () => {
  it('allows a free client to join a server', () => {
    expect(canConnect('hierfl', nodes, [], { source: 'client', target: 'left' })).toBe(true);
  });

  it('keeps clients attached to a single server', () => {
    const edges = [{ id: 'e', source: 'left', target: 'client' }] as StaticEdge[];
    expect(canConnect('hierfl', nodes, edges, { source: 'client', target: 'right' })).toBe(false);
  });

  it('rejects duplicate links in either direction', () => {
    const edges = [{ id: 'e', source: 'super', target: 'left' }] as StaticEdge[];
    expect(canConnect('hierfl', nodes, edges, { source: 'left', target: 'super' })).toBe(false);
  });

  it('keeps the client handle free of peer server links', () => {
    const viaClientHandle = { source: 'left', target: 'right', sourceHandle: 'server-out-bottom' };
    expect(canConnect('spyker', nodes, [], viaClientHandle)).toBe(false);
    expect(canConnect('spyker', nodes, [], { source: 'left', target: 'right' })).toBe(true);
  });

  it('applies the architecture link rules', () => {
    expect(canConnect('spyker', nodes, [], { source: 'super', target: 'left' })).toBe(false);
    expect(canConnect('hierfl', nodes, [], { source: 'left', target: 'right' })).toBe(false);
  });
});

describe('normalizeConnection', () => {
  it.each([
    [{ source: 'left', target: 'super' }, { source: 'super', target: 'left', sourceHandle: 'superserver-out', targetHandle: 'server-in-top' }],
    [{ source: 'client', target: 'left' }, { source: 'left', target: 'client', sourceHandle: 'server-out-bottom', targetHandle: 'client-in' }],
    [{ source: 'right', target: 'left' }, { source: 'left', target: 'right', sourceHandle: 'server-out', targetHandle: 'server-in' }],
  ])('orients %o', (connection, expected) => {
    expect(normalizeConnection(nodes, connection)).toEqual(expected);
  });
});

describe('orientServerLinks', () => {
  it('flips server links after the servers swapped sides', () => {
    const edges = [{ id: 'e', source: 'left', target: 'right', sourceHandle: 'server-out', targetHandle: 'server-in' }] as StaticEdge[];
    const moved = [node('left', 'ServerNode', 200), node('right', 'ServerNode', 0)];
    expect(orientServerLinks(moved, edges)[0]).toMatchObject({ source: 'right', target: 'left' });
    expect(orientServerLinks(nodes, edges)).toBe(edges);
  });
});
