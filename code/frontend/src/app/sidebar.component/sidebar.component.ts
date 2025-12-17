import { Component, Inject, Output, EventEmitter } from '@angular/core';
import { CommonModule, DOCUMENT } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { ErrorPopup } from '../error.popup/error.popup'; 
import { StartPopup } from '../start.popup/start.popup'; 
import { ResetButton } from '../reset.button/reset.button'; 

@Component({
  selector: 'app-sidebar',
  standalone: true,
  templateUrl: './sidebar.component.html',
  styleUrls: ['./sidebar.component.css'],
  imports: [FormsModule, CommonModule, ErrorPopup, StartPopup, ResetButton],
})
export class SidebarComponent {
  public isOpen = true;
  public isDarkMode = true;
  public showSimulationpopup = false;
  public toastMessage: string | null = null;

  @Output() resetGraph = new EventEmitter<void>();

  public selectedArchitectures = {
    spyker: false,
    hierfl: true,
  };

  public configDraft = {
    superserver: { name: 'SuperServer', id: 'SS-01', cpus: 8, gpus: 1 },
    server: { name: 'Server Node', environment: 'Spyker', cpus: 4, gpus: 0, computeTimeMs: 50 },
    client: { id: 'CL-01', count: 50, type: 'mobile', computeTimeMs: 120, pingMs: 40, packetloss: 0.02 }
  };

  constructor(@Inject(DOCUMENT) private document: Document) {}

  private showToast(message: string) {
    this.toastMessage = message;
    setTimeout(() => { this.toastMessage = null; }, 2000);
  }

  public onResetRequested(): void {
    this.resetGraph.emit();
  }

  public toggleArchitecture(): void {
    this.selectedArchitectures.spyker = !this.selectedArchitectures.spyker;
    this.selectedArchitectures.hierfl = !this.selectedArchitectures.spyker;
  }

  public setArchitecture(isSpyker: boolean): void {
    this.selectedArchitectures.spyker = isSpyker;
    this.selectedArchitectures.hierfl = !isSpyker;
  }

  public toggleSidebar(): void { this.isOpen = !this.isOpen; }
  public openSidebar(): void { this.isOpen = true; }
  public closeSidebar(): void { this.isOpen = false; }

  public toggleTheme(): void {
    this.isDarkMode = !this.isDarkMode;
    if (this.isDarkMode) { this.document.body.classList.remove('light-mode'); } 
    else { this.document.body.classList.add('light-mode'); }
  }

  public onDragStart(event: DragEvent, kind: 'SuperServerNode' | 'ServerNode' | 'ClientNode'): void {
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
        this.showToast('Only one Super Server can exist in the environment Hierarchical.');
        return;
      }
    }
    const payload = { type: kind, config: this.configDraft };
    if (event.dataTransfer) {
      event.dataTransfer.setData('application/json', JSON.stringify(payload));
      event.dataTransfer.effectAllowed = 'copy';
    }
  }

  public openSimulationpopup(): void { this.showSimulationpopup = true; }
  public closeSimulationpopup(): void { this.showSimulationpopup = false; }
  
  public runSimulation(type: 'spyker' | 'hierarchical' | 'both'): void { 
    console.log('Starte Simulation für:', type); 
    this.closeSimulationpopup(); 
  }
}