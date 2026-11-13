import { InjectionToken } from '@angular/core';
import { environment } from '../../environments/environment';

export interface AppConfig {
  /** Base URL of the FedSim API, without trailing slash. */
  apiBaseUrl: string;
  /** Base URL of Grafana for embedded panels, without trailing slash. */
  grafanaBaseUrl: string;
}

/** Values a deployment can set on `window` before the app starts. */
export interface RuntimeConfigGlobals {
  FEDSIM_API_BASE_URL?: unknown;
  FEDSIM_GRAFANA_BASE_URL?: unknown;
}

export const APP_CONFIG = new InjectionToken<AppConfig>('APP_CONFIG', {
  providedIn: 'root',
  factory: () => resolveAppConfig(window as RuntimeConfigGlobals, window.location.origin),
});

export function resolveAppConfig(globals: RuntimeConfigGlobals, origin: string): AppConfig {
  const apiBaseUrl = withoutTrailingSlash(nonEmpty(globals.FEDSIM_API_BASE_URL) ?? environment.apiBaseUrl);
  // Behind the bundled reverse proxy Grafana is served next to the API.
  const proxiedGrafana = apiBaseUrl === '/api' ? `${origin}/grafana` : null;
  const grafanaBaseUrl = withoutTrailingSlash(
    nonEmpty(globals.FEDSIM_GRAFANA_BASE_URL) ?? proxiedGrafana ?? environment.grafanaBaseUrl,
  );
  return { apiBaseUrl, grafanaBaseUrl };
}

function nonEmpty(value: unknown): string | null {
  return typeof value === 'string' && value.trim() ? value.trim() : null;
}

function withoutTrailingSlash(url: string): string {
  return url.replace(/\/+$/, '');
}
