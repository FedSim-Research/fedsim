import { provideHttpClient } from '@angular/common/http';
import { provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { StaticNode } from 'ngx-vflow';
import { ClientNode } from './nodes/client-node/client-node';
import { SuperServerNode } from './nodes/super-server-node/super-server-node';
import { createGraphNode } from './nodes/node-factory';
import { NodeKind } from '../domain/topology';
import { HierflGraphService } from './topologies/hierfl-graph.service';
import { GraphApiService } from '../api/graph-api.service';

describe('GraphService', () => {
  let service: HierflGraphService;

  function node(id: string, kind: NodeKind): StaticNode {
    return createGraphNode({ id, kind, architecture: 'hierfl', point: { x: 0, y: 0 }, config: {} });
  }

  beforeEach(() => {
    TestBed.configureTestingModule({ providers: [provideHttpClient(), provideHttpClientTesting()] });
    service = TestBed.inject(HierflGraphService);
    service.addNode(node('server', 'ServerNode'));
    service.addNode(node('client-a', 'ClientNode'));
    service.addNode(node('client-b', 'ClientNode'));
    service.addEdge({ id: 'e1', source: 'server', target: 'client-a' });
    service.addEdge({ id: 'e2', source: 'server', target: 'client-b' });
  });

  it('selects nodes and edges without touching history', () => {
    service.setSelection(new Set(['server']), new Set(['e1']));

    expect(service.nodes().map((n) => Boolean((n as { data?: { selected?: boolean } }).data?.selected))).toEqual([true, false, false]);
    expect(service.edges().map((e) => Boolean((e as { data?: { selected?: boolean } }).data?.selected))).toEqual([true, false]);

    const nodes = service.nodes();
    service.setSelection(new Set(['server']), new Set(['e1']));
    expect(service.nodes()).toBe(nodes);

    // Undo skips the selection and takes back the last real edit.
    service.undo();
    expect(service.edges().map((e) => e.id)).toEqual(['e1']);
  });

  it('removes nodes with their attached edges as one undo step', () => {
    service.removeEntities(['client-a'], ['e2']);

    expect(service.nodes().map((n) => n.id)).toEqual(['server', 'client-b']);
    expect(service.edges()).toEqual([]);

    service.undo();
    expect(service.nodes()).toHaveLength(3);
    expect(service.edges().map((e) => e.id)).toEqual(['e1', 'e2']);
  });

  it('allows a new super server once the previous one was removed', () => {
    service.addNode(node('super-1', 'SuperServerNode'));
    expect(service.addNode(node('super-2', 'SuperServerNode'))).toContain('Only one Super Server');
    expect(service.nodes().filter((n) => n.type === SuperServerNode)).toHaveLength(1);

    service.removeNodeById('super-1');
    service.addNode(node('super-2', 'SuperServerNode'));
    expect(service.nodes().map((n) => n.id)).toContain('super-2');
  });
});

describe('GraphService saving', () => {
  const replaceGraphState = vi.fn();
  let service: HierflGraphService;

  function node(id: string): StaticNode {
    return { id, point: { x: 0, y: 0 }, type: ClientNode, data: { type: 'ClientNode', config: {} } } as StaticNode;
  }

  beforeEach(() => {
    vi.useFakeTimers();
    localStorage.clear();
    replaceGraphState.mockReset().mockResolvedValue({});
    TestBed.configureTestingModule({
      providers: [{ provide: GraphApiService, useValue: { replaceGraphState } }],
    });
    service = TestBed.inject(HierflGraphService);
    service.setGraphId(5);
  });

  afterEach(() => vi.useRealTimers());

  it('writes a burst of edits as one state request with editor ids', async () => {
    service.addNode(node('a'));
    service.addNode(node('b'));
    service.removeNodeById('a');
    await vi.runAllTimersAsync();

    expect(replaceGraphState).toHaveBeenCalledTimes(1);
    const [graphId, payload] = replaceGraphState.mock.calls[0];
    expect(graphId).toBe(5);
    expect(payload.nodes.map((n: { id: string }) => n.id)).toEqual(['b']);
  });

  it('resets by clearing the graph instead of replacing it', async () => {
    service.addNode(node('a'));
    service.resetGraph();
    await vi.runAllTimersAsync();

    expect(service.getGraphId()).toBe(5);
    expect(replaceGraphState).toHaveBeenLastCalledWith(5, { nodes: [], edges: [] });
    expect(service.undo()).toBe(true);
    expect(service.nodes().map((n) => n.id)).toEqual(['a']);
  });

  it('retries a failed save with the next edit', async () => {
    replaceGraphState.mockRejectedValueOnce(new Error('offline'));
    service.addNode(node('a'));
    await vi.runAllTimersAsync();
    service.updateNodeConfig('a', { count: 2 });
    await vi.runAllTimersAsync();

    expect(replaceGraphState).toHaveBeenCalledTimes(2);
    expect(replaceGraphState.mock.calls[1][1].nodes[0].data.config).toEqual({ count: 2 });
  });

  it('reports an explicit save failure and allows a later retry', async () => {
    replaceGraphState.mockRejectedValueOnce(new Error('offline'));
    service.addNode(node('a'));

    await expect(service.flushSave()).rejects.toThrow('offline');
    await service.flushSave();

    expect(replaceGraphState).toHaveBeenCalledTimes(2);
    expect(replaceGraphState.mock.calls[1][1].nodes[0].id).toBe('a');
  });

  it('flushes edits made while a state request is in flight', async () => {
    let finishFirst!: () => void;
    replaceGraphState.mockImplementationOnce(() => new Promise<void>((resolve) => { finishFirst = resolve; }));
    service.addNode(node('a'));
    const saved = service.flushSave();
    await Promise.resolve();
    service.updateNodeConfig('a', { count: 7 });
    finishFirst();
    await saved;

    expect(replaceGraphState).toHaveBeenCalledTimes(2);
    expect(replaceGraphState.mock.calls[1][1].nodes[0].data.config.count).toBe(7);
  });
});

describe('GraphService undo', () => {
  it('saves the restored state through the regular save queue', async () => {
    vi.useFakeTimers();
    const replaceGraphState = vi.fn().mockResolvedValue({});
    TestBed.configureTestingModule({ providers: [{ provide: GraphApiService, useValue: { replaceGraphState } }] });
    const service = TestBed.inject(HierflGraphService);
    service.setGraphId(5);
    service.addNode({ id: 'a', point: { x: 0, y: 0 }, type: ClientNode, data: { type: 'ClientNode', config: {} } } as StaticNode);
    await vi.runAllTimersAsync();

    expect(service.undo()).toBe(true);
    expect(service.undo()).toBe(false);
    await vi.runAllTimersAsync();

    expect(replaceGraphState).toHaveBeenCalledTimes(2);
    expect(replaceGraphState.mock.calls[1][1].nodes).toEqual([]);
    vi.useRealTimers();
  });
});

describe('GraphService detachGraph', () => {
  it('drops pending saves for a graph that no longer exists', async () => {
    vi.useFakeTimers();
    localStorage.clear();
    const replaceGraphState = vi.fn().mockResolvedValue({});
    TestBed.configureTestingModule({ providers: [{ provide: GraphApiService, useValue: { replaceGraphState } }] });
    const service = TestBed.inject(HierflGraphService);
    service.setGraphId(5);
    service.addNode({ id: 'a', point: { x: 0, y: 0 }, type: ClientNode, data: { type: 'ClientNode', config: {} } } as StaticNode);

    service.detachGraph();
    await vi.runAllTimersAsync();

    expect(replaceGraphState).not.toHaveBeenCalled();
    expect(service.getGraphId()).toBeNull();
    expect(service.nodes()).toEqual([]);
    vi.useRealTimers();
  });
});
