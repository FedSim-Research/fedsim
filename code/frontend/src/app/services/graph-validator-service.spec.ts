import { TestBed } from '@angular/core/testing';

import { GraphValidatorService } from './graph-validator-service';

describe('GraphValidatorService', () => {
  let service: GraphValidatorService;

  beforeEach(() => {
    TestBed.configureTestingModule({});
    service = TestBed.inject(GraphValidatorService);
  });

  it('should be created', () => {
    expect(service).toBeTruthy();
  });
});
