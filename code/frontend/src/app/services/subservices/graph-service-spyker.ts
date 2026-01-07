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

  public override addNode(newNode: Node) {
    this.nodes.update((nodes) => [...nodes, newNode]);
    this.persistCreateNode(newNode);

    if (newNode.type !== ServerNode) {
      this.graphHistory.saveState({ nodes: this.nodes(), edges: this.edges() });
      return;
    }

    const servers = this.nodes().filter((n) => n.id !== newNode.id && n.type === ServerNode);
    for (const s of servers) {
      const exists = this.edges().some(
        (e) =>
          (e.source === s.id && e.target === newNode.id) ||
          (e.source === newNode.id && e.target === s.id)
      );
      if (!exists){
      super.addEdge({id: crypto.randomUUID(),
            source: s.id,
            target: newNode.id,
            reconnectable: true,
            floating: false,})}
      }

    this.graphHistory.saveState({ nodes: this.nodes(), edges: this.edges() });
  }
  
}
