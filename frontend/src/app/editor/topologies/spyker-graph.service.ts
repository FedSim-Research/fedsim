import { Injectable } from '@angular/core';
import { GraphService } from '../graph.service';
import { SpykerGraphHistoryService } from './spyker-graph-history.service';
import { Node } from 'ngx-vflow';
import { ServerNode } from '../nodes/server-node/server-node';
import { v4 as uuidv4 } from 'uuid';

@Injectable({
  providedIn: 'root',
})
export class SpykerGraphService extends GraphService<SpykerGraphHistoryService> {
  constructor(graphHistory: SpykerGraphHistoryService) {
    super(graphHistory, 'spyker');
  }

  public override addNode(newNode: Node): void {
    super.addNode(newNode);
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
      super.addEdge({id: uuidv4(),
            source: s.id,
            target: newNode.id,
            reconnectable: true,
            floating: false,})}
      }

    this.graphHistory.saveState({ nodes: this.nodes(), edges: this.edges() });
  }

}
