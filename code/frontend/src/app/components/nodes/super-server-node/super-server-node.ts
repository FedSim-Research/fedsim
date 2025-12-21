import { Component, computed, inject } from '@angular/core';
import { CustomNodeComponent, HandleComponent } from 'ngx-vflow';
import { NodeDeleteUiService } from '../../../services/node-delete-ui.service';

@Component({
  selector: 'app-super-server-node',
  standalone: true, 
  imports: [HandleComponent],
  templateUrl: './super-server-node.html',
  styleUrl: './super-server-node.css',
})
export class SuperServerNode extends CustomNodeComponent {
  private nodeDeleteUi = inject(NodeDeleteUiService);
  public showDelete = computed(() => this.nodeDeleteUi.activeId() === this.node().id);
  public isSelected = computed(() => Boolean((this.node().data as any)?.selected));

  public superserver = computed(() => {
    const config = ((this.node().data as any)?.config) ?? {};
    const environment = ((this.node().data as any)?.environment) ?? (config.environment ?? 'spyker');
    return {
      name: config.name ?? '',
      id: config.id ?? '',
      cpus: config.cpus ?? 0,
      gpus: config.gpus ?? 0,
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
    this.nodeDeleteUi.requestDelete(this.node().id);
  }
}