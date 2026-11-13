import { Injectable } from '@angular/core';
import { GraphService } from '../graph.service';
import { SpykerGraphHistoryService } from './spyker-graph-history.service';
import { StaticEdge as Edge, StaticNode as Node } from 'ngx-vflow';
import { ServerNode } from '../nodes/server-node/server-node';
import { v4 as uuidv4 } from 'uuid';

@Injectable({
  providedIn: 'root',
})
export class SpykerGraphService extends GraphService<SpykerGraphHistoryService> {
  constructor(graphHistory: SpykerGraphHistoryService) {
    super(graphHistory, 'spyker');
  }

  /** Spyker servers form a full mesh, so a new server is linked to every existing one. */
  public override addNode(newNode: Node): void {
    const meshEdges = newNode.type === ServerNode ? this.meshEdgesFor(newNode.id) : [];
    this.addEntities([newNode], meshEdges);
  }

  private meshEdgesFor(serverId: string): Edge[] {
    return this.nodes()
      .filter((node) => node.type === ServerNode && node.id !== serverId)
      .map((server) => ({
        id: uuidv4(),
        source: server.id,
        target: serverId,
        reconnectable: true,
        floating: false,
      }));
  }
}
