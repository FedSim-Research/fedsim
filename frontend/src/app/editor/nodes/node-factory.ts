import { Type } from '@angular/core';
import { CustomNodeComponent, StaticNode as Node } from 'ngx-vflow';
import { Architecture, NodeKind } from '../../domain/topology';
import { ClientNode } from './client-node/client-node';
import { ServerNode } from './server-node/server-node';
import { SuperServerNode } from './super-server-node/super-server-node';

/** Component that renders each node kind on the canvas. */
export const NODE_COMPONENTS: Record<NodeKind, Type<CustomNodeComponent>> = {
  ClientNode,
  ServerNode,
  SuperServerNode,
};

export interface GraphNodeInit {
  id: string;
  kind: NodeKind;
  architecture: Architecture;
  point: { x: number; y: number };
  config: Record<string, unknown>;
}

/** The single place where editor nodes are built, whatever their origin. */
export function createGraphNode({ id, kind, architecture, point, config }: GraphNodeInit): Node {
  return {
    id,
    point,
    type: NODE_COMPONENTS[kind],
    data: { type: kind, config, environment: architecture, selected: false },
  };
}
