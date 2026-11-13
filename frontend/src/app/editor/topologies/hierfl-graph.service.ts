import { Injectable } from '@angular/core';
import { GraphService } from '../graph.service';

@Injectable({
  providedIn: 'root',
})
export class HierflGraphService extends GraphService {
  constructor() {
    super('hierfl');
  }
}
