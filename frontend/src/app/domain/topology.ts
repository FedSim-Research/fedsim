/** Federated-learning architectures the simulator supports. */
export type Architecture = 'spyker' | 'hierfl';

/** Node kinds as the backend names them. */
export type NodeKind = 'ClientNode' | 'ServerNode' | 'SuperServerNode';

export const NODE_KINDS: readonly NodeKind[] = ['ClientNode', 'ServerNode', 'SuperServerNode'];

export function isNodeKind(value: unknown): value is NodeKind {
  return NODE_KINDS.includes(value as NodeKind);
}
