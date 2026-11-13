import { StaticNode } from 'ngx-vflow';
import { GraphHistory } from './graph-history';

describe('GraphHistory', () => {
  const state = (...ids: string[]) => ({
    nodes: ids.map((id) => ({ id, point: { x: 0, y: 0 }, type: 'default', data: { selected: true } }) as unknown as StaticNode),
    edges: [],
  });

  it('undoes and redoes committed states', () => {
    const history = new GraphHistory();
    history.saveState(state('a'));
    history.saveState(state('a', 'b'));

    history.undo();
    expect(history.getState().nodes.map((n) => n.id)).toEqual(['a']);
    history.redo();
    expect(history.getState().nodes.map((n) => n.id)).toEqual(['a', 'b']);
  });

  it('keeps only the configured number of undo steps', () => {
    const history = new GraphHistory(2);
    for (const id of ['a', 'b', 'c', 'd']) history.saveState(state(id));

    history.undo();
    history.undo();
    history.undo();
    expect(history.getState().nodes.map((n) => n.id)).toEqual(['b']);
  });

  it('does not store selection flags', () => {
    const history = new GraphHistory();
    history.saveState(state('a'));
    expect((history.getState().nodes[0] as { data?: { selected?: boolean } }).data?.selected).toBe(false);
  });
});
