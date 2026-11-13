import { provideHttpClient } from '@angular/common/http';
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

  beforeEach(() => {
    localStorage.clear();
    TestBed.configureTestingModule({
      providers: [
        provideHttpClient(),
        provideHttpClientTesting(),
        { provide: GraphApiService, useValue: { getGraph: vi.fn().mockResolvedValue(detail) } },
      ],
    });
  });

  it('keeps stored edge metrics when loading a graph', async () => {
    const service = TestBed.inject(HierflGraphService);
    await TestBed.inject(GraphPersistenceService).loadGraph(service, 'hierfl', 7);

    expect(service.getGraphId()).toBe(7);
    expect((service.edges()[0].data as { metrics: unknown }).metrics).toEqual(metrics);
  });
});
