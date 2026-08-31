import { act } from "react";
import { renderHook, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { describe, expect, it, vi } from "vitest";
import { useDeleteOrphanFiles } from "../../frontend/src/hooks/useDeleteOrphanFiles.js";
import { useTriggerCleanup } from "../../frontend/src/hooks/useTriggerCleanup.js";
import { server } from "./setup.js";
import { createWrapper, TEST_BASE_URL } from "./helpers.js";
import { makeCleanupRun } from "./fixtures.js";

// APP-DESIGN.md §12's frontend security checklist, named explicitly for this app's two
// mutations in docs/CONTRACT.md §7: "a mutation hook for a destructive or sensitive action
// never fires on mount or on a passive render — it only fires from an explicit user action."
// Real files are deleted (useDeleteOrphanFiles) or a real cleanup run is started
// (useTriggerCleanup); either firing on mount would be a silent data-loss bug.

describe("destructive mutations never fire on mount or a passive render", () => {
  it("useDeleteOrphanFiles stays idle through mount and re-renders, fires only on mutate()", async () => {
    const deleteHandler = vi.fn(() => HttpResponse.json(makeCleanupRun(), { status: 202 }));
    server.use(http.post(`${TEST_BASE_URL}/api/v1/cleanup/admin/orphans/delete/`, deleteHandler));

    const { result, rerender } = renderHook(() => useDeleteOrphanFiles(), {
      wrapper: createWrapper().Wrapper,
    });

    expect(result.current.isIdle).toBe(true);
    expect(deleteHandler).not.toHaveBeenCalled();

    // A passive re-render (no user action) must not trigger the mutation either.
    rerender();
    rerender();
    await act(async () => {
      await Promise.resolve();
    });
    expect(result.current.isIdle).toBe(true);
    expect(deleteHandler).not.toHaveBeenCalled();

    result.current.mutate(["uploads/orphan.jpg"]);
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(deleteHandler).toHaveBeenCalledTimes(1);
  });

  it("useTriggerCleanup stays idle through mount and re-renders, fires only on mutate()", async () => {
    const triggerHandler = vi.fn(() => HttpResponse.json(makeCleanupRun(), { status: 200 }));
    server.use(http.post(`${TEST_BASE_URL}/api/v1/cleanup/admin/runs/`, triggerHandler));

    const { result, rerender } = renderHook(() => useTriggerCleanup(), {
      wrapper: createWrapper().Wrapper,
    });

    expect(result.current.isIdle).toBe(true);
    expect(triggerHandler).not.toHaveBeenCalled();

    rerender();
    rerender();
    await act(async () => {
      await Promise.resolve();
    });
    expect(result.current.isIdle).toBe(true);
    expect(triggerHandler).not.toHaveBeenCalled();

    result.current.mutate({ dry_run: true });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(triggerHandler).toHaveBeenCalledTimes(1);
  });
});
