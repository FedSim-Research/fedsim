import { Component, signal } from '@angular/core';
import { CustomNodeComponent, NodeHtmlTemplateDirective } from 'ngx-vflow';

@Component({
  selector: 'app-client-node',
  imports: [NodeHtmlTemplateDirective],
  templateUrl: './client-node.html',
  styleUrl: './client-node.css',
})

export class ClientNode extends CustomNodeComponent{
   override data = signal({ 
     id: '', 
     count: 0, 
     type: '', 
     computeTimeMs: 0, 
     pingMs: 0, 
     packetloss: 0, 
   });
 }