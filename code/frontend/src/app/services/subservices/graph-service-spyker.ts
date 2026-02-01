import { Injectable } from '@angular/core';
import { GraphService } from '../graph-service';
import { GraphHistoryServiceSpyker } from './graph-history-service-spyker';
import { Node } from 'ngx-vflow';
import { ServerNode } from '../../components/nodes/server-node/server-node';

@Injectable({
  providedIn: 'root',
})
export class GraphServiceSpyker extends GraphService<GraphHistoryServiceSpyker> {
  constructor(graphHistory: GraphHistoryServiceSpyker) {
    super(graphHistory, 'spyker');
  }

  public override addNode(newNode: Node): void {
    const resolvedNode = this.normalizeNodeId(newNode);
    this.nodes.update((nodes) => [...nodes, resolvedNode]);
    this.persistCreateNode(resolvedNode);
    this.graphHistory.saveState({ nodes: this.nodes(), edges: this.edges() });
  }
  
}
