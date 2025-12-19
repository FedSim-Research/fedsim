import { Component, computed, inject, signal } from '@angular/core';
import { CustomNodeComponent } from 'ngx-vflow';
import { NodeDeleteUiService } from '../../../services/node-delete-ui.service';

@Component({
  selector: 'app-client-node',
  templateUrl: './client-node.html',
  styleUrl: './client-node.css',
})

export class ClientNode extends CustomNodeComponent{
   private nodeDeleteUi = inject(NodeDeleteUiService);
   public showDelete = computed(() => this.nodeDeleteUi.activeId() === this.node().id);

   override data = signal({ 
     id: '', 
     count: 0, 
     type: '', 
     computeTimeMs: 0, 
     pingMs: 0, 
     packetloss: 0, 
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
