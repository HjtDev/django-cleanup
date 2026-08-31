import type { ReactNode } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ApiClientProvider } from "@hjtdev/appkit";
import type { HttpClient } from "@hjtdev/appkit";

/**
 * appkit ships no client implementation of its own (docs/CONTRACT.md §13) — this is a minimal,
 * test-only `fetch`-based `HttpClient` so MSW has something real to intercept, modelled on
 * ../appkit/tests/frontend/header-sources.msw.test.tsx's own `makeFetchClient`.
 *
 * Throws on a non-OK response rather than resolving — without this every error-path test would
 * see a "successful" mutation/query against a 4xx/5xx handler.
 */
export function makeFetchClient(baseUrl: string): HttpClient {
  async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
    const response = await fetch(`${baseUrl}${path}`, init);
    if (!response.ok) {
      throw new Error(`Request failed: ${response.status}`);
    }
    if (response.status === 204) {
      return undefined as T;
    }
    return (await response.json()) as T;
  }

  return {
    get: (path, init) => request(path, init),
    post: (path, body, init) =>
      request(path, {
        ...init,
        method: "POST",
        headers: { "Content-Type": "application/json", ...init?.headers },
        body: body !== undefined ? JSON.stringify(body) : undefined,
      }),
    put: (path, body, init) =>
      request(path, {
        ...init,
        method: "PUT",
        headers: { "Content-Type": "application/json", ...init?.headers },
        body: body !== undefined ? JSON.stringify(body) : undefined,
      }),
    patch: (path, body, init) =>
      request(path, {
        ...init,
        method: "PATCH",
        headers: { "Content-Type": "application/json", ...init?.headers },
        body: body !== undefined ? JSON.stringify(body) : undefined,
      }),
    delete: (path, init) => request(path, { ...init, method: "DELETE" }),
  };
}

export const TEST_BASE_URL = "https://api.test";

/**
 * Wraps a `renderHook` call in `QueryClientProvider` (retry disabled on both queries and
 * mutations, per docs/APP-DESIGN.md §7.7's "retry: false stops react-query's default retry from
 * making a failure-path test take three seconds") plus appkit's `ApiClientProvider`, bound to
 * the `cleanup` namespace at `/api/v1/cleanup` — the same default `useCleanupConfig` itself uses.
 */
export function createWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  const client = makeFetchClient(TEST_BASE_URL);

  function Wrapper({ children }: { children: ReactNode }) {
    return (
      <QueryClientProvider client={queryClient}>
        <ApiClientProvider client={client} basePaths={{ cleanup: "/api/v1/cleanup" }}>
          {children}
        </ApiClientProvider>
      </QueryClientProvider>
    );
  }

  return { Wrapper, queryClient };
}
