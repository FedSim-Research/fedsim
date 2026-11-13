import { Component } from '@angular/core';
import { LowerCasePipe, NgIf, TitleCasePipe } from '@angular/common';
import { ButtonModule } from 'primeng/button';
import { HandleComponent } from 'ngx-vflow';
import { GraphNodeComponent } from '../graph-node.component';

type ClientSettings = {
  count: number;
  type: string;
  computeFactor: number;
  performanceSigma: number;
  uploadMbps: number;
  downloadMbps: number;
};

@Component({
  selector: 'app-client-node',
  standalone: true,
  imports: [NgIf, LowerCasePipe, TitleCasePipe, HandleComponent, ButtonModule],
  templateUrl: './client-node.html',
  styleUrl: './client-node.css',
})
export class ClientNode extends GraphNodeComponent<ClientSettings> {
  /** Shown preselected when a client has no type yet, and stored if saved like that. */
  public readonly defaultClientType = 'laptop';

  protected readonly defaults: ClientSettings = {
    count: 50,
    type: '',
    computeFactor: 0.8,
    performanceSigma: 0,
    uploadMbps: 2,
    downloadMbps: 10,
  };
  protected readonly forwardKind = 'client';

  public readonly client = this.settings;

  /** Client types are stored in lowercase, as the sidebar does. */
  protected override toConfig(draft: ClientSettings): Partial<ClientSettings> {
    const config = super.toConfig(draft);
    return { ...config, type: (config.type || this.defaultClientType).toLowerCase() };
  }
}
