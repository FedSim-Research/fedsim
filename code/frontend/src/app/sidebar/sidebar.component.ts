import { Component } from '@angular/core';
import { FormsModule } from '@angular/forms';

@Component({
  selector: 'app-sidebar',
  standalone: true,
  templateUrl: './sidebar.component.html',
  styleUrls: ['./sidebar.component.css'],
  imports: [FormsModule],
})
export class SidebarComponent {
  public isOpen = true;

  
  public selectedArchitectures = {
    spyker: true,
    hierfl: false,
  };

  public edgesChecked = false;

  // Zentrales Datenmodell für die Inputs
  public configDraft = {
    superserver: {
      name: 'SuperServer',
      id: 'SS-01',
      cpus: 8,
      gpus: 1
    },
    server: {
      name: 'Server Node',
      environment: 'Spyker', 
      cpus: 4,
      gpus: 0,
      computeTimeMs: 50
    },
    client: {
      id: 'CL-01',
      count: 50,
      type: 'mobile', 
      computeTimeMs: 120,
      pingMs: 40,
      packetloss: 0.02
    }
  };

  public toggleSidebar(): void {
    this.isOpen = !this.isOpen;
  }

  public openSidebar(): void {
    this.isOpen = true;
  }

  public closeSidebar(): void {
    this.isOpen = false;
  }

  public onDragStart(
    event: DragEvent,
    kind: 'superserver' | 'server' | 'client'
  ): void {
    if (kind === 'superserver' && this.selectedArchitectures.spyker) {
      event.preventDefault();
      return;
    }


    const payload = {
      type: kind,
      config: this.configDraft[kind]
    };

    // Daten als JSON String anhängen
    if (event.dataTransfer) {
      event.dataTransfer.setData('application/json', JSON.stringify(payload));
      event.dataTransfer.effectAllowed = 'copy';
    }
  }
}