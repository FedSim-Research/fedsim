import { Component } from '@angular/core';
import { CustomNodeComponent } from 'ngx-vflow';

@Component({
  selector: 'app-super-server-node',
  standalone: true, 
  imports: [],
  templateUrl: './super-server-node.html',
  styleUrl: './super-server-node.css',
})
export class SuperServerNode extends CustomNodeComponent {
}