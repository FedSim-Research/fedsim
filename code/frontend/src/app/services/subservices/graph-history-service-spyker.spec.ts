import { TestBed } from '@angular/core/testing';

import { GraphHistoryServiceSpyker } from './graph-history-service-spyker';

describe('GraphHistoryServiceSpyker', () => {
  let service: GraphHistoryServiceSpyker;

  beforeEach(() => {
    TestBed.configureTestingModule({});
    service = TestBed.inject(GraphHistoryServiceSpyker);
  });

  it('should be created', () => {
    expect(service).toBeTruthy();
  });
});
