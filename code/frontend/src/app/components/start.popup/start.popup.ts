import { Component, EventEmitter, Input, OnInit, Output, SimpleChanges } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { StepperModule } from 'primeng/stepper';

type StartMode = 'spyker' | 'hierfl' | 'both';

type CommonTrainingConfig = {
  epochs: number;
  lr: number;
  modelComplexity: number;
  batchSize?: number;
};

type CommonSimulationConfig = {
  runTimeLimit: number;
  evalInterval: number;
  gpuBudget: number;
  seed: number;
  outputFilename: string;
  evaluateModel: boolean;
};

type RunPayload = {
  mode: StartMode;
  hierfl: {
    trainingConfig: CommonTrainingConfig;
    simulationSettings: CommonSimulationConfig;
  };
  spyker: {
    trainingConfig: CommonTrainingConfig;
    simulationSettings: CommonSimulationConfig & { idleTokenDelay: number };
    spykerConfig: {
      decayBeta: number;
      minLearningRate: number;
      hInter: number;
      hIntra: number;
      sigmoidPhi: number;
      serverLearningRate: number;
      tcpRtoDelay: number;
    };
  };
};

@Component({
  selector: 'app-start-popup',
  standalone: true,
  imports: [CommonModule, FormsModule, StepperModule],
  templateUrl: './start.popup.html',
  styleUrl: './start.popup.css',
})
export class StartPopup implements OnInit {
  @Input() hierflGraphId: number | null = null;
  @Input() spykerGraphId: number | null = null;
  @Output() close = new EventEmitter<void>();
  @Output() run = new EventEmitter<RunPayload>();

  public activeStep = 1;
  public selectedMode: StartMode | null = null;
  public evaluateAfterRun = false;
  private evaluateAfterRunByArchitecture: { hierfl: boolean; spyker: boolean } = {
    hierfl: false,
    spyker: false,
  };

  public hierflSettings = {
    epochs: 1,
    lr: 0.005,
    modelComplexity: 1.0,
    batchSize: 32,
    runTimeLimit: 5000,
    evalInterval: 500,
    gpuBudget: 0,
    seed: 42,
    outputFilename: 'final_model_hierarchical.pth',
    evaluateModel: false,
  };

  public spykerSettings = {
    epochs: 1,
    lr: 0.005,
    modelComplexity: 1.0,
    batchSize: 32,
    runTimeLimit: 5000,
    evalInterval: 500,
    gpuBudget: 0,
    seed: 42,
    idleTokenDelay: 0.5,
    outputFilename: 'final_model_spyker.pth',
    evaluateModel: false,
    decayBeta: 0.1,
    minLearningRate: 0.000001,
    hInter: 5,
    hIntra: 50,
    sigmoidPhi: 1.0,
    serverLearningRate: 0.1,
    tcpRtoDelay: 0.2,
  };

  private lastPersistedSignature: string | null = null;

  public onClose(): void {
    this.close.emit();
  }

  public selectMode(mode: StartMode): void {
    this.selectedMode = mode;
    this.applyEvaluateFlagForMode(mode);
    this.activeStep = 1;
    this.persistSettingsIfChanged();
  }

  public nextStep(): void {
    if (!this.selectedMode) {
      return;
    }
    this.activeStep = this.isHierflIncluded() ? 2 : 3;
    this.applyEvaluateFlagForMode(this.selectedMode);
  }

  public nextFromHierfl(): void {
    if (!this.isHierflIncluded()) {
      return;
    }
    this.activeStep = 3;
    this.applyEvaluateFlagForMode(this.selectedMode);
  }

  public previousStep(): void {
    this.activeStep = 1;
    this.applyEvaluateFlagForMode(this.selectedMode);
  }

  public previousFromSpyker(): void {
    this.activeStep = this.isHierflIncluded() ? 2 : 1;
    this.applyEvaluateFlagForMode(this.selectedMode);
  }

  public isHierflIncluded(): boolean {
    return this.selectedMode === 'hierfl' || this.selectedMode === 'both';
  }

  public isSpykerIncluded(): boolean {
    return this.selectedMode === 'spyker' || this.selectedMode === 'both';
  }

  public canStartFromHierflStep(): boolean {
    return this.selectedMode === 'hierfl';
  }

  public onRun(): void {
    if (!this.selectedMode) {
      return;
    }

    this.run.emit({
      mode: this.selectedMode,
      hierfl: {
        trainingConfig: {
          epochs: this.hierflSettings.epochs,
          lr: this.hierflSettings.lr,
          modelComplexity: this.hierflSettings.modelComplexity,
          batchSize: this.hierflSettings.batchSize,
        },
        simulationSettings: {
          runTimeLimit: this.hierflSettings.runTimeLimit,
          evalInterval: this.hierflSettings.evalInterval,
          gpuBudget: this.hierflSettings.gpuBudget,
          seed: this.hierflSettings.seed,
          outputFilename: this.hierflSettings.outputFilename,
          evaluateModel: this.evaluateAfterRunByArchitecture.hierfl,
        },
      },
      spyker: {
        trainingConfig: {
          epochs: this.spykerSettings.epochs,
          lr: this.spykerSettings.lr,
          modelComplexity: this.spykerSettings.modelComplexity,
          batchSize: this.spykerSettings.batchSize,
        },
        simulationSettings: {
          runTimeLimit: this.spykerSettings.runTimeLimit,
          evalInterval: this.spykerSettings.evalInterval,
          gpuBudget: this.spykerSettings.gpuBudget,
          seed: this.spykerSettings.seed,
          idleTokenDelay: this.spykerSettings.idleTokenDelay,
          outputFilename: this.spykerSettings.outputFilename,
          evaluateModel: this.evaluateAfterRunByArchitecture.spyker,
        },
        spykerConfig: {
          decayBeta: this.spykerSettings.decayBeta,
          minLearningRate: this.spykerSettings.minLearningRate,
          hInter: this.spykerSettings.hInter,
          hIntra: this.spykerSettings.hIntra,
          sigmoidPhi: this.spykerSettings.sigmoidPhi,
          serverLearningRate: this.spykerSettings.serverLearningRate,
          tcpRtoDelay: this.spykerSettings.tcpRtoDelay,
        },
      },
    });
  }

  public ngOnChanges(changes: SimpleChanges): void {
    if (changes['hierflGraphId']) {
      this.restoreHierflSettings();
    }
    if (changes['spykerGraphId']) {
      this.restoreSpykerSettings();
    }
    this.applyEvaluateFlagForMode(this.selectedMode);
    this.persistSettingsIfChanged();
  }

  public ngOnInit(): void {
    this.restoreHierflSettings();
    this.restoreSpykerSettings();
    this.applyEvaluateFlagForMode(this.selectedMode);
    this.persistSettingsIfChanged();
  }

  public onSettingsChanged(): void {
    this.persistSettingsIfChanged();
  }

  public onEvaluateAfterRunChanged(value: boolean): void {
    this.evaluateAfterRun = value;

    if (this.selectedMode === 'hierfl') {
      this.evaluateAfterRunByArchitecture.hierfl = value;
    } else if (this.selectedMode === 'spyker') {
      this.evaluateAfterRunByArchitecture.spyker = value;
    } else if (this.selectedMode === 'both') {
      this.evaluateAfterRunByArchitecture.hierfl = value;
      this.evaluateAfterRunByArchitecture.spyker = value;
    }

    this.persistSettingsIfChanged();
  }

  public formatDecimal(value: number): string {
    return Number.isFinite(value) ? value.toString() : '';
  }

  public parseDecimalInput(value: string, fallback: number): number {
    const normalized = value.trim().replace(',', '.');
    const parsed = Number(normalized);
    return Number.isFinite(parsed) ? parsed : fallback;
  }

  private persistSettingsIfChanged(): void {
    const signature = JSON.stringify({
      selectedMode: this.selectedMode,
      evaluateAfterRun: this.evaluateAfterRun,
      evaluateAfterRunByArchitecture: this.evaluateAfterRunByArchitecture,
      hierflGraphId: this.hierflGraphId,
      spykerGraphId: this.spykerGraphId,
      hierflSettings: this.hierflSettings,
      spykerSettings: this.spykerSettings,
    });
    if (signature === this.lastPersistedSignature) {
      return;
    }

    this.lastPersistedSignature = signature;
    this.persistArchitectureParams(
      'hierfl',
      this.hierflGraphId,
      this.hierflSettings,
      this.evaluateAfterRunByArchitecture.hierfl,
    );
    this.persistArchitectureParams(
      'spyker',
      this.spykerGraphId,
      this.spykerSettings,
      this.evaluateAfterRunByArchitecture.spyker,
    );
  }

  private restoreHierflSettings(): void {
    const params = this.readSavedParams('hierfl', this.hierflGraphId);
    if (!params) {
      return;
    }
    this.hierflSettings = {
      ...this.hierflSettings,
      ...params.settings,
    };
    this.evaluateAfterRunByArchitecture.hierfl = params.evaluateAfterRun === true;
  }

  private restoreSpykerSettings(): void {
    const params = this.readSavedParams('spyker', this.spykerGraphId);
    if (!params) {
      return;
    }
    this.spykerSettings = {
      ...this.spykerSettings,
      ...params.settings,
    };
    this.evaluateAfterRunByArchitecture.spyker = params.evaluateAfterRun === true;
  }

  private applyEvaluateFlagForMode(mode: StartMode | null): void {
    if (mode === 'hierfl') {
      this.evaluateAfterRun = this.evaluateAfterRunByArchitecture.hierfl;
      return;
    }
    if (mode === 'spyker') {
      this.evaluateAfterRun = this.evaluateAfterRunByArchitecture.spyker;
      return;
    }
    if (mode === 'both') {
      this.evaluateAfterRun = this.activeStep === 2
        ? this.evaluateAfterRunByArchitecture.hierfl
        : this.evaluateAfterRunByArchitecture.spyker;
    }
  }

  private persistArchitectureParams(
    architecture: 'hierfl' | 'spyker',
    graphId: number | null,
    settings: Record<string, unknown>,
    evaluateAfterRun: boolean,
  ): void {
    if (graphId === null || !Number.isFinite(graphId)) {
      return;
    }
    localStorage.setItem(
      this.storageKey(architecture, graphId),
      JSON.stringify({
        evaluateAfterRun,
        settings,
      }),
    );
  }

  private readSavedParams(
    architecture: 'hierfl' | 'spyker',
    graphId: number | null
  ): { evaluateAfterRun?: boolean; settings?: Record<string, unknown> } | null {
    if (graphId === null || !Number.isFinite(graphId)) {
      return null;
    }
    const raw = localStorage.getItem(this.storageKey(architecture, graphId));
    if (!raw) {
      return null;
    }
    try {
      const parsed = JSON.parse(raw) as { evaluateAfterRun?: boolean; settings?: Record<string, unknown> };
      if (parsed && typeof parsed === 'object') {
        return parsed;
      }
    } catch {
      return null;
    }
    return null;
  }

  private storageKey(architecture: 'hierfl' | 'spyker', graphId: number): string {
    return `fedsim.start-params.${architecture}.${graphId}`;
  }
}
