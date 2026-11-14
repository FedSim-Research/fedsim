import { HttpErrorResponse, provideHttpClient } from '@angular/common/http';
import { provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { GraphApiService, GraphDetail } from '../api/graph-api.service';
import { GraphPersistenceService } from './graph-persistence.service';
import { HierflGraphService } from './topologies/hierfl-graph.service';

describe('GraphPersistenceService', () => {
  const metrics = { pingMs: 80, jitterMs: 9, packetloss: 0.2, packetlossStddev: 0.01 };
  const detail: GraphDetail = {
    graph_id: 7,
    name: 'stored',
    architecture: 'hierfl',
    metadata: null,
    nodes: [
      { node_id: 's', graph_id: 7, type: 'ServerNode', config: {}, position: { x: 0, y: 0 } },
      { node_id: 'c', graph_id: 7, type: 'ClientNode', config: {}, position: { x: 0, y: 100 } },
    ],
    edges: [{ edge_id: 3, graph_id: 7, source_node_id: 's', target_node_id: 'c', config: metrics }],
  };

  const replaceGraphState = vi.fn().mockResolvedValue({});

  beforeEach(() => {
    localStorage.clear();
    replaceGraphState.mockClear();
    TestBed.configureTestingModule({
      providers: [
        provideHttpClient(),
        provideHttpClientTesting(),
        { provide: GraphApiService, useValue: { getGraph: vi.fn().mockResolvedValue(detail), replaceGraphState } },
      ],
    });
  });

  it('keeps stored edge metrics when loading a graph', async () => {
    const service = TestBed.inject(HierflGraphService);
    await TestBed.inject(GraphPersistenceService).loadGraph(service, 'hierfl', 7);

    expect(service.getGraphId()).toBe(7);
    expect((service.edges()[0].data as { metrics: unknown }).metrics).toEqual(metrics);
  });

  it('saves pending edits of the previous graph before switching', async () => {
    const service = TestBed.inject(HierflGraphService);
    service.setGraphId(1);
    service.addNode({ id: 'x', point: { x: 0, y: 0 }, type: 'default', data: { type: 'ClientNode', config: {} } } as never);

    await TestBed.inject(GraphPersistenceService).loadGraph(service, 'hierfl', 7);

    expect(replaceGraphState).toHaveBeenCalledWith(1, expect.objectContaining({ nodes: [expect.objectContaining({ id: 'x' })] }));
    expect(service.getGraphId()).toBe(7);
  });

  it('keeps the current graph and its edits when saving before a switch fails', async () => {
    const service = TestBed.inject(HierflGraphService);
    service.setGraphId(1);
    service.addNode({ id: 'unsaved', point: { x: 0, y: 0 }, data: { type: 'ClientNode', config: {} } } as never);
    replaceGraphState.mockRejectedValueOnce(new Error('offline'));

    await expect(TestBed.inject(GraphPersistenceService).loadGraph(service, 'hierfl', 7)).rejects.toThrow('offline');

    expect(service.getGraphId()).toBe(1);
    expect(service.nodes().map((node) => node.id)).toEqual(['unsaved']);
  });

  it('does not replace a stored graph after a temporary backend error', async () => {
    localStorage.setItem('fedsim.graphId.hierfl', '7');
    const api = TestBed.inject(GraphApiService);
    vi.spyOn(api, 'getGraph').mockRejectedValueOnce(new HttpErrorResponse({ status: 503 }));
    const createGraph = vi.fn();
    (api as unknown as { createGraph: typeof createGraph }).createGraph = createGraph;

    await expect(TestBed.inject(GraphPersistenceService).initializeGraph(
      TestBed.inject(HierflGraphService), 'hierfl',
    )).rejects.toBeInstanceOf(HttpErrorResponse);

    expect(createGraph).not.toHaveBeenCalled();
    expect(localStorage.getItem('fedsim.graphId.hierfl')).toBe('7');
  });

  it('keeps the most recently requested graph when responses arrive out of order', async () => {
    const api = TestBed.inject(GraphApiService);
    let finishOlder!: (graph: GraphDetail) => void;
    vi.spyOn(api, 'getGraph')
      .mockImplementationOnce(() => new Promise((resolve) => { finishOlder = resolve; }))
      .mockResolvedValueOnce({ ...detail, graph_id: 8, nodes: [], edges: [] });
    const service = TestBed.inject(HierflGraphService);
    const persistence = TestBed.inject(GraphPersistenceService);
    const older = persistence.loadGraph(service, 'hierfl', 7);
    await Promise.resolve();
    await Promise.resolve();
    const newer = persistence.loadGraph(service, 'hierfl', 8);
    await newer;
    finishOlder(detail);
    await older;

    expect(service.getGraphId()).toBe(8);
    expect(service.nodes()).toEqual([]);
  });

  it('creates a replacement only when the stored graph no longer exists', async () => {
    localStorage.setItem('fedsim.graphId.hierfl', '7');
    const api = TestBed.inject(GraphApiService);
    vi.spyOn(api, 'getGraph').mockRejectedValueOnce(new HttpErrorResponse({ status: 404 }));
    const createGraph = vi.fn().mockResolvedValue({ graph_id: 9 });
    (api as unknown as { createGraph: typeof createGraph }).createGraph = createGraph;
    const service = TestBed.inject(HierflGraphService);
    await TestBed.inject(GraphPersistenceService).initializeGraph(service, 'hierfl');
    expect(createGraph).toHaveBeenCalledTimes(1);
    expect(service.getGraphId()).toBe(9);
  });

  it('does not restore a graph after its workspace was detached during a fetch', async () => {
    let finish!: (graph: GraphDetail) => void;
    const api = TestBed.inject(GraphApiService);
    vi.spyOn(api, 'getGraph').mockImplementationOnce(() => new Promise((resolve) => { finish = resolve; }));
    const service = TestBed.inject(HierflGraphService);
    service.setGraphId(1);
    const pending = TestBed.inject(GraphPersistenceService).loadGraph(service, 'hierfl', 7);
    await vi.waitFor(() => expect(api.getGraph).toHaveBeenCalled());
    service.detachGraph();
    finish(detail);
    await pending;
    expect(service.getGraphId()).toBeNull();
    expect(service.nodes()).toEqual([]);
  });

  it('preserves edits made while reloading the same graph', async () => {
    let finish!: (graph: GraphDetail) => void;
    const api = TestBed.inject(GraphApiService);
    vi.spyOn(api, 'getGraph').mockImplementationOnce(() => new Promise((resolve) => { finish = resolve; }));
    const service = TestBed.inject(HierflGraphService);
    service.setGraphId(7);
    service.loadContents([{ id: 's', point: { x: 0, y: 0 }, data: { type: 'ServerNode', config: {} } } as never], []);
    const pending = TestBed.inject(GraphPersistenceService).loadGraph(service, 'hierfl', 7);
    await vi.waitFor(() => expect(api.getGraph).toHaveBeenCalled());
    service.updateNodeConfig('s', { name: 'latest edit' });
    finish(detail);
    await pending;
    expect((service.nodes()[0] as unknown as { data: { config: { name: string } } }).data.config.name).toBe('latest edit');
    expect(replaceGraphState).toHaveBeenCalledWith(7, expect.objectContaining({
      nodes: [expect.objectContaining({ data: expect.objectContaining({ config: { name: 'latest edit' } }) })],
    }));
  });
});
