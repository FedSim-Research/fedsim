import { Injectable, inject } from '@angular/core';
import { GraphService } from '../graph-service';
import { Edge, Node } from 'ngx-vflow';
import { SuperServerNode } from '../../components/nodes/super-server-node/super-server-node';
import { GraphHistoryServiceHierach } from './graph-history-service-hierach';
import { State } from '../graph-history.service';

@Injectable({
  providedIn: 'root',
})
export class GraphServiceHierach extends GraphService<GraphHistoryServiceHierach>{
  private hasSuperServer = false;  

  constructor(graphHistory: GraphHistoryServiceHierach){
    super(graphHistory, 'hierfl');
  }

  public override addNode(newNode: Node): void {
    if (newNode.type==SuperServerNode){
      if (this.hasSuperServer){
        // error toast
        console.warn('Block: SuperServer already exists')
        return;
      }
      this.hasSuperServer = true;
    }
    super.addNode(newNode);
  } 

  public override removeNodeById(nodeId: String): void {
    const node = this.nodes().find((n) => n.id === nodeId);
    if (node?.type === SuperServerNode) {
      this.hasSuperServer = false;
    }
    super.removeNodeById(nodeId);
  }

  protected override onStateApplied(state: State): void {
    this.hasSuperServer = state.nodes.some((node) => node.type === SuperServerNode);
  }
}
