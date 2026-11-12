/**
 * Options for calls made by server code (pages), which cannot use the relative "/api/v1".
 * BACKEND_ORIGIN is read at run time here, so one build works for staging and live.
 */
export const SERVER_API_BASE = `${process.env.BACKEND_ORIGIN ?? "http://localhost:8000"}/api/v1`;

export const serverOptions = { baseUrl: SERVER_API_BASE, cache: "no-store" as const };
