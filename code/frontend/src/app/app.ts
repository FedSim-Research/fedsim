import { Component } from '@angular/core';
import { CommonModule } from '@angular/common'; 
import { Vflow, Node, Edge } from 'ngx-vflow';
import { SidebarComponent } from './sidebar/sidebar.component';

@Component({
  selector: 'app-root',
  standalone: true,
  imports: [Vflow, SidebarComponent, CommonModule],
  template: `
    <div
      class="canvas-wrapper"
      (dragover)="onDragOver($event)" 
      (drop)="onDrop($event)"
    >
      
      <vflow
        [nodes]="nodes"
        [edges]="edges"
        view="auto"
        [background]="{ type: 'dots' }"
        [alignmentHelper]="true"
      >
        <ng-template let-ctx>
          <div class="custom-node" [ngClass]="ctx.node.data.type">
            
            <div class="node-header">
              <strong>{{ ctx.node.data.config.name || ctx.node.data.config.id }}</strong>
              <span class="badge">{{ ctx.node.data.type }}</span>
            </div>

            <div class="node-body">
              
              <div *ngIf="ctx.node.data.config.cpus" class="node-row">
                <span>CPU: {{ ctx.node.data.config.cpus }}</span>
                <span>GPU: {{ ctx.node.data.config.gpus }}</span>
              </div>
              
              <div *ngIf="ctx.node.data.type === 'client'" class="node-row">
                <span>{{ ctx.node.data.config.count }}x {{ ctx.node.data.config.type }}</span>
              </div>

               <div *ngIf="ctx.node.data.config.pingMs" class="node-row muted">
                Ping: {{ ctx.node.data.config.pingMs }}ms
              </div>
            </div>

            <div class="handle source"></div>
            <div class="handle target"></div>
          </div>
        </ng-template>

        <mini-map />
      </vflow>

      <app-sidebar />
    </div>
  `,
  styles: [`
    /* Füllt den gesamten Viewport */
    .canvas-wrapper {
      height: 100vh;
      width: 100vw;
      background-color: #1a1a1a; 
      overflow: hidden;
      position: relative;
    }

    /* --- NODE DESIGN --- */
    .custom-node {
      width: 200px;
      background: #0b0b0b; /* Fast Schwarz */
      border: 1px solid rgba(255, 255, 255, 0.15);
      border-radius: 8px;
      color: #ffffff;
      font-family: 'Inter', system-ui, sans-serif;
      box-shadow: 0 8px 24px rgba(0,0,0,0.5);
      transition: transform 0.1s, box-shadow 0.1s;
    }

    .custom-node:hover {
      border-color: rgba(255, 255, 255, 0.4);
      box-shadow: 0 12px 32px rgba(0,0,0,0.7);
    }

    /* Farbliche Codierung (Border Top) */
    .custom-node.superserver { border-top: 4px solid #ff4757; } /* Rot */
    .custom-node.server      { border-top: 4px solid #2ed573; } /* Grün */
    .custom-node.client      { border-top: 4px solid #1e90ff; } /* Blau */

    /* Header Styling */
    .node-header {
      padding: 10px 12px;
      background: rgba(255, 255, 255, 0.05);
      border-bottom: 1px solid rgba(255, 255, 255, 0.1);
      display: flex;
      justify-content: space-between;
      align-items: center;
    }

    .node-header strong {
      font-size: 0.85rem;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
      max-width: 110px;
    }

    .badge {
      font-size: 0.65rem;
      text-transform: uppercase;
      font-weight: 700;
      padding: 2px 6px;
      border-radius: 4px;
      background: rgba(255, 255, 255, 0.1);
      color: rgba(255, 255, 255, 0.6);
    }

    /* Content Styling */
    .node-body {
      padding: 12px;
      font-size: 0.8rem;
      display: flex;
      flex-direction: column;
      gap: 6px;
      color: rgba(255, 255, 255, 0.8);
    }

    .node-row {
      display: flex;
      justify-content: space-between;
      align-items: center;
    }
    
    .muted {
      color: rgba(255, 255, 255, 0.4);
      font-size: 0.75rem;
      margin-top: 4px;
    }
    `]
})
export class App {
  // Demo-Daten
  public nodes: Node[] = [
    {
      id: '1',
      point: { x: 10, y: 10 },
      type: 'default',
      text: 'Server',
    },
    {
      id: '2',
      point: { x: 100, y: 100 },
      type: 'default',
      text: '2',
    },
    {
      id: '3',
      point: { x: 200, y: 200 },
      type: 'default',
      text: '3',
    },
  ];

  public edges: Edge[] = [
    {
      id: '1-2',
      source: '1',
      target: '2',
    },
    {
      id: '2-3',
      source: '2',
      target: '3',
    },
  ];

  // DragOver: Erlaubt das Droppen auf diesem Element.
  public onDragOver(event: DragEvent) {
    event.preventDefault(); 
    if (event.dataTransfer) {
      event.dataTransfer.dropEffect = 'copy'; 
    }
  }

  // OnDrop: Erstellt den neuen Node basierend auf den Sidebar-Daten.
  public onDrop(event: DragEvent) {
    event.preventDefault();

    // 1. JSON-String auslesen
    const rawData = event.dataTransfer?.getData('application/json');
    if (!rawData) return;

    try {
      const payload = JSON.parse(rawData);

      // 2. Position bestimmen 
      const position = {
        x: event.clientX - 100, 
        y: event.clientY - 50
      };

      // 3. Neuen Node erstellen
      const newNode: Node = {
        id: crypto.randomUUID(), 
        point: position,
        type: 'default',   
        text: payload.type,
        data: {
          type: payload.type,    
          config: payload.config 
        }
      };

      // 4. Liste aktualisieren (Immutable Update)
      this.nodes = [...this.nodes, newNode];
      console.log('Neuer Node hinzugefügt:', newNode);
      console.log('Aktuelle Nodes:', this.nodes);

    } catch (error) {
      console.error('Fehler beim Einfügen des Nodes:', error);
    }
  }
}