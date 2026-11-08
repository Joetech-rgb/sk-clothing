/**
 * Reads the standard error envelope every /api/v1 error uses:
 *   { "error": { "code", "message", "details"?, "request_id"? } }
 * The server's message is already in plain words, so the UI shows it as it is.
 */

export interface ApiError {
  /** HTTP status, or 0 when no response arrived. */
  status: number;
  code: string;
  message: string;
  /** details.reason, the stable machine-readable reason some refusals carry. */
  reason: string | null;
  /** Everything else in details, for example a variant_id. */
  details: Record<string, unknown> | null;
  /** Validation messages by field path, such as "delivery.latitude" or "items.0.quantity". */
  fields: Record<string, string[]>;
  retryAfterSeconds: number | null;
  requestId: string | null;
}

/** Key used for validation messages that belong to no single field. */
export const NON_FIELD = "_";

export const GENERIC_MESSAGE = "Something went wrong. Please try again.";
export const NETWORK_MESSAGE = "We could not reach the server. Check your connection and try again.";

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function flatten(value: unknown, path: string, out: Record<string, string[]>): void {
  if (typeof value === "string") {
    (out[path === "" ? NON_FIELD : path] ??= []).push(value);
    return;
  }
  if (Array.isArray(value)) {
    value.forEach((item, index) => {
      if (typeof item === "string") {
        (out[path === "" ? NON_FIELD : path] ??= []).push(item);
      } else {
        flatten(item, path === "" ? String(index) : `${path}.${index}`, out);
      }
    });
    return;
  }
  if (isRecord(value)) {
    for (const [key, item] of Object.entries(value)) {
      flatten(item, path === "" ? key : `${path}.${key}`, out);
    }
  }
}

function blank(status: number, code: string, message: string): ApiError {
  return {
    status,
    code,
    message,
    reason: null,
    details: null,
    fields: {},
    retryAfterSeconds: null,
    requestId: null,
  };
}

export function networkError(): ApiError {
  return blank(0, "network_error", NETWORK_MESSAGE);
}

/** Turns a response status and parsed body into an ApiError. Never throws. */
export function parseApiError(status: number, body: unknown): ApiError {
  const envelope = isRecord(body) && isRecord(body.error) ? body.error : null;
  if (!envelope || typeof envelope.code !== "string" || typeof envelope.message !== "string") {
    return blank(status, "unexpected_response", GENERIC_MESSAGE);
  }
  const raw = envelope.details;
  const details = isRecord(raw) ? raw : null;
  const fields: Record<string, string[]> = {};
  if (envelope.code === "validation_error" && raw !== undefined && raw !== null) {
    flatten(raw, "", fields);
  }
  return {
    status,
    code: envelope.code,
    message: envelope.message,
    reason: details && typeof details.reason === "string" ? details.reason : null,
    details,
    fields,
    retryAfterSeconds:
      details && typeof details.retry_after_seconds === "number"
        ? details.retry_after_seconds
        : null,
    requestId: typeof envelope.request_id === "string" ? envelope.request_id : null,
  };
}

/** The sentence to show the customer. */
export function describeError(error: ApiError): string {
  if (error.code === "throttled" && error.retryAfterSeconds !== null) {
    const seconds = Math.ceil(error.retryAfterSeconds);
    return `Too many tries. Please wait ${seconds} seconds and try again.`;
  }
  return error.message;
}
