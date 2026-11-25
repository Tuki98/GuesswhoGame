import { API_BASE_URL, API_TIMEOUT_MS } from "@/config";

const INTERNAL_ERROR_CODES = new Set(["internal_error", "http_error", "service_unavailable"]);

interface ErrorEnvelope {
  error?: {
    code?: unknown;
    message?: unknown;
    details?: unknown;
  };
}

export interface ApiErrorInit {
  status: number;
  code: string;
  message: string;
  details?: unknown;
}

export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly details: unknown;

  constructor(init: ApiErrorInit) {
    super(init.message);
    this.name = "ApiError";
    this.status = init.status;
    this.code = init.code;
    this.details = init.details;
  }

  get isInvalidSession(): boolean {
    return this.status === 401 || this.code === "invalid_session";
  }

  get userMessage(): string {
    if (this.code === "network_error") {
      return "Unable to reach the game server. Check your connection and try again.";
    }
    if (this.code === "timeout") {
      return "The game server took too long to respond. Please try again.";
    }
    if (this.status >= 500 || INTERNAL_ERROR_CODES.has(this.code)) {
      return "The game server hit a problem. Please try again.";
    }
    if (this.code === "validation_error") {
      return this.validationSummary ?? this.message;
    }
    return this.message;
  }

  private get validationSummary(): string | null {
    if (!Array.isArray(this.details) || this.details.length === 0) {
      return null;
    }
    const first: unknown = this.details[0];
    if (!first || typeof first !== "object") {
      return null;
    }
    const row = first as Record<string, unknown>;
    if (typeof row.message !== "string") {
      return null;
    }
    const location = Array.isArray(row.location)
      ? row.location.filter((part): part is string => typeof part === "string").at(-1)
      : null;
    return location ? `${location}: ${row.message}` : row.message;
  }
}

export type HttpMethod = "GET" | "POST" | "PATCH" | "PUT" | "DELETE";

export interface ApiRequestOptions {
  method?: HttpMethod;
  token?: string | null;
  body?: unknown;
  formData?: FormData;
  timeoutMs?: number;
}

function buildUrl(path: string): string {
  const normalized = path.startsWith("/") ? path : `/${path}`;
  return `${API_BASE_URL}${normalized}`;
}

async function readError(response: Response): Promise<ApiError> {
  let envelope: ErrorEnvelope | null = null;
  try {
    envelope = (await response.json()) as ErrorEnvelope;
  } catch {
    envelope = null;
  }
  const nested = envelope?.error;
  const code =
    typeof nested?.code === "string"
      ? nested.code
      : response.status === 401
        ? "invalid_session"
        : `http_${response.status}`;
  const message =
    typeof nested?.message === "string"
      ? nested.message
      : response.status === 401
        ? "Your session is invalid or has expired."
        : "The request could not be completed.";
  return new ApiError({
    status: response.status,
    code,
    message,
    details: nested?.details,
  });
}

export async function apiRequest<T>(
  path: string,
  options: ApiRequestOptions = {},
): Promise<T> {
  const controller = new AbortController();
  const timeout = window.setTimeout(
    () => controller.abort(),
    options.timeoutMs ?? API_TIMEOUT_MS,
  );
  const headers = new Headers({ Accept: "application/json" });
  if (options.token) {
    headers.set("Authorization", `Bearer ${options.token}`);
  }

  let body: BodyInit | undefined;
  if (options.formData) {
    body = options.formData;
  } else if (options.body !== undefined) {
    headers.set("Content-Type", "application/json");
    body = JSON.stringify(options.body);
  }

  try {
    const response = await fetch(buildUrl(path), {
      method: options.method ?? "GET",
      headers,
      body,
      signal: controller.signal,
      credentials: "omit",
    });

    if (!response.ok) {
      throw await readError(response);
    }

    if (response.status === 204) {
      return undefined as T;
    }

    const text = await response.text();
    if (!text) {
      return undefined as T;
    }
    return JSON.parse(text) as T;
  } catch (error) {
    if (error instanceof ApiError) {
      throw error;
    }
    if (error instanceof DOMException && error.name === "AbortError") {
      throw new ApiError({
        status: 0,
        code: "timeout",
        message: "The game server took too long to respond.",
      });
    }
    throw new ApiError({
      status: 0,
      code: "network_error",
      message: "Unable to reach the game server. Check your connection and try again.",
    });
  } finally {
    window.clearTimeout(timeout);
  }
}

export function mediaUrl(path: string | null | undefined): string | null {
  if (!path) {
    return null;
  }
  if (/^https?:\/\//i.test(path)) {
    return path;
  }
  const normalized = path.startsWith("/") ? path : `/${path}`;
  return `${API_BASE_URL}${normalized}`;
}
