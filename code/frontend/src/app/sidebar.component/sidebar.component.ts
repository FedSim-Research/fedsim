import { Component, Inject } from '@angular/core';
import { CommonModule, DOCUMENT } from '@angular/common';
import { FormsModule } from '@angular/forms';
// Die Node Imports brauchst du hier eigentlich nicht zwingend, 
// es sei denn du nutzt sie für Typen, aber sie schaden auch nicht.

@Component({
  selector: 'app-sidebar',
  standalone: true,
  templateUrl: './sidebar.component.html',
  styleUrls: ['./sidebar.component.css'],
  imports: [FormsModule, CommonModule],
})
export class SidebarComponent {
  public isOpen = true;
  public isDarkMode = true;

  // WICHTIG: Name geändert zu 'showSimulationpopup' passend zur HTML
  public showSimulationpopup = false;
  
  public selectedArchitectures = {
    spyker: true,
    hierfl: false,
  };

  public edgesChecked = false;

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

  constructor(@Inject(DOCUMENT) private document: Document) {}

  public toggleSidebar(): void {
    this.isOpen = !this.isOpen;
  }

  public openSidebar(): void {
    this.isOpen = true;
  }

  public closeSidebar(): void {
    this.isOpen = false;
  }

  public toggleTheme(): void {
    this.isDarkMode = !this.isDarkMode;
    
    if (this.isDarkMode) {
      this.document.body.classList.remove('light-mode');
    } else {
      this.document.body.classList.add('light-mode');
    }
  }

  public onDragStart(
    event: DragEvent,
    kind: 'SuperServerNode' | 'ServerNode' | 'ClientNode'
  ): void {
    if (kind === 'SuperServerNode') {
      if (this.selectedArchitectures.spyker) {
        event.preventDefault();
        return;
      }

      const allGraphNodes = document.querySelectorAll('.vflow-node');
      const alreadyExists = Array.from(allGraphNodes).some(node => 
        node.textContent?.includes('SuperServer')
      );
      
      if (alreadyExists) {
        event.preventDefault();
        event.stopPropagation();
        return;
      }
    }

    const payload = {
      type: kind,
      config: this.configDraft
    };

    if (event.dataTransfer) {
      event.dataTransfer.setData('application/json', JSON.stringify(payload));
      event.dataTransfer.effectAllowed = 'copy';
    }
  }

  // --- popup Logic ---

  public openSimulationpopup(): void {
    this.showSimulationpopup = true;
  }

  public closeSimulationpopup(): void {
    this.showSimulationpopup = false;
  }

  public runSimulation(type: 'spyker' | 'hierarchical' | 'both'): void {
    console.log('Starte Simulation für:', type);
    // Hier Logik einfügen (z.B. Service call)
    this.closeSimulationpopup();
  }
}