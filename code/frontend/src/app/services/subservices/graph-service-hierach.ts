import { Injectable } from '@angular/core';
import { GraphService } from '../graph-service';
import { Edge, Node } from 'ngx-vflow';
import { SuperServerNode } from '../../components/nodes/super-server-node/super-server-node';

@Injectable({
  providedIn: 'root',
})
export class GraphServiceHierach extends GraphService{
  private hasSuperServer = false;  

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
  } 
}
