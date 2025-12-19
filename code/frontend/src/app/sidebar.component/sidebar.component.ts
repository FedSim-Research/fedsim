import { Component, Inject, Output, EventEmitter } from '@angular/core';
import { CommonModule, DOCUMENT } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { StartPopup } from '../start.popup/start.popup';
import { ResetButton } from '../reset.button/reset.button';
import { ToastModule } from 'primeng/toast';
import { MessageService } from 'primeng/api';

@Component({
  selector: 'app-sidebar',
  standalone: true,
  templateUrl: './sidebar.component.html',
  styleUrls: ['./sidebar.component.css'],
  imports: [FormsModule, CommonModule, StartPopup, ResetButton, ToastModule],
  providers: [MessageService],
})
export class SidebarComponent {
  public isOpen = true;
  public isDarkMode = true;
  public showSimulationpopup = false;

  @Output() resetGraph = new EventEmitter<void>();
  @Output() modeChange = new EventEmitter<'spyker' | 'hierfl'>();

  public selectedArchitectures = {
    spyker: false,
    hierfl: true,
  };

  public configDraft = {
    superserver: { name: 'SuperServer', id: 'SS-01', cpus: 8, gpus: 1 },
    server: { name: 'Server Node', environment: 'Spyker', cpus: 4, gpus: 0, computeTimeMs: 50 },
    client: { id: 'CL-01', count: 50, type: 'mobile', computeTimeMs: 120, pingMs: 40, packetloss: 0.02 }
  };

  constructor(
    @Inject(DOCUMENT) private document: Document,
    private messageService: MessageService
  ) {}

  private showErrorToast(message: string) {
    this.messageService.add({
      severity: 'error',
      summary: 'Error',
      detail: message,
    });
  }

  public onResetRequested(): void {
    this.resetGraph.emit();
  }

  @Output() undoRequested = new EventEmitter<void>();
  @Output() redoRequested = new EventEmitter<void>();
  
  public redo(): void {
    this.redoRequested.emit();
  }

  public undo(): void {
    this.undoRequested.emit();
  }

  public toggleArchitecture(): void {
    this.selectedArchitectures.spyker = !this.selectedArchitectures.spyker;
    this.selectedArchitectures.hierfl = !this.selectedArchitectures.spyker;
    this.modeChange.emit(this.selectedArchitectures.spyker ? 'spyker' : 'hierfl');
  }

  public setArchitecture(isSpyker: boolean): void {
    this.selectedArchitectures.spyker = isSpyker;
    this.selectedArchitectures.hierfl = !isSpyker;
    this.modeChange.emit(isSpyker ? 'spyker' : 'hierfl');
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
        this.showErrorToast('Only one Super Server can exist in the environment Hierarchical.');
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
