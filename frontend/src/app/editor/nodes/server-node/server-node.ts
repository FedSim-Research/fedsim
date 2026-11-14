import { Component } from '@angular/core';
import { NgIf } from '@angular/common';
import { ButtonModule } from 'primeng/button';
import { HandleComponent } from 'ngx-vflow';
import { GraphNodeComponent } from '../graph-node.component';

type ServerSettings = {
  name: string;
  computeFactor: number;
  performanceSigma: number;
  uploadMbps: number;
  downloadMbps: number;
};

@Component({
  selector: 'app-server-node',
  standalone: true,
  imports: [NgIf, HandleComponent, ButtonModule],
  templateUrl: './server-node.html',
  styleUrl: './server-node.css',
})
export class ServerNode extends GraphNodeComponent<ServerSettings> {
  protected readonly defaults: ServerSettings = {
    name: '',
    computeFactor: 2,
    performanceSigma: 0,
    uploadMbps: 20,
    downloadMbps: 100,
  };
  protected readonly forwardKind = 'server';

  public readonly server = this.settings;
}
