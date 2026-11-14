import { GraphApiService } from '../../api/graph-api.service';
import { PresetLibrary } from './preset-library';

type ServerConfig = { name: string; uploadMbps: number };

describe('PresetLibrary', () => {
  let nextId = 0;
  const api = {
    listPresets: vi.fn(),
    createPreset: vi.fn(async (body) => ({ preset_id: ++nextId, ...body })),
    updatePreset: vi.fn(async (id, body) => ({ preset_id: id, name: body.name ?? 'kept', config: body.config })),
    deletePreset: vi.fn(async () => undefined),
  };
  let library: PresetLibrary<ServerConfig>;

  beforeEach(() => {
    nextId = 0;
    Object.values(api).forEach((mock) => mock.mockClear());
    library = new PresetLibrary<ServerConfig>(api as unknown as GraphApiService, {
      nodeKind: 'ServerNode',
      label: 'Server Node',
      defaults: { name: 'Server', uploadMbps: 20 },
      nameFor: (config) => config.name,
    });
  });

  it('fills missing config values with defaults when loading', async () => {
    api.listPresets.mockResolvedValue([{ preset_id: 4, name: 'Fast', config: { uploadMbps: 99 } }]);
    await library.load('spyker');

    expect(library.items).toEqual([{ id: 4, name: 'Fast', config: { name: 'Server', uploadMbps: 99 } }]);
    expect(library.selectedName).toBe('None');
  });

  it('creates a new preset from the draft and selects it', async () => {
    library.openPopup({ name: 'Edge', uploadMbps: 5 });
    const item = await library.saveDraft('hierfl');

    expect(api.createPreset).toHaveBeenCalledWith({
      architecture: 'hierfl', node_type: 'ServerNode', name: 'Server Node Preset 1', config: { name: 'Edge', uploadMbps: 5 },
    });
    expect(library.selected).toBe(item);
  });

  it('updates the selected preset instead of creating another one', async () => {
    await library.saveConfig('hierfl', { name: 'Edge', uploadMbps: 5 });
    library.draft.config.uploadMbps = 7;
    await library.saveDraft('hierfl');

    expect(api.createPreset).toHaveBeenCalledTimes(1);
    expect(api.updatePreset).toHaveBeenCalledWith(1, { name: 'Edge', config: { name: 'Edge', uploadMbps: 7 } });
    expect(library.items).toHaveLength(1);
  });

  it('keeps the selection on the same preset after deleting an earlier one', async () => {
    await library.createDefault('spyker');
    await library.createDefault('spyker');
    await library.remove(0);

    expect(library.selectedIndex).toBe(0);
    expect(library.selected?.id).toBe(2);
  });
});
