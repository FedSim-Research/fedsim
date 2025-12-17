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
  private alreadyHasSuperServer = false;

  private history: Node[][] = []; 
  private historyIndex = 0;

  constructor() {
    this.saveHistory();
  }

  private saveHistory() {
    if (this.historyIndex < this.history.length - 1) {
      this.history = this.history.slice(0, this.historyIndex + 1);
    }
    
    this.history.push([...this.nodes]);
    this.historyIndex++;
    
    if (this.history.length > 20) {
      this.history.shift();
      this.historyIndex--;
    }
  }

  public undo() {
    if (this.historyIndex > 0) {
      this.historyIndex--;
      this.nodes = [...this.history[this.historyIndex]];
      this.updateSuperServerStatus();
    }
  }

  public redo() {
    if (this.historyIndex < this.history.length - 1) {
      this.historyIndex++;
      this.nodes = [...this.history[this.historyIndex]];
      this.updateSuperServerStatus();
    }
  }

  private updateSuperServerStatus() {
    this.alreadyHasSuperServer = this.nodes.some(n => (n as any).data?.type === 'SuperServerNode');
  }

  public handleReset() {
    this.nodes = [];
    this.edges = [];
    this.alreadyHasSuperServer = false;
    this.saveHistory();
  }
  
  public onDragOver(event: DragEvent) {
    event.preventDefault();
    if (event.dataTransfer) {
      event.dataTransfer.dropEffect = 'copy';
    }
  }

  public onDrop(event: DragEvent) {
    event.preventDefault();

    const rawData = event.dataTransfer?.getData('application/json');
    if (!rawData) return;

    try {
      const payload = JSON.parse(rawData);

      const mousePosition = {
        x: event.clientX,
        y: event.clientY,
      };

      let nodeType;
      switch (payload.type.toString()) {
        case 'ClientNode':
          nodeType = ClientNode;
          break;
        case 'ServerNode':
          nodeType = ServerNode;
          break;
        case 'SuperServerNode':
          nodeType = SuperServerNode;
          if (this.alreadyHasSuperServer) {
            console.warn('Block: SuperServer already exists (found by text content).');
            event.preventDefault();
            event.stopPropagation();
            return;
          } else {
            this.alreadyHasSuperServer = true;
          }
          break;
        default:
          console.log("this is the default case")
          return;
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
      this.nodes = [...this.nodes, newNode];
      this.saveHistory();
      console.log("added new node:", newNode);
    } catch (e) {
      console.log('Catched', e);
    }
  }
}