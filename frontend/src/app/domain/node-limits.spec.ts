import { nodeLimitViolation } from './node-limits';

describe('nodeLimitViolation', () => {
  it('allows one super server in a hierarchical graph', () => {
    expect(nodeLimitViolation('hierfl', ['ServerNode'], ['SuperServerNode'])).toBeNull();
    expect(nodeLimitViolation('hierfl', ['SuperServerNode'], ['SuperServerNode'])).toContain('Only one');
    expect(nodeLimitViolation('hierfl', [], ['SuperServerNode', 'SuperServerNode'])).toContain('Only one');
  });

  it('forbids super servers in spyker graphs', () => {
    expect(nodeLimitViolation('spyker', [], ['SuperServerNode'])).toContain('No super server');
  });

  it('does not limit servers and clients', () => {
    expect(nodeLimitViolation('spyker', ['ServerNode'], ['ServerNode', 'ClientNode'])).toBeNull();
  });
});
