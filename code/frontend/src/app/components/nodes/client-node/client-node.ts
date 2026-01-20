import { Component, computed, inject } from '@angular/core';
import { CustomNodeComponent, HandleComponent } from 'ngx-vflow';
import { NodeDeleteUiService } from '../../../services/node-delete-ui.service';
import { GraphServiceHierach } from '../../../services/subservices/graph-service-hierach';
import { GraphServiceSpyker } from '../../../services/subservices/graph-service-spyker';

@Component({
  selector: 'app-client-node',
  standalone: true,
  imports: [HandleComponent],
  templateUrl: './client-node.html',
  styleUrl: './client-node.css',
})

export class ClientNode extends CustomNodeComponent {
  protected graphServiceSpyker = inject(GraphServiceSpyker);
  protected graphServiceHierach = inject(GraphServiceHierach);
  private nodeDeleteUi = inject(NodeDeleteUiService);
  public showDelete = computed(() => this.nodeDeleteUi.activeId() === this.node().id);

  public isSelected = computed(() => Boolean((this.node().data as any)?.selected));

  public client = computed(() => {
    const config = ((this.node().data as any)?.config) ?? {};
    const environment = ((this.node().data as any)?.environment) ?? (config.environment ?? 'spyker');

    const rawType = config.type ?? '';
    const type = typeof rawType === 'string' && rawType.length
      ? rawType.charAt(0).toUpperCase() + rawType.slice(1)
      : rawType;

    return {
      id: config.id ?? '',
      count: config.count ?? 50,
      type,
      computeFactor: config.computeFactor ?? 0.8,
      pingMs: config.pingMs ?? 40,
      jitterMs: config.jitterMs ?? 4,
      packetloss: config.packetloss ?? 0.02,
      packetlossStddev: config.packetlossStddev ?? 0.002,
      uploadMbps: config.uploadMbps ?? 2,
      downloadMbps: config.downloadMbps ?? 10,
      environment,
    };
  });

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
      console.log("Removed client node from spyker");
    } else {
      this.graphServiceHierach.removeNodeById(this.node().id);
      console.log("Removed client node from hierfl");
    }
  }
}
