import { NodePositionChange } from 'ngx-vflow';
import { ArchitectureGraph } from './graph-workspace.service';
import { NodeDrag } from './node-drag';

describe('NodeDrag', () => {
  const nodes = [
    { id: 'a', point: { x: 0, y: 0 } },
    { id: 'b', point: { x: 10, y: 10 } },
    { id: 'c', point: { x: 50, y: 50 } },
  ];
  const graph = { nodes: () => nodes, previewPositions: vi.fn(), moveNodes: vi.fn() };
  const at = (id: string, x: number, y: number): NodePositionChange => ({ type: 'position', id, point: { x, y } });
  let target: EventTarget;
  let drag: NodeDrag;

  function create(selection: string[]) {
    drag = new NodeDrag(() => graph as unknown as ArchitectureGraph, () => new Set(selection), target as Window);
  }
  const press = () => target.dispatchEvent(new Event('pointerdown'));
  const release = async () => {
    target.dispatchEvent(new Event('pointerup'));
    await vi.runAllTimersAsync();
  };

  beforeEach(() => {
    vi.useFakeTimers();
    target = new EventTarget();
    graph.previewPositions.mockClear();
    graph.moveNodes.mockClear();
  });

  afterEach(() => {
    drag.destroy();
    vi.useRealTimers();
  });

  it('moves selected nodes by the total offset and commits once', async () => {
    create(['a', 'b']);
    press();
    drag.handle([at('a', 5, 5)]);
    drag.handle([at('a', 20, 30)]);
    expect(graph.previewPositions).toHaveBeenLastCalledWith([at('b', 30, 40)]);

    await release();
    expect(graph.moveNodes).toHaveBeenCalledTimes(1);
    expect(graph.moveNodes).toHaveBeenCalledWith([at('a', 20, 30), at('b', 30, 40)]);
  });

  it('ignores the echoes of follower previews', async () => {
    create(['a', 'b']);
    press();
    drag.handle([at('a', 5, 5)]);
    drag.handle([at('b', 15, 15)]);
    await release();

    expect(graph.moveNodes).toHaveBeenCalledWith([at('a', 5, 5), at('b', 15, 15)]);
  });

  it('takes the last position reported after the pointer was released', async () => {
    create(['a']);
    press();
    drag.handle([at('a', 5, 5)]);
    target.dispatchEvent(new Event('pointerup'));
    drag.handle([at('a', 9, 9)]);
    await vi.runAllTimersAsync();

    expect(graph.moveNodes).toHaveBeenCalledWith([at('a', 9, 9)]);
  });

  it('does not treat position changes made by the app as a drag', async () => {
    create(['a']);
    drag.handle([at('a', 100, 100)]);
    press();
    await release();

    expect(graph.moveNodes).not.toHaveBeenCalled();
  });

  it('moves only the dragged node when it is not part of the selection', async () => {
    create(['b', 'c']);
    press();
    drag.handle([at('a', 5, 5)]);
    await release();

    expect(graph.moveNodes).toHaveBeenCalledWith([at('a', 5, 5)]);
  });
});
