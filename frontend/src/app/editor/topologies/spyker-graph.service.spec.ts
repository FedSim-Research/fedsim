import { provideHttpClient } from '@angular/common/http';
import { provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { StaticNode } from 'ngx-vflow';
import { createGraphNode } from '../nodes/node-factory';
import { SpykerGraphService } from './spyker-graph.service';

describe('SpykerGraphService', () => {
  let service: SpykerGraphService;

  function server(id: string): StaticNode {
    return createGraphNode({ id, kind: 'ServerNode', architecture: 'spyker', point: { x: 0, y: 0 }, config: {} });
  }

  beforeEach(() => {
    TestBed.configureTestingModule({ providers: [provideHttpClient(), provideHttpClientTesting()] });
    service = TestBed.inject(SpykerGraphService);
  });

  it('links a new server to every existing server', () => {
    service.addNode(server('a'));
    service.addNode(server('b'));
    service.addNode(server('c'));

    const pairs = service.edges().map((edge) => `${edge.source}->${edge.target}`);
    expect(pairs).toEqual(['a->b', 'a->c', 'b->c']);
  });

  it('links pasted servers with each other and with existing ones', () => {
    service.addNode(server('a'));
    service.addEntities([server('b'), server('c')], []);

    const pairs = service.edges().map((edge) => `${edge.source}->${edge.target}`);
    expect(pairs).toEqual(['a->b', 'a->c', 'b->c']);
  });

  it('undoes a server and its mesh edges in a single step', () => {
    service.addNode(server('a'));
    service.addNode(server('b'));

    const history = service.getGraphHistory();
    history.undo();
    service.applyHistoryState(history.getState());

    expect(service.nodes().map((node) => node.id)).toEqual(['a']);
    expect(service.edges()).toEqual([]);
  });
});
