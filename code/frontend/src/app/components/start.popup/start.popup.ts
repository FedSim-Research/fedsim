import { Component, EventEmitter, Output } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { StepperModule } from 'primeng/stepper';

type StartMode = 'spyker' | 'hierfl' | 'both';

type CommonTrainingConfig = {
  epochs: number;
  lr: number;
  modelComplexity: number;
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
export class StartPopup {
  @Output() close = new EventEmitter<void>();
  @Output() run = new EventEmitter<RunPayload>();

  public activeStep = 1;
  public selectedMode: StartMode | null = null;
  public evaluateAfterRun = false;

  public hierflSettings = {
    epochs: 1,
    lr: 0.005,
    modelComplexity: 1.0,
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

  public onClose(): void {
    this.close.emit();
  }

  public selectMode(mode: StartMode): void {
    this.selectedMode = mode;
    this.activeStep = 1;
  }

  public nextStep(): void {
    if (!this.selectedMode) {
      return;
    }
    this.activeStep = this.isHierflIncluded() ? 2 : 3;
  }

  public nextFromHierfl(): void {
    if (!this.isHierflIncluded()) {
      return;
    }
    this.activeStep = 3;
  }

  public previousStep(): void {
    this.activeStep = 1;
  }

  public previousFromSpyker(): void {
    this.activeStep = this.isHierflIncluded() ? 2 : 1;
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
        },
        simulationSettings: {
          runTimeLimit: this.hierflSettings.runTimeLimit,
          evalInterval: this.hierflSettings.evalInterval,
          gpuBudget: this.hierflSettings.gpuBudget,
          seed: this.hierflSettings.seed,
          outputFilename: this.hierflSettings.outputFilename,
          evaluateModel: this.evaluateAfterRun,
        },
      },
      spyker: {
        trainingConfig: {
          epochs: this.spykerSettings.epochs,
          lr: this.spykerSettings.lr,
          modelComplexity: this.spykerSettings.modelComplexity,
        },
        simulationSettings: {
          runTimeLimit: this.spykerSettings.runTimeLimit,
          evalInterval: this.spykerSettings.evalInterval,
          gpuBudget: this.spykerSettings.gpuBudget,
          seed: this.spykerSettings.seed,
          idleTokenDelay: this.spykerSettings.idleTokenDelay,
          outputFilename: this.spykerSettings.outputFilename,
          evaluateModel: this.evaluateAfterRun,
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

  public formatDecimal(value: number): string {
    return Number.isFinite(value) ? value.toString() : '';
  }

  public parseDecimalInput(value: string, fallback: number): number {
    const normalized = value.trim().replace(',', '.');
    const parsed = Number(normalized);
    return Number.isFinite(parsed) ? parsed : fallback;
  }
}
