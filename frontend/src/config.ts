function trimTrailingSlash(value: string): string {
  return value.replace(/\/+$/, "");
}

function defaultApiBaseUrl(): string {
  // Production builds default to the page origin because FastAPI serves the SPA,
  // REST API, media, and WebSockets together. The Vite dev server keeps using
  // the separate backend port.
  return import.meta.env.PROD ? "" : "http://localhost:8000";
}

function defaultWsBaseUrl(apiBaseUrl: string): string {
  if (apiBaseUrl) {
    return trimTrailingSlash(apiBaseUrl.replace(/^http/i, "ws"));
  }
  if (typeof window !== "undefined") {
    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    return `${protocol}//${window.location.host}`;
  }
  return "ws://localhost:8000";
}

const configuredApiBase = import.meta.env.VITE_API_BASE_URL;
const configuredWsBase = import.meta.env.VITE_WS_BASE_URL;

export const API_BASE_URL =
  configuredApiBase === undefined
    ? defaultApiBaseUrl()
    : trimTrailingSlash(configuredApiBase.trim());

export const WS_BASE_URL = trimTrailingSlash(
  configuredWsBase === undefined || configuredWsBase.trim() === ""
    ? defaultWsBaseUrl(API_BASE_URL)
    : configuredWsBase.trim(),
);

export const API_TIMEOUT_MS = 20_000;
export const WS_MAX_RECONNECT_DELAY_MS = 15_000;
export const WS_BASE_RECONNECT_DELAY_MS = 600;
export const WS_MAX_FRAME_BYTES = 8192;
export const MAX_CHARACTER_IMAGE_BYTES = 5 * 1024 * 1024;
