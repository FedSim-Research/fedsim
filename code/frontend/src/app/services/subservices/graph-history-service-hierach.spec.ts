import { TestBed } from '@angular/core/testing';

import { GraphHistoryServiceHierach } from './graph-history-service-hierach';

describe('GraphHistoryServiceHierach', () => {
  let service: GraphHistoryServiceHierach;

  beforeEach(() => {
    TestBed.configureTestingModule({});
    service = TestBed.inject(GraphHistoryServiceHierach);
  });

  it('should be created', () => {
    expect(service).toBeTruthy();
  });
});
