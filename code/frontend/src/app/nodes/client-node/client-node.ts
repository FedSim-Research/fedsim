import { Component } from '@angular/core';
import { CustomNodeComponent, NodeHtmlTemplateDirective } from 'ngx-vflow';

@Component({
  selector: 'app-client-node',
  imports: [NodeHtmlTemplateDirective],
  templateUrl: './client-node.html',
  styleUrl: './client-node.css',
})
export class ClientNode extends CustomNodeComponent{
    displayTooltips = false;  
}