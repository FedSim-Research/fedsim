import { TestBed } from '@angular/core/testing';

import { GraphServiceHierach } from './graph-service-hierach';

describe('GraphServiceHierach', () => {
  let service: GraphServiceHierach;

  beforeEach(() => {
    TestBed.configureTestingModule({});
    service = TestBed.inject(GraphServiceHierach);
  });

  it('should be created', () => {
    expect(service).toBeTruthy();
  });
});
