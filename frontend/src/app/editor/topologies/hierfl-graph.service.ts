import { Injectable } from '@angular/core';
import { GraphService } from '../graph.service';
import { StaticNode as Node } from 'ngx-vflow';
import { SuperServerNode } from '../nodes/super-server-node/super-server-node';
import { HierflGraphHistoryService } from './hierfl-graph-history.service';

@Injectable({
  providedIn: 'root',
})
export class HierflGraphService extends GraphService<HierflGraphHistoryService> {
  constructor(graphHistory: HierflGraphHistoryService) {
    super(graphHistory, 'hierfl');
  }

  public override addNode(newNode: Node): void {
    if (newNode.type === SuperServerNode && this.hasSuperServer()) {
      console.warn('Block: SuperServer already exists');
      return;
    }
    super.addNode(newNode);
  }

  private hasSuperServer(): boolean {
    return this.nodes().some((node) => node.type === SuperServerNode);
  }
}
