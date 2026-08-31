import { renderHook, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";
import { useCleanupRuns } from "../../frontend/src/hooks/useCleanupRuns.js";
import { server } from "./setup.js";
import { createWrapper, TEST_BASE_URL } from "./helpers.js";
import { makePaginatedCleanupRunList } from "./fixtures.js";

const RUNS_URL = `${TEST_BASE_URL}/api/v1/cleanup/admin/runs/`;

describe("useCleanupRuns", () => {
  it("returns the paginated run list on success", async () => {
    const body = makePaginatedCleanupRunList();
    server.use(http.get(RUNS_URL, () => HttpResponse.json(body)));

    const { result } = renderHook(() => useCleanupRuns(), { wrapper: createWrapper().Wrapper });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data).toEqual(body);
  });

  it("sends status/trigger filters as query params", async () => {
    let observedUrl: string | undefined;
    server.use(
      http.get(RUNS_URL, ({ request }) => {
        observedUrl = request.url;
        return HttpResponse.json(makePaginatedCleanupRunList());
      }),
    );

    const { result } = renderHook(() => useCleanupRuns({ status: "failed", trigger: "auto" }), {
      wrapper: createWrapper().Wrapper,
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(observedUrl).toBe(`${RUNS_URL}?status=failed&trigger=auto`);
  });

  it("surfaces an error on a failed request", async () => {
    server.use(http.get(RUNS_URL, () => HttpResponse.json({}, { status: 500 })));

    const { result } = renderHook(() => useCleanupRuns(), { wrapper: createWrapper().Wrapper });

    await waitFor(() => expect(result.current.isError).toBe(true));
  });
});
