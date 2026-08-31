/**
 * The host's own concrete HttpClient implementation — adapted from
 * ../../../appkit/playground/frontend/lib/api-client.ts, with one deliberate difference: this
 * playground proxies same-origin via next.config.ts's rewrites() (decision 2 of the Phase 7
 * plan, since every cleanup_app endpoint is IsAppAdmin-gated and needs a real session cookie),
 * so there is no NEXT_PUBLIC_API_URL to resolve — every request is a plain relative path against
 * the Next.js server's own origin.
 *
 * Errors are constructed via appkit's apiErrorFromEnvelope, not a locally-declared ApiError
 * class, so makeQueryClient's brand-based isApiError() retry predicate recognises what this
 * client throws.
 */
import { apiErrorFromEnvelope, type HttpClient } from "@hjtdev/appkit";

const REQUEST_ID_HEADER = "X-Request-ID";
const CSRF_COOKIE_NAME = "csrftoken";
const CSRF_HEADER_NAME = "X-CSRFToken";
const UNSAFE_METHODS = new Set(["POST", "PUT", "PATCH", "DELETE"]);

function readCookie(name: string): string | null {
  if (typeof document === "undefined") return null;
  const match = document.cookie.match(new RegExp(`(?:^|; )${name}=([^;]*)`));
  return match?.[1] ? decodeURIComponent(match[1]) : null;
}

export class ApiClient implements HttpClient {
  async request<T>(path: string, init: RequestInit = {}): Promise<T> {
    const method = (init.method ?? "GET").toUpperCase();

    const headers = new Headers(init.headers);
    if (init.body !== undefined && !headers.has("Content-Type")) {
      headers.set("Content-Type", "application/json");
    }
    if (UNSAFE_METHODS.has(method)) {
      const csrfToken = readCookie(CSRF_COOKIE_NAME);
      if (csrfToken) headers.set(CSRF_HEADER_NAME, csrfToken);
    }

    const response = await fetch(path, { ...init, method, credentials: "same-origin", headers });

    if (response.status === 204) {
      return undefined as T;
    }

    const requestId = response.headers.get(REQUEST_ID_HEADER);
    const retryAfter = response.headers.get("Retry-After");
    const contentType = response.headers.get("Content-Type") ?? "";

    if (!contentType.includes("application/json")) {
      const text = await response.text();
      if (!response.ok) {
        throw apiErrorFromEnvelope({ status: response.status, body: text, requestId, retryAfter });
      }
      return text as unknown as T;
    }

    let data: unknown;
    try {
      data = await response.json();
    } catch {
      throw apiErrorFromEnvelope({ status: response.status, body: undefined, requestId, retryAfter });
    }

    if (!response.ok) {
      throw apiErrorFromEnvelope({ status: response.status, body: data, requestId, retryAfter });
    }

    return data as T;
  }

  get<T>(path: string, init?: RequestInit): Promise<T> {
    return this.request<T>(path, { ...init, method: "GET" });
  }
  post<T>(path: string, body?: unknown, init?: RequestInit): Promise<T> {
    return this.request<T>(path, {
      ...init,
      method: "POST",
      body: body !== undefined ? JSON.stringify(body) : undefined,
    });
  }
  put<T>(path: string, body?: unknown, init?: RequestInit): Promise<T> {
    return this.request<T>(path, {
      ...init,
      method: "PUT",
      body: body !== undefined ? JSON.stringify(body) : undefined,
    });
  }
  patch<T>(path: string, body?: unknown, init?: RequestInit): Promise<T> {
    return this.request<T>(path, {
      ...init,
      method: "PATCH",
      body: body !== undefined ? JSON.stringify(body) : undefined,
    });
  }
  delete<T>(path: string, init?: RequestInit): Promise<T> {
    return this.request<T>(path, { ...init, method: "DELETE" });
  }
}

export const apiClient = new ApiClient();
