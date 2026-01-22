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

    if (resolvedNode.type !== ServerNode) {
      this.graphHistory.saveState({ nodes: this.nodes(), edges: this.edges() });
      return;
    }

    const servers = this.nodes().filter((n) => n.id !== resolvedNode.id && n.type === ServerNode);
    for (const s of servers) {
      const exists = this.edges().some(
        (e) =>
          (e.source === s.id && e.target === resolvedNode.id) ||
          (e.source === resolvedNode.id && e.target === s.id)
      );
      if (!exists){
      super.addEdge({id: crypto.randomUUID(),
            source: s.id,
            target: resolvedNode.id,
            reconnectable: true,
            floating: false,})}
      }

    this.graphHistory.saveState({ nodes: this.nodes(), edges: this.edges() });
  }
  
}
