import { canLink } from './link-rules';

describe('canLink', () => {
  it.each([
    ['hierfl', 'SuperServerNode', 'ServerNode', true],
    ['hierfl', 'ClientNode', 'ServerNode', true],
    ['hierfl', 'ServerNode', 'ServerNode', false],
    ['hierfl', 'SuperServerNode', 'ClientNode', false],
    ['spyker', 'ServerNode', 'ServerNode', true],
    ['spyker', 'ClientNode', 'ServerNode', true],
    ['spyker', 'SuperServerNode', 'ServerNode', false],
    ['spyker', 'ClientNode', 'ClientNode', false],
  ] as const)('%s: %s - %s -> %s', (architecture, first, second, expected) => {
    expect(canLink(architecture, first, second)).toBe(expected);
  });
});
