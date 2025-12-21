import { Component, computed, inject } from '@angular/core';
import { NgIf } from '@angular/common';
import { CustomNodeComponent, HandleComponent } from 'ngx-vflow';
import { NodeDeleteUiService } from '../../../services/node-delete-ui.service';

@Component({
  selector: 'app-server-node',
  standalone: true,
  imports: [NgIf, HandleComponent],
  templateUrl: './server-node.html',
  styleUrl: './server-node.css',
})
export class ServerNode extends CustomNodeComponent{
  private nodeDeleteUi = inject(NodeDeleteUiService);
  public showDelete = computed(() => this.nodeDeleteUi.activeId() === this.node().id);
  public isSelected = computed(() => Boolean((this.node().data as any)?.selected));

  public server = computed(() => {
    const config = ((this.node().data as any)?.config) ?? {};
    const environment = ((this.node().data as any)?.environment) ?? (config.environment ?? 'spyker');
    return {
      name: config.name ?? '',
      cpus: config.cpus ?? 0,
      gpus: config.gpus ?? 0,
      computeTimeMs: config.computeTimeMs ?? 0,
      environment,
    };
  });

  public environment = computed(() => (this.server().environment ?? 'spyker').toString().toLowerCase());

  public onNodeClick(event: MouseEvent): void {
    if (event.button !== 0) return;
    if (event.ctrlKey || event.metaKey) {
      event.stopPropagation();
      window.dispatchEvent(new CustomEvent('node-ctrl-click', { detail: { id: this.node().id } }));
      return;
    }
    event.stopPropagation();
    this.nodeDeleteUi.showFor(this.node().id);
  }

  public onDelete(event: MouseEvent): void {
    event.stopPropagation();
    this.nodeDeleteUi.requestDelete(this.node().id);
  }
}
