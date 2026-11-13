import { Injectable } from '@angular/core';
import { GraphService } from '../graph.service';
import { HierflGraphHistoryService } from './hierfl-graph-history.service';

@Injectable({
  providedIn: 'root',
})
export class HierflGraphService extends GraphService<HierflGraphHistoryService> {
  constructor(graphHistory: HierflGraphHistoryService) {
    super(graphHistory, 'hierfl');
  }
}
