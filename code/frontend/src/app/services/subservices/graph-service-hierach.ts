import { Injectable, inject } from '@angular/core';
import { GraphService } from '../graph-service';
import { Edge, Node } from 'ngx-vflow';
import { SuperServerNode } from '../../components/nodes/super-server-node/super-server-node';
import { GraphHistoryServiceHierach } from './graph-history-service-hierach';

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
    this.nodes.update((nodes) => [...nodes, newNode]);
    this.persistCreateNode(newNode);
    this.graphHistory.saveState({nodes: this.nodes(), edges: this.edges()});
  } 
}
