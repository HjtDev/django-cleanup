import { renderHook, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { describe, expect, it, vi } from "vitest";
import { useDeleteOrphanFiles } from "../../frontend/src/hooks/useDeleteOrphanFiles.js";
import { server } from "./setup.js";
import { createWrapper, TEST_BASE_URL } from "./helpers.js";
import { makeCleanupRun, makePaginatedOrphanFileList } from "./fixtures.js";
import { cleanupKeys } from "../../frontend/src/hooks/keys.js";

const DELETE_URL = `${TEST_BASE_URL}/api/v1/cleanup/admin/orphans/delete/`;

describe("useDeleteOrphanFiles", () => {
  it("deletes the given paths and returns the resulting run", async () => {
    const run = makeCleanupRun();
    let observedBody: unknown;
    server.use(
      http.post(DELETE_URL, async ({ request }) => {
        observedBody = await request.json();
        return HttpResponse.json(run, { status: 202 });
      }),
    );

    const { result } = renderHook(() => useDeleteOrphanFiles(), {
      wrapper: createWrapper().Wrapper,
    });

    result.current.mutate(["uploads/orphan.jpg"]);

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data).toEqual(run);
    expect(observedBody).toEqual({ file_paths: ["uploads/orphan.jpg"] });
  });

  it("surfaces an error when a path isn't in the current snapshot (400)", async () => {
    server.use(http.post(DELETE_URL, () => HttpResponse.json({}, { status: 400 })));

    const { result } = renderHook(() => useDeleteOrphanFiles(), {
      wrapper: createWrapper().Wrapper,
    });

    result.current.mutate(["not/a/real/orphan.jpg"]);

    await waitFor(() => expect(result.current.isError).toBe(true));
  });

  it("invalidates the orphans list, runs list, and summary once the run finishes", async () => {
    const run = makeCleanupRun({ finished_at: "2026-08-31T10:00:05Z" });
    server.use(http.post(DELETE_URL, () => HttpResponse.json(run, { status: 202 })));

    const { Wrapper, queryClient } = createWrapper();
    queryClient.setQueryData(cleanupKeys.orphans(), makePaginatedOrphanFileList());

    const invalidateSpy = vi.spyOn(queryClient, "invalidateQueries");
    const { result } = renderHook(() => useDeleteOrphanFiles(), { wrapper: Wrapper });

    result.current.mutate(["uploads/orphan.jpg"]);
    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: cleanupKeys.orphans() });
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: cleanupKeys.runs() });
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: cleanupKeys.summary() });
  });

  it("invalidates only the orphans list when the run hasn't finished yet", async () => {
    // Exercises isRunFinished(run) === false. The backend never actually returns an unfinished
    // run from this endpoint today (docs/CONTRACT.md §4 — POST /orphans/delete/ always runs
    // synchronously), but the hook checks rather than assumes, so this branch is real code, not
    // dead code, and stays covered.
    const run = makeCleanupRun({ finished_at: null });
    server.use(http.post(DELETE_URL, () => HttpResponse.json(run, { status: 202 })));

    const { Wrapper, queryClient } = createWrapper();
    const invalidateSpy = vi.spyOn(queryClient, "invalidateQueries");
    const { result } = renderHook(() => useDeleteOrphanFiles(), { wrapper: Wrapper });

    result.current.mutate(["uploads/orphan.jpg"]);
    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: cleanupKeys.orphans() });
    expect(invalidateSpy).not.toHaveBeenCalledWith({ queryKey: cleanupKeys.runs() });
    expect(invalidateSpy).not.toHaveBeenCalledWith({ queryKey: cleanupKeys.summary() });
  });
});
