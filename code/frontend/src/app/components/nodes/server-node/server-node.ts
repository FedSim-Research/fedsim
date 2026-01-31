import { Component, computed, inject } from '@angular/core';
import { NgIf } from '@angular/common';
import { CustomNodeComponent, HandleComponent } from 'ngx-vflow';
import { NodeDeleteUiService } from '../../../services/node-delete-ui.service';
import { GraphServiceSpyker } from '../../../services/subservices/graph-service-spyker';
import { GraphServiceHierach } from '../../../services/subservices/graph-service-hierach';

@Component({
  selector: 'app-server-node',
  standalone: true,
  imports: [NgIf, HandleComponent],
  templateUrl: './server-node.html',
  styleUrl: './server-node.css',
})
export class ServerNode extends CustomNodeComponent {
  protected graphServiceSpyker = inject(GraphServiceSpyker);
  protected graphServiceHierach = inject(GraphServiceHierach);
  private nodeDeleteUi = inject(NodeDeleteUiService);
  public showDelete = computed(() => this.nodeDeleteUi.activeId() === this.node().id);
  public isSelected = computed(() => Boolean((this.node().data as any)?.selected));

  public server = computed(() => {
    const config = ((this.node().data as any)?.config) ?? {};
    const environment = ((this.node().data as any)?.environment) ?? (config.environment ?? 'spyker');
    return {
      name: config.name ?? '',
      id: config.id ?? '',
      computeFactor: config.computeFactor ?? 2.0,
      pingMs: config.pingMs ?? 20,
      jitterMs: config.jitterMs ?? 2,
      packetloss: config.packetloss ?? 0.001,
      packetlossStddev: config.packetlossStddev ?? 0.0001,
      uploadMbps: config.uploadMbps ?? 20,
      downloadMbps: config.downloadMbps ?? 100,
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
    if (this.graphServiceSpyker.nodes().some(node => node.id === this.node().id)) {
      this.graphServiceSpyker.removeNodeById(this.node().id);
      console.log("Removed server node from spyker");
    } else {
      this.graphServiceHierach.removeNodeById(this.node().id);
      console.log("Removed server node from hierfl");
    }
  }
}
