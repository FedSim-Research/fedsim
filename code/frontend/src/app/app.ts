import { Component, DestroyRef } from '@angular/core';
import { CommonModule } from '@angular/common';
import { Vflow, Node, Edge } from 'ngx-vflow';
import { SidebarComponent } from './components/sidebar.component/sidebar.component';
import { ClientNode } from './components/nodes/client-node/client-node';
import { ServerNode } from './components/nodes/server-node/server-node';
import { SuperServerNode } from './components/nodes/super-server-node/super-server-node';
import { NodeDeleteUiService } from './services/node-delete-ui.service';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';

@Component({
  selector: 'app-root',
  standalone: true,
  templateUrl: './app.html',
  styleUrls: ['./app.css'],
  imports: [Vflow, SidebarComponent, CommonModule],
})
export class App {
  public activeMode: 'spyker' | 'hierfl' = 'hierfl';
  public nodes: Node[] = [];
  public edges: Edge[] = [];
  private alreadyHasSuperServer = false;

  private graphsByMode: Record<'spyker' | 'hierfl', { nodes: Node[]; edges: Edge[] }> = {
    spyker: { nodes: [], edges: [] },
    hierfl: { nodes: [], edges: [] },
  };

  private historyByMode: Record<'spyker' | 'hierfl', Node[][]> = {
    spyker: [],
    hierfl: [],
  };
  private historyIndexByMode: Record<'spyker' | 'hierfl', number> = {
    spyker: 0,
    hierfl: 0,
  };

  constructor(
    private nodeDeleteUi: NodeDeleteUiService,
    private destroyRef: DestroyRef
  ) {
    this.saveHistory();
    this.nodeDeleteUi.deleteRequests$
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe((nodeId) => this.deleteNodeById(nodeId));
  }

  private saveHistory() {
    const history = this.historyByMode[this.activeMode];
    const index = this.historyIndexByMode[this.activeMode];

    if (index < history.length - 1) {
      this.historyByMode[this.activeMode] = history.slice(0, index + 1);
    }
    
    this.historyByMode[this.activeMode].push([...this.nodes]);
    this.historyIndexByMode[this.activeMode] += 1;
    
    if (this.historyByMode[this.activeMode].length > 20) {
      this.historyByMode[this.activeMode].shift();
      this.historyIndexByMode[this.activeMode] -= 1;
    }
  }

  public undo() {
    if (this.historyIndexByMode[this.activeMode] > 0) {
      this.historyIndexByMode[this.activeMode] -= 1;
      const history = this.historyByMode[this.activeMode];
      this.nodes = [...history[this.historyIndexByMode[this.activeMode]]];
      this.graphsByMode[this.activeMode].nodes = this.nodes;
      this.updateSuperServerStatus();
    }
  }

  public redo() {
    const history = this.historyByMode[this.activeMode];
    if (this.historyIndexByMode[this.activeMode] < history.length - 1) {
      this.historyIndexByMode[this.activeMode] += 1;
      this.nodes = [...history[this.historyIndexByMode[this.activeMode]]];
      this.graphsByMode[this.activeMode].nodes = this.nodes;
      this.updateSuperServerStatus();
    }
  }

  private updateSuperServerStatus() {
    this.alreadyHasSuperServer = this.nodes.some(n => (n as any).data?.type === 'SuperServerNode');
  }

  private deleteNodeById(nodeId: string): void {
    if (!this.nodes.some(node => node.id === nodeId)) return;
    this.nodes = this.nodes.filter(node => node.id !== nodeId);
    this.edges = this.edges.filter(edge => edge.source !== nodeId && edge.target !== nodeId);
    this.graphsByMode[this.activeMode] = { nodes: this.nodes, edges: this.edges };
    this.updateSuperServerStatus();
    this.saveHistory();
  }

  public handleReset() {
    this.nodes = [];
    this.edges = [];
    this.alreadyHasSuperServer = false;
    this.graphsByMode[this.activeMode] = { nodes: [], edges: [] };
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
      this.graphsByMode[this.activeMode].nodes = this.nodes;
      this.saveHistory();
      console.log("added new node:", newNode);
    } catch (e) {
      console.log('Catched', e);
    }
  }

  public onModeChange(mode: 'spyker' | 'hierfl'): void {
    if (this.activeMode === mode) return;

    this.graphsByMode[this.activeMode] = {
      nodes: this.nodes,
      edges: this.edges,
    };

    this.activeMode = mode;
    this.nodes = this.graphsByMode[mode].nodes;
    this.edges = this.graphsByMode[mode].edges;

    if (this.historyByMode[mode].length === 0) {
      this.historyByMode[mode] = [ [...this.nodes] ];
      this.historyIndexByMode[mode] = 0;
    }

    this.updateSuperServerStatus();
  }
}
