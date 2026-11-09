import { networkError, parseApiError } from "./errors";
import type { ApiError } from "./errors";

export type ApiResult<T> =
  | { ok: true; status: number; data: T }
  | { ok: false; error: ApiError };

export const API_BASE = "/api/v1";
export const DEFAULT_TIMEOUT_MS = 20_000;

export interface RequestOptions {
  body?: unknown;
  /** Query string values. Undefined values are left out. */
  query?: Record<string, string | number | undefined>;
  /** Sent as the Idempotency-Key header. Reuse the same key when retrying one attempt. */
  idempotencyKey?: string;
  signal?: AbortSignal;
  timeoutMs?: number;
  /**
   * In the browser the default "/api/v1" works (Next forwards it to the backend).
   * Server code must pass an absolute URL, for example `${BACKEND_ORIGIN}/api/v1`.
   */
  baseUrl?: string;
  cache?: RequestCache;
  /** For tests. */
  fetch?: typeof fetch;
}

type Method = "GET" | "POST" | "PUT" | "PATCH" | "DELETE";

function buildUrl(baseUrl: string, path: string, query: RequestOptions["query"]): string {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(query ?? {})) {
    if (value !== undefined) params.set(key, String(value));
  }
  const qs = params.toString();
  return `${baseUrl}${path}${qs ? `?${qs}` : ""}`;
}

/**
 * One call to the backend. Never throws: a failure comes back as { ok: false, error } with
 * the server's message in plain words, or a network message when nothing arrived.
 * The client never sends a price: callers send ids and quantities only.
 */
export async function apiRequest<T>(
  method: Method,
  path: string,
  options: RequestOptions = {},
): Promise<ApiResult<T>> {
  const fetchImpl = options.fetch ?? fetch;
  const url = buildUrl(options.baseUrl ?? API_BASE, path, options.query);

  const headers: Record<string, string> = { Accept: "application/json" };
  let body: string | undefined;
  if (options.body !== undefined) {
    headers["Content-Type"] = "application/json";
    body = JSON.stringify(options.body);
  }
  if (options.idempotencyKey) {
    headers["Idempotency-Key"] = options.idempotencyKey;
  }

  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), options.timeoutMs ?? DEFAULT_TIMEOUT_MS);
  options.signal?.addEventListener("abort", () => controller.abort(), { once: true });

  try {
    const response = await fetchImpl(url, {
      method,
      headers,
      body,
      signal: controller.signal,
      credentials: "same-origin",
      cache: options.cache,
    });
    const text = await response.text();
    let parsed: unknown = null;
    let validJson = true;
    if (text !== "") {
      try {
        parsed = JSON.parse(text);
      } catch {
        validJson = false;
      }
    }
    if (!response.ok) {
      return { ok: false, error: parseApiError(response.status, validJson ? parsed : undefined) };
    }
    if (!validJson) {
      return { ok: false, error: parseApiError(response.status, undefined) };
    }
    return { ok: true, status: response.status, data: parsed as T };
  } catch {
    return { ok: false, error: networkError() };
  } finally {
    clearTimeout(timer);
  }
}
