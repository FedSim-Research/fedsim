import { Injectable, inject } from '@angular/core';
import { Architecture } from '../domain/topology';
import { HierflGraphService } from './topologies/hierfl-graph.service';
import { SpykerGraphService } from './topologies/spyker-graph.service';

export type ArchitectureGraph = SpykerGraphService | HierflGraphService;

/** Gives access to the editor graph of each architecture. */
@Injectable({ providedIn: 'root' })
export class GraphWorkspace {
  private readonly graphs: Record<Architecture, ArchitectureGraph> = {
    spyker: inject(SpykerGraphService),
    hierfl: inject(HierflGraphService),
  };

  public graphFor(architecture: Architecture): ArchitectureGraph {
    return this.graphs[architecture];
  }
}
