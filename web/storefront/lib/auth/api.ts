import type { paths } from "@sk/api-client";
import { apiRequest } from "../api/request";
import type { ApiResult } from "../api/request";

type CodeRequestBody = paths["/api/v1/auth/code/request/"]["post"]["requestBody"]["content"]["application/json"];
type CodeVerifyBody = paths["/api/v1/auth/code/verify/"]["post"]["requestBody"]["content"]["application/json"];

interface Options {
  fetch?: typeof fetch;
}

/** Asks the server to text a sign-in code. The server normalises the number and decides if it is valid. */
export function requestLoginCode(phone: string, options: Options = {}): Promise<ApiResult<unknown>> {
  const body: CodeRequestBody = { phone: phone.trim() };
  return apiRequest<unknown>("POST", "/auth/code/request/", { body, ...options });
}

/** Signing in succeeds when the server says so; the code is never stored here. */
export function verifyLoginCode(
  phone: string,
  code: string,
  options: Options = {},
): Promise<ApiResult<unknown>> {
  const body: CodeVerifyBody = { phone: phone.trim(), code: code.trim() };
  return apiRequest<unknown>("POST", "/auth/code/verify/", { body, ...options });
}

/** True when the server recognises the browser's session. Only the status matters. */
export async function isSignedIn(options: Options = {}): Promise<boolean> {
  const result = await apiRequest<unknown>("GET", "/auth/me/", options);
  return result.ok;
}

export function signOut(options: Options = {}): Promise<ApiResult<unknown>> {
  return apiRequest<unknown>("POST", "/auth/logout/", options);
}
