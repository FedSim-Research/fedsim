import { parseRunArchitecture } from './topology';

describe('parseRunArchitecture', () => {
  it('maps both backend names of the hierarchical architecture to hierfl', () => {
    expect(parseRunArchitecture('hierarchical')).toBe('hierfl');
    expect(parseRunArchitecture('hierfl')).toBe('hierfl');
  });

  it('keeps spyker and both', () => {
    expect(parseRunArchitecture('spyker')).toBe('spyker');
    expect(parseRunArchitecture('both')).toBe('both');
  });

  it.each(['p2p', '', 'Spyker', null, undefined, 3])('returns null for %s', (value) => {
    expect(parseRunArchitecture(value)).toBeNull();
  });
});
