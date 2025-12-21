import { TestBed } from '@angular/core/testing';

import { GraphServiceSpyker } from './graph-service-spyker';

describe('GraphServiceSpyker', () => {
  let service: GraphServiceSpyker;

  beforeEach(() => {
    TestBed.configureTestingModule({});
    service = TestBed.inject(GraphServiceSpyker);
  });

  it('should be created', () => {
    expect(service).toBeTruthy();
  });
});
