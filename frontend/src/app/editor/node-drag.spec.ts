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
  const move = (x: number, y: number): NodePositionChange[] => [{ type: 'position', id: 'a', point: { x, y } }];

  beforeEach(() => {
    graph.previewPositions.mockClear();
    graph.moveNodes.mockClear();
  });

  it('moves selected nodes by the total offset and commits once', () => {
    const drag = new NodeDrag(() => graph as unknown as ArchitectureGraph, () => new Set(['a', 'b']));
    drag.handle(move(5, 5));
    drag.handle(move(20, 30));

    expect(graph.previewPositions).toHaveBeenLastCalledWith([{ type: 'position', id: 'b', point: { x: 30, y: 40 } }]);
    window.dispatchEvent(new Event('pointerup'));
    window.dispatchEvent(new Event('mouseup'));

    expect(graph.moveNodes).toHaveBeenCalledTimes(1);
    expect(graph.moveNodes).toHaveBeenCalledWith([...move(20, 30), { type: 'position', id: 'b', point: { x: 30, y: 40 } }]);
  });

  it('moves only the dragged node when it is not part of the selection', () => {
    const drag = new NodeDrag(() => graph as unknown as ArchitectureGraph, () => new Set(['b', 'c']));
    drag.handle(move(5, 5));
    drag.finish();

    expect(graph.moveNodes).toHaveBeenCalledWith(move(5, 5));
  });
});
