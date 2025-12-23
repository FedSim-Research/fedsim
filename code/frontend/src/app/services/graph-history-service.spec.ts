import { TestBed } from '@angular/core/testing';

import { GraphHistoryService } from './graph-history-service';

describe('GraphHistoryService', () => {
  let service: GraphHistoryService;

  beforeEach(() => {
    TestBed.configureTestingModule({});
    service = TestBed.inject(GraphHistoryService);
  });

  it('should be created', () => {
    expect(service).toBeTruthy();
  });
});
