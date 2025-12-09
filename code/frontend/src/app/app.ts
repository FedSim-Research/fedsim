import { Component, ChangeDetectionStrategy } from '@angular/core';
import { Vflow, Node, Edge } from 'ngx-vflow';
import { SidebarComponent } from './sidebar/sidebar.component';

@Component({
  selector: 'app-root',
  standalone: true,
  template: `
    <div style="height: 100vh; width: 100vw; background-color: #f0f0f0;">
      <vflow
        [nodes]="nodes"
        [edges]="edges"
        view="auto"
        [background]="{ type: 'dots' }"
        [alignmentHelper]="true"
      >
        <mini-map />
      </vflow>
      <app-sidebar />
    </div>
  `,
  imports: [Vflow, SidebarComponent],
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class App {
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
}
