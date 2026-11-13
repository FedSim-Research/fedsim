import { resolveAppConfig } from './app-config';

describe('resolveAppConfig', () => {
  const origin = 'https://fedsim.example';

  it('falls back to the environment defaults', () => {
    expect(resolveAppConfig({}, origin)).toEqual({
      apiBaseUrl: 'http://localhost:8000',
      grafanaBaseUrl: 'http://localhost:3000',
    });
  });

  it('serves Grafana next to a proxied API', () => {
    expect(resolveAppConfig({ FEDSIM_API_BASE_URL: '/api/' }, origin)).toEqual({
      apiBaseUrl: '/api',
      grafanaBaseUrl: 'https://fedsim.example/grafana',
    });
  });

  it('prefers explicitly configured values', () => {
    const config = resolveAppConfig(
      { FEDSIM_API_BASE_URL: 'https://api.example', FEDSIM_GRAFANA_BASE_URL: ' https://grafana.example/ ' },
      origin,
    );
    expect(config).toEqual({ apiBaseUrl: 'https://api.example', grafanaBaseUrl: 'https://grafana.example' });
  });
});
