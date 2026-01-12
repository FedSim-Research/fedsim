import { Component, Inject, Output, EventEmitter, ViewChild, ElementRef, Input } from '@angular/core';
import { CommonModule, DOCUMENT } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { StartPopup } from '../start.popup/start.popup';
import { ResetButton } from '../reset.button/reset.button';
import { ViewGraphsDialog } from '../view-graphs.component/view-graphs.component';
import { ToastModule } from 'primeng/toast';
import { MessageService } from 'primeng/api';
import { ConfirmDialogModule } from 'primeng/confirmdialog';
import { ConfirmationService } from 'primeng/api';
import { Shortcuts } from '../../directives/shortcuts';

@Component({
  selector: 'app-sidebar',
  standalone: true,
  templateUrl: './sidebar.component.html',
  styleUrls: ['./sidebar.component.css'],
  imports: [FormsModule, CommonModule, StartPopup, ResetButton, ViewGraphsDialog, ToastModule, ConfirmDialogModule],
  providers: [MessageService, ConfirmationService],
})
export class SidebarComponent {
  public isOpen = true;
  public isDarkMode = true;
  public showSimulationpopup = false;
  public showViewGraphsDialog = false;
  @ViewChild('supDetails') private supDetails?: ElementRef<HTMLDetailsElement>;

  @Input() shortcuts?: Shortcuts;
  @Output() resetGraph = new EventEmitter<void>();
  @Output() modeChange = new EventEmitter<'spyker' | 'hierfl'>();
  @Output() graphSelected = new EventEmitter<{ graphId: number; architecture: 'spyker' | 'hierfl' }>();

  public selectedArchitectures = {
    spyker: false,
    hierfl: true,
  };

  public configDraft = {
    superserver: { name: 'Super Server', id: 'SS-01', cpus: 8, gpus: 1 },
    server: { name: 'Server Node', environment: 'Spyker', cpus: 4, gpus: 0, computeTimeMs: 50 },
    client: { id: 'CL-01', count: 50, type: 'mobile', computeTimeMs: 120, pingMs: 40, packetloss: 0.02 }
  };

  constructor(
    @Inject(DOCUMENT) private document: Document,
    private messageService: MessageService,
    private confirmationService: ConfirmationService
  ) {}

  private showErrorToast(message: string) {
    this.messageService.add({
      severity: 'error',
      summary: 'Error',
      detail: message,
    });
  }

  public onResetRequested(): void {
    this.confirmationService.confirm({
      header: 'Reset graph?',
      message: 'Are you sure you want to delete all nodes and edges?',
      icon: 'pi pi-exclamation-triangle',
      acceptLabel: 'Yes, delete',
      rejectLabel: 'Cancel',
      rejectButtonStyleClass: 'p-button-text p-button-sm',
      acceptButtonStyleClass: 'p-button-danger p-button-sm',
      defaultFocus: 'accept',
      closable: true,
      closeOnEscape: true,
      accept: () => {
        this.resetGraph.emit();
      },
    });
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
    if (this.selectedArchitectures.spyker) {
      this.closeSuperServerDisclosure();
    }
  }

  public setArchitecture(isSpyker: boolean): void {
    this.selectedArchitectures.spyker = isSpyker;
    this.selectedArchitectures.hierfl = !isSpyker;
    this.modeChange.emit(isSpyker ? 'spyker' : 'hierfl');
    if (isSpyker) {
      this.closeSuperServerDisclosure();
    }
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
        event.stopPropagation();
        this.showErrorToast('No super server is allowed to exist in the Spyker Environment');
        return;
      }
      const allGraphNodes = document.querySelectorAll('.vflow-node');
      const alreadyExists = Array.from(allGraphNodes).some(node => {
        const text = node.textContent?.toLowerCase().replace(/\s+/g, '') ?? '';
        return text.includes('superserver');
      });
      if (alreadyExists) {
        event.preventDefault();
        event.stopPropagation();
        this.showErrorToast('Only one Super Server can exist in the Environment Hierarchical.');
        return;
      }
    }
    const configByKind = {
      SuperServerNode: { ...this.configDraft.superserver },
      ServerNode: { ...this.configDraft.server },
      ClientNode: { ...this.configDraft.client },
    } as const;

    const payload = { type: kind, config: configByKind[kind] };
    if (event.dataTransfer) {
      event.dataTransfer.setData('application/json', JSON.stringify(payload));
      event.dataTransfer.effectAllowed = 'copy';
    }
  }

  public openSimulationpopup(): void { this.showSimulationpopup = true; }
  public closeSimulationpopup(): void { this.showSimulationpopup = false; }
  public onSuperServerSummaryClick(event: Event): void {
    if (this.selectedArchitectures.spyker) {
      event.preventDefault();
      this.closeSuperServerDisclosure();
      this.showErrorToast('No super server is allowed to exist in the Spyker Environment');
    }
  }
  private closeSuperServerDisclosure(): void {
    this.supDetails?.nativeElement.removeAttribute('open');
  }

  public openViewGraphsDialog(): void {
    this.showViewGraphsDialog = true;
  }

  public closeViewGraphsDialog(): void {
    this.showViewGraphsDialog = false;
  }

  public onGraphSelected(event: { graphId: number; architecture: 'spyker' | 'hierfl' }): void {
    this.graphSelected.emit(event);
    this.closeViewGraphsDialog();
  }
  
  public runSimulation(type: 'spyker' | 'hierarchical' | 'both'): void { 
    console.log('Starte Simulation für:', type); 
    this.closeSimulationpopup();
  }
}
