import { Component, computed, inject } from '@angular/core';
import { CustomNodeComponent } from 'ngx-vflow';
import { NodeDeleteUiService } from '../../../services/node-delete-ui.service';

@Component({
  selector: 'app-super-server-node',
  standalone: true, 
  imports: [],
  templateUrl: './super-server-node.html',
  styleUrl: './super-server-node.css',
})
export class SuperServerNode extends CustomNodeComponent {
  private nodeDeleteUi = inject(NodeDeleteUiService);
  public showDelete = computed(() => this.nodeDeleteUi.activeId() === this.node().id);

  public onNodeClick(event: MouseEvent): void {
    if (event.button !== 0) return;
    event.stopPropagation();
    this.nodeDeleteUi.showFor(this.node().id);
  }

  public onDelete(event: MouseEvent): void {
    event.stopPropagation();
    this.nodeDeleteUi.requestDelete(this.node().id);
  }
}