import { renderHook, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { describe, expect, it, vi } from "vitest";
import { useTriggerCleanup } from "../../frontend/src/hooks/useTriggerCleanup.js";
import { server } from "./setup.js";
import { createWrapper, TEST_BASE_URL } from "./helpers.js";
import { makeCleanupRun, makePendingCleanupRun } from "./fixtures.js";
import { cleanupKeys } from "../../frontend/src/hooks/keys.js";

const RUNS_URL = `${TEST_BASE_URL}/api/v1/cleanup/admin/runs/`;

describe("useTriggerCleanup", () => {
  it("triggers a run and returns the finished run (synchronous path, 200)", async () => {
    const run = makeCleanupRun();
    let observedBody: unknown;
    server.use(
      http.post(RUNS_URL, async ({ request }) => {
        observedBody = await request.json();
        return HttpResponse.json(run, { status: 200 });
      }),
    );

    const { result } = renderHook(() => useTriggerCleanup(), { wrapper: createWrapper().Wrapper });

    result.current.mutate({ dry_run: true });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data).toEqual(run);
    expect(observedBody).toEqual({ dry_run: true });
  });

  it("triggers a run and returns a pending run (celery-queued path, 202)", async () => {
    const run = makePendingCleanupRun();
    server.use(http.post(RUNS_URL, () => HttpResponse.json(run, { status: 202 })));

    const { result } = renderHook(() => useTriggerCleanup(), { wrapper: createWrapper().Wrapper });

    result.current.mutate();

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data).toEqual(run);
  });

  it("surfaces an error on a failed request", async () => {
    server.use(http.post(RUNS_URL, () => HttpResponse.json({}, { status: 500 })));

    const { result } = renderHook(() => useTriggerCleanup(), { wrapper: createWrapper().Wrapper });

    result.current.mutate();

    await waitFor(() => expect(result.current.isError).toBe(true));
  });

  it("invalidates runs, summary, and orphans unconditionally, even on a pending run", async () => {
    const run = makePendingCleanupRun();
    server.use(http.post(RUNS_URL, () => HttpResponse.json(run, { status: 202 })));

    const { Wrapper, queryClient } = createWrapper();
    const invalidateSpy = vi.spyOn(queryClient, "invalidateQueries");
    const { result } = renderHook(() => useTriggerCleanup(), { wrapper: Wrapper });

    result.current.mutate();
    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: cleanupKeys.runs() });
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: cleanupKeys.summary() });
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: cleanupKeys.orphans() });
  });
});
