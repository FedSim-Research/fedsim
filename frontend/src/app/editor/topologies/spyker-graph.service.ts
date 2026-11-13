import { Injectable } from '@angular/core';
import { StaticEdge as Edge, StaticNode as Node } from 'ngx-vflow';
import { v4 as uuidv4 } from 'uuid';
import { GraphService } from '../graph.service';
import { SpykerGraphHistoryService } from './spyker-graph-history.service';

@Injectable({
  providedIn: 'root',
})
export class SpykerGraphService extends GraphService<SpykerGraphHistoryService> {
  constructor(graphHistory: SpykerGraphHistoryService) {
    super(graphHistory, 'spyker');
  }

  /** Spyker servers form a full mesh, so every new server is linked to every other one. */
  protected override linksForNewNodes(newNodes: Node[]): Edge[] {
    const isServer = (node: Node) => (node as { data?: { type?: string } }).data?.type === 'ServerNode';
    const newServers = newNodes.filter(isServer);
    const peers = [...this.nodes().filter(isServer), ...newServers];
    return newServers.flatMap((server) =>
      peers
        .slice(0, peers.indexOf(server))
        .map((peer) => ({ id: uuidv4(), source: peer.id, target: server.id, reconnectable: true, floating: false })),
    );
  }
}
