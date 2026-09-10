import { getDesktopApiBase, getDesktopSessionToken } from "./desktop-session";
import { clearStoredAuth, getStoredToken } from "../auth-storage";

const BASE_URL = process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000";
const API_PREFIX = "/api/v1";

export class ApiError extends Error {
  code: string;
  retryable: boolean;
  status: number;

  constructor(code: string, message: string, retryable: boolean, status: number) {
    super(message);
    this.name = "ApiError";
    this.code = code;
    this.retryable = retryable;
    this.status = status;
  }
}

/** Absolute URL (with /api/v1 prefix) for a backend path, honoring the desktop
 * base override when present, else NEXT_PUBLIC_API_BASE, else localhost:8000. */
export async function buildApiUrl(path: string): Promise<string> {
  const desktopBase = await getDesktopApiBase();
  return `${desktopBase ?? BASE_URL}${API_PREFIX}${path}`;
}

/** Auth headers every backend call should carry: desktop session token and the
 * Bearer login token (server mode). */
export async function authHeaders(): Promise<Record<string, string>> {
  const headers: Record<string, string> = {};
  const desktopToken = await getDesktopSessionToken();
  if (desktopToken) headers["X-Desktop-Session"] = desktopToken;
  const authToken = getStoredToken();
  if (authToken) headers["Authorization"] = `Bearer ${authToken}`;
  return headers;
}

export async function apiFetch<T>(
  path: string,
  options?: { method?: string; body?: unknown; timeoutMs?: number }
): Promise<T> {
  const timeoutMs = options?.timeoutMs ?? 15_000;
  let timeoutHandle: ReturnType<typeof setTimeout> | undefined;
  const timeoutError = new ApiError(
    "DESKTOP_API_TIMEOUT",
    "本地服务响应超时，请稍后重试；如持续出现，请打开日志目录。",
    true,
    504
  );
  const timeoutPromise = new Promise<never>((_resolve, reject) => {
    timeoutHandle = setTimeout(() => {
      reject(timeoutError);
    }, timeoutMs);
  });

  const requestPromise = performApiFetch<T>(path, options);
  try {
    return await Promise.race([requestPromise, timeoutPromise]);
  } finally {
    if (timeoutHandle !== undefined) clearTimeout(timeoutHandle);
  }
}

async function performApiFetch<T>(
  path: string,
  options: { method?: string; body?: unknown; timeoutMs?: number } | undefined
): Promise<T> {
  const url = await buildApiUrl(path);
  const method = options?.method ?? "GET";
  const headers: Record<string, string> = await authHeaders();

  let body: string | undefined;
  if (options?.body !== undefined) {
    headers["Content-Type"] = "application/json";
    body = JSON.stringify(options.body);
  }

  const response = await fetch(url, { method, headers, body });

  if (!response.ok) {
    let code = "UPSTREAM_ERROR";
    let message = `HTTP ${response.status}`;
    let retryable = response.status >= 500;

    try {
      const json = await response.json();
      if (json?.detail?.code) {
        code = json.detail.code;
        message = json.detail.message;
        retryable = json.detail.retryable ?? retryable;
      }
    } catch {
      // non-JSON response, use defaults
    }

    // Session expiry (not a bad login attempt) → clear local auth so the
    // session guard redirects back to the login page.
    if (response.status === 401 && path !== "/auth/login") {
      clearStoredAuth();
      if (typeof window !== "undefined") {
        window.dispatchEvent(new Event("bundling-auth-expired"));
      }
    }

    throw new ApiError(code, message, retryable, response.status);
  }

  return response.json() as Promise<T>;
}
