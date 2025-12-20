import { Component, computed, inject } from '@angular/core';
import { CustomNodeComponent, HandleComponent } from 'ngx-vflow';
import { NodeDeleteUiService } from '../../../services/node-delete-ui.service';

@Component({
  selector: 'app-client-node',
  standalone: true,
  imports: [HandleComponent],
  templateUrl: './client-node.html',
  styleUrl: './client-node.css',
})

export class ClientNode extends CustomNodeComponent{
   private nodeDeleteUi = inject(NodeDeleteUiService);
   public showDelete = computed(() => this.nodeDeleteUi.activeId() === this.node().id);

   public client = computed(() => {
     const config = ((this.node().data as any)?.config) ?? {};
    const environment = ((this.node().data as any)?.environment) ?? (config.environment ?? 'spyker');
     return {
       id: config.id ?? '',
       count: config.count ?? 0,
       type: config.type ?? '',
       computeTimeMs: config.computeTimeMs ?? 0,
       pingMs: config.pingMs ?? 0,
       packetloss: config.packetloss ?? 0,
      environment,
     };
   });

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
