import { GraphApiService, PresetResponse } from '../../api/graph-api.service';
import { Architecture, NodeKind } from '../../domain/topology';

export interface PresetItem<T> {
  id: number;
  name: string;
  config: T;
}

export interface PresetDraft<T> {
  presetName: string;
  config: T;
}

export interface PresetLibraryOptions<T> {
  nodeKind: NodeKind;
  /** Used for generated names such as "Server Node Preset 3". */
  label: string;
  defaults: T;
  /** Name for a preset saved straight from the sidebar settings. */
  nameFor?: (config: T) => string;
}

/** Saved node presets of one node kind, plus the state of their editor popup. */
export class PresetLibrary<T extends object> {
  public items: PresetItem<T>[] = [];
  public selectedIndex: number | null = null;
  public popupOpen = false;
  public draft: PresetDraft<T>;

  constructor(
    private readonly api: GraphApiService,
    private readonly options: PresetLibraryOptions<T>,
  ) {
    this.draft = { presetName: '', config: { ...options.defaults } };
  }

  public get selected(): PresetItem<T> | null {
    return this.selectedIndex === null ? null : this.items[this.selectedIndex] ?? null;
  }

  public get selectedName(): string {
    return this.selected?.name ?? 'None';
  }

  public async load(architecture: Architecture): Promise<void> {
    const presets = await this.api.listPresets(architecture, this.options.nodeKind);
    this.items = presets.map((preset) => this.toItem(preset));
    this.selectedIndex = null;
  }

  public openPopup(current: T): void {
    this.draft = { presetName: '', config: { ...current } };
    this.selectedIndex = null;
    this.popupOpen = true;
  }

  public closePopup(): void {
    this.popupOpen = false;
  }

  /** Selects a preset and returns a copy of its config, or null for an unknown index. */
  public select(index: number): T | null {
    const item = this.items[index];
    if (!item) {
      return null;
    }
    this.selectedIndex = index;
    this.draft = { presetName: item.name, config: { ...item.config } };
    return { ...item.config };
  }

  /** Stores the popup draft: updates the selected preset or creates a new one. */
  public async saveDraft(architecture: Architecture): Promise<PresetItem<T>> {
    const name = this.draft.presetName.trim() || this.generatedName();
    const config = { ...this.draft.config };
    const selected = this.selected;
    if (selected && this.selectedIndex !== null) {
      return this.replace(this.selectedIndex, await this.api.updatePreset(selected.id, { name, config: asRecord(config) }));
    }
    return this.create(architecture, name, config);
  }

  /** Creates a preset from the sidebar settings, named after them where possible. */
  public async saveConfig(architecture: Architecture, config: T): Promise<PresetItem<T>> {
    const name = this.options.nameFor?.(config).trim() || this.generatedName();
    return this.create(architecture, name, config);
  }

  public async createDefault(architecture: Architecture): Promise<PresetItem<T>> {
    return this.create(architecture, this.generatedName(), { ...this.options.defaults });
  }

  public async updateSelected(config: T): Promise<PresetItem<T> | null> {
    const selected = this.selected;
    if (!selected || this.selectedIndex === null) {
      return null;
    }
    return this.replace(this.selectedIndex, await this.api.updatePreset(selected.id, { config: asRecord(config) }));
  }

  public async remove(index: number): Promise<void> {
    const item = this.items[index];
    if (!item) {
      return;
    }
    await this.api.deletePreset(item.id);
    this.items.splice(index, 1);
    if (this.selectedIndex === index) {
      this.selectedIndex = null;
    } else if (this.selectedIndex !== null && this.selectedIndex > index) {
      this.selectedIndex -= 1;
    }
  }

  private async create(architecture: Architecture, name: string, config: T): Promise<PresetItem<T>> {
    const created = await this.api.createPreset({
      architecture,
      node_type: this.options.nodeKind,
      name,
      config: asRecord(config),
    });
    this.items.push(this.toItem(created));
    this.select(this.items.length - 1);
    return this.items[this.items.length - 1];
  }

  private replace(index: number, preset: PresetResponse): PresetItem<T> {
    this.items[index] = this.toItem(preset);
    this.select(index);
    return this.items[index];
  }

  private generatedName(): string {
    return `${this.options.label} Preset ${this.items.length + 1}`;
  }

  private toItem(preset: PresetResponse): PresetItem<T> {
    return { id: preset.preset_id, name: preset.name, config: { ...this.options.defaults, ...(preset.config as Partial<T>) } };
  }
}

function asRecord(config: object): Record<string, unknown> {
  return { ...config } as Record<string, unknown>;
}
