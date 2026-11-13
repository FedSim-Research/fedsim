import { Architecture, NodeKind } from './topology';

/** Node kinds that may be linked directly, per architecture. Links are undirected. */
const ALLOWED_LINKS: Record<Architecture, ReadonlyArray<readonly [NodeKind, NodeKind]>> = {
  hierfl: [
    ['SuperServerNode', 'ServerNode'],
    ['ServerNode', 'ClientNode'],
  ],
  spyker: [
    ['ServerNode', 'ServerNode'],
    ['ServerNode', 'ClientNode'],
  ],
};

export function canLink(architecture: Architecture, first: string, second: string): boolean {
  return ALLOWED_LINKS[architecture].some(
    ([a, b]) => (a === first && b === second) || (a === second && b === first),
  );
}
