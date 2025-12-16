import { Component } from '@angular/core';
import { CommonModule } from '@angular/common';
import { Vflow, Node, Edge, CustomNodeComponent } from 'ngx-vflow';
import { SidebarComponent } from './sidebar.component/sidebar.component';
import { ClientNode } from './nodes/client-node/client-node';
import { ServerNode } from './nodes/server-node/server-node';
import { SuperServerNode } from './nodes/super-server-node/super-server-node';

@Component({
  selector: 'app-root',
  standalone: true,
  templateUrl: './app.html',
  styleUrls: ['./app.css'],
  imports: [Vflow, SidebarComponent, CommonModule],
})
export class App {
  public nodes: Node[] = [];
  public edges: Edge[] = [];

  public onDragOver(event: DragEvent) {
    event.preventDefault();
    if (event.dataTransfer) {
      event.dataTransfer.dropEffect = 'copy';
    }
  }

  public onDrop(event: DragEvent) {
    event.preventDefault();

    // 1. JSON-String auslesen
    const rawData = event.dataTransfer?.getData('application/json');
    if (!rawData) return;

    try {
      const payload = JSON.parse(rawData);
      
      // 2. Position bestimmen
      const mousePosition = {
        x: event.clientX,
        y: event.clientY,
      };

      let nodeType;
      switch (payload.type.toString()){
        case 'ClientNode':
          nodeType=ClientNode;
          break;
        case 'ServerNode':
          nodeType=ServerNode;
          break;
        case 'SuperServerNode':
          nodeType = SuperServerNode;
          break;
        default:
            console.log("yo mister white yo, there's an error")
        }
        const newNode: Node = {
          id: crypto.randomUUID(),
          point: mousePosition,
          type: nodeType,
          data: {
          type: payload.type,
          config: payload.config,
            },
          };
        this.nodes.push(newNode);
        console.log("added new node:", newNode);
      } catch {
        console.log('FUCK YOU');
    }
  } 
}