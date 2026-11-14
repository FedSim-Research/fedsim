import { Component } from '@angular/core';
import { NgIf } from '@angular/common';
import { ButtonModule } from 'primeng/button';
import { HandleComponent } from 'ngx-vflow';
import { GraphNodeComponent } from '../graph-node.component';

type SuperServerSettings = {
  name: string;
  computeFactor: number;
  performanceSigma: number;
  uploadMbps: number;
  downloadMbps: number;
};

@Component({
  selector: 'app-super-server-node',
  standalone: true,
  imports: [NgIf, HandleComponent, ButtonModule],
  templateUrl: './super-server-node.html',
  styleUrl: './super-server-node.css',
})
export class SuperServerNode extends GraphNodeComponent<SuperServerSettings> {
  protected readonly defaults: SuperServerSettings = {
    name: '',
    computeFactor: 2,
    performanceSigma: 0,
    uploadMbps: 20,
    downloadMbps: 100,
  };
  protected readonly forwardKind = 'superserver';

  public readonly superserver = this.settings;
}
