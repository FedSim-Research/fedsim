import { createGraphNode } from './node-factory';

describe('createGraphNode', () => {
  it('stores canvas points as plain coordinates', () => {
    // Like DOMPoint: coordinates are prototype getters, invisible to spreading.
    class CanvasPoint {
      get x() { return 12; }
      get y() { return 34; }
    }
    const node = createGraphNode({ id: 'n', kind: 'ClientNode', architecture: 'hierfl', point: new CanvasPoint(), config: {} });

    expect({ ...node.point }).toEqual({ x: 12, y: 34 });
    expect(JSON.parse(JSON.stringify(node.point))).toEqual({ x: 12, y: 34 });
  });
});
