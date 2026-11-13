import { Component, EventEmitter, Input, OnInit, Output, SimpleChanges, inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { InputNumberModule } from 'primeng/inputnumber';
import { InputTextModule } from 'primeng/inputtext';
import { StepperModule } from 'primeng/stepper';
import { GraphApiService } from '../../api/graph-api.service';

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
  dataset: string;
  seedSet: number[];
  repetitions: number;
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

type PersistedStartParams = {
  evaluateAfterRun?: boolean;
  settings?: Record<string, unknown>;
  updatedAt?: number;
};

@Component({
  selector: 'app-start-popup',
  standalone: true,
  imports: [CommonModule, FormsModule, InputNumberModule, InputTextModule, StepperModule],
  templateUrl: './start-popup.html',
  styleUrl: './start-popup.css',
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
    dataset: 'uoft-cs/cifar10',
    seedSetText: '42, 43, 44, 45, 46',
    repetitions: 5,
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
    dataset: 'uoft-cs/cifar10',
    seedSetText: '42, 43, 44, 45, 46',
    repetitions: 5,
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
  private api = inject(GraphApiService);
  private backendSyncTimers: Partial<Record<'hierfl' | 'spyker', ReturnType<typeof setTimeout>>> = {};

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

    const hierflSeedSet = this.parseSeedSetInput(this.hierflSettings.seedSetText) ?? [];
    const spykerSeedSet = this.parseSeedSetInput(this.spykerSettings.seedSetText) ?? [];

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
          dataset: this.hierflSettings.dataset,
          seedSet: hierflSeedSet,
          repetitions: hierflSeedSet.length,
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
          dataset: this.spykerSettings.dataset,
          seedSet: spykerSeedSet,
          repetitions: spykerSeedSet.length,
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

  public updateSeedSet(architecture: 'hierfl' | 'spyker', value: string): void {
    const target = architecture === 'hierfl' ? this.hierflSettings : this.spykerSettings;
    target.seedSetText = value;
    target.repetitions = this.countSeeds(value);
    this.onSettingsChanged();
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
      void this.reconcileWithBackend('hierfl', this.hierflGraphId, null);
      return;
    }
    this.applyPersistedParams('hierfl', params);
    void this.reconcileWithBackend('hierfl', this.hierflGraphId, params);
  }

  private restoreSpykerSettings(): void {
    const params = this.readSavedParams('spyker', this.spykerGraphId);
    if (!params) {
      void this.reconcileWithBackend('spyker', this.spykerGraphId, null);
      return;
    }
    this.applyPersistedParams('spyker', params);
    void this.reconcileWithBackend('spyker', this.spykerGraphId, params);
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
    const payload: PersistedStartParams = {
      evaluateAfterRun,
      settings,
      updatedAt: Date.now(),
    };
    localStorage.setItem(
      this.storageKey(architecture, graphId),
      JSON.stringify(payload),
    );
    this.scheduleBackendSync(architecture, graphId, payload);
  }

  private readSavedParams(
    architecture: 'hierfl' | 'spyker',
    graphId: number | null
  ): PersistedStartParams | null {
    if (graphId === null || !Number.isFinite(graphId)) {
      return null;
    }
    const raw = localStorage.getItem(this.storageKey(architecture, graphId));
    if (!raw) {
      return null;
    }
    try {
      const parsed = JSON.parse(raw) as PersistedStartParams;
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

  private scheduleBackendSync(
    architecture: 'hierfl' | 'spyker',
    graphId: number,
    payload: PersistedStartParams,
  ): void {
    const existingTimer = this.backendSyncTimers[architecture];
    if (existingTimer) {
      clearTimeout(existingTimer);
    }

    this.backendSyncTimers[architecture] = setTimeout(() => {
      void this.syncArchitectureParamsToBackend(graphId, payload);
    }, 500);
  }

  private async syncArchitectureParamsToBackend(
    graphId: number,
    payload: PersistedStartParams,
  ): Promise<void> {
    try {
      await this.api.patchGraphMetadata(graphId, {
        patch: {
          start_params: payload,
        },
      });
    } catch {
      // Keep local persistence as fallback; the next settings change retries sync.
    }
  }

  private extractBackendStartParams(
    graphMetadata: Record<string, unknown> | null | undefined,
  ): PersistedStartParams | null {
    if (!graphMetadata || typeof graphMetadata !== 'object') {
      return null;
    }
    const candidate = graphMetadata['start_params'];
    if (!candidate || typeof candidate !== 'object') {
      return null;
    }
    return candidate as PersistedStartParams;
  }

  private applyPersistedParams(architecture: 'hierfl' | 'spyker', params: PersistedStartParams): void {
    const currentSettings = architecture === 'hierfl' ? this.hierflSettings : this.spykerSettings;
    const normalizedSettings = this.normalizeSavedSettings(params.settings, currentSettings.seedSetText);
    const mergedSettings = this.mergePersistedSettings(currentSettings, normalizedSettings);

    if (architecture === 'hierfl') {
      this.hierflSettings = mergedSettings as typeof this.hierflSettings;
      this.hierflSettings.repetitions = this.countSeeds(this.hierflSettings.seedSetText);
      this.evaluateAfterRunByArchitecture.hierfl = params.evaluateAfterRun === true;
      return;
    }

    this.spykerSettings = mergedSettings as typeof this.spykerSettings;
    this.spykerSettings.repetitions = this.countSeeds(this.spykerSettings.seedSetText);
    this.evaluateAfterRunByArchitecture.spyker = params.evaluateAfterRun === true;
  }

  private async reconcileWithBackend(
    architecture: 'hierfl' | 'spyker',
    graphId: number | null,
    localParams: PersistedStartParams | null,
  ): Promise<void> {
    if (graphId === null || !Number.isFinite(graphId)) {
      return;
    }

    try {
      const graph = await this.api.getGraph(graphId);
      const backendParams = this.extractBackendStartParams(graph.metadata);

      if (!backendParams) {
        if (localParams) {
          this.scheduleBackendSync(architecture, graphId, localParams);
        }
        return;
      }

      const localTs = typeof localParams?.updatedAt === 'number' ? localParams.updatedAt : 0;
      const backendTs = typeof backendParams.updatedAt === 'number' ? backendParams.updatedAt : 0;

      if (backendTs >= localTs) {
        this.applyPersistedParams(architecture, backendParams);
        localStorage.setItem(this.storageKey(architecture, graphId), JSON.stringify(backendParams));
      } else if (localParams) {
        this.scheduleBackendSync(architecture, graphId, localParams);
      }

      this.applyEvaluateFlagForMode(this.selectedMode);
      this.persistSettingsIfChanged();
    } catch {
      // Local settings remain authoritative if backend cannot be reached.
    }
  }

  private normalizeSavedSettings(
    settings: Record<string, unknown> | undefined,
    fallbackSeedSetText: string,
  ): Record<string, unknown> {
    const normalized = { ...(settings ?? {}) };
    normalized['seedSetText'] = this.extractSeedSetText(settings, fallbackSeedSetText);
    normalized['repetitions'] = this.countSeeds(String(normalized['seedSetText']));
    delete normalized['seed'];
    delete normalized['seedSet'];
    return normalized;
  }

  /** Takes over stored values only for known settings of the same type. */
  private mergePersistedSettings<T extends Record<string, unknown>>(
    currentSettings: T,
    persistedSettings: Record<string, unknown>,
  ): T {
    const merged: Record<string, unknown> = { ...currentSettings };
    for (const [key, current] of Object.entries(currentSettings)) {
      const stored = persistedSettings[key];
      const sameType = typeof stored === typeof current
        && (typeof stored !== 'number' || Number.isFinite(stored));
      if (sameType) {
        merged[key] = stored;
      }
    }
    return merged as T;
  }

  private extractSeedSetText(
    settings: Record<string, unknown> | undefined,
    fallbackSeedSetText: string,
  ): string {
    const rawSeedSetText = settings?.['seedSetText'];
    if (typeof rawSeedSetText === 'string' && rawSeedSetText.trim()) {
      return rawSeedSetText;
    }

    const rawSeedSet = settings?.['seedSet'];
    if (Array.isArray(rawSeedSet)) {
      const values = rawSeedSet
        .map((value) => Number(value))
        .filter((value) => Number.isInteger(value) && value >= 0);
      if (values.length) {
        return values.join(', ');
      }
    }

    const rawSeed = settings?.['seed'];
    if (Number.isInteger(rawSeed) && Number(rawSeed) >= 0) {
      return String(rawSeed);
    }

    return fallbackSeedSetText;
  }

  private countSeeds(value: string): number {
    const parsed = this.parseSeedSetInput(value);
    return parsed?.length ?? 0;
  }

  private parseSeedSetInput(value: string): number[] | null {
    const tokens = value
      .split(/[\s,;]+/)
      .map((token) => token.trim())
      .filter((token) => token.length > 0);
    if (!tokens.length) {
      return null;
    }

    const seeds: number[] = [];
    for (const token of tokens) {
      if (!/^\d+$/.test(token)) {
        return null;
      }
      const seed = Number(token);
      if (!Number.isInteger(seed) || seed < 0) {
        return null;
      }
      seeds.push(seed);
    }

    return seeds;
  }
}
