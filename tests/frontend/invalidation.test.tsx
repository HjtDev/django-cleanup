import { renderHook, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";
import { useOrphanFiles } from "../../frontend/src/hooks/useOrphanFiles.js";
import { useDeleteOrphanFiles } from "../../frontend/src/hooks/useDeleteOrphanFiles.js";
import { cleanupKeys } from "../../frontend/src/hooks/keys.js";
import { server } from "./setup.js";
import { createWrapper, TEST_BASE_URL } from "./helpers.js";
import { makeCleanupRun, makePaginatedOrphanFileList } from "./fixtures.js";

const ORPHANS_URL = `${TEST_BASE_URL}/api/v1/cleanup/admin/orphans/`;
const DELETE_URL = `${TEST_BASE_URL}/api/v1/cleanup/admin/orphans/delete/`;

// Regression test for cleanupKeys.orphans()'s length-mismatch trap: a naive
// `[...all, "orphans", params]` factory produces a length-3 key (`[..., undefined]`) when
// called with no argument, which never prefix-matches a filtered query's length-3 key holding a
// real params object — so invalidateQueries({ queryKey: cleanupKeys.orphans() }) would silently
// invalidate nothing. This test proves a *filtered* useOrphanFiles query really does refetch
// after useDeleteOrphanFiles succeeds.
describe("cleanupKeys.orphans() invalidates filtered queries too", () => {
  it("a useOrphanFiles({ page: 2 }) query refetches after a delete mutation succeeds", async () => {
    let callCount = 0;
    server.use(
      http.get(ORPHANS_URL, () => {
        callCount += 1;
        return HttpResponse.json(makePaginatedOrphanFileList({ count: callCount }));
      }),
      http.post(DELETE_URL, () =>
        HttpResponse.json(makeCleanupRun({ finished_at: "2026-08-31T10:00:05Z" }), {
          status: 202,
        }),
      ),
    );

    const { Wrapper } = createWrapper();
    const { result: listResult } = renderHook(() => useOrphanFiles({ page: 2 }), {
      wrapper: Wrapper,
    });
    await waitFor(() => expect(listResult.current.isSuccess).toBe(true));
    const firstCallCount = callCount;

    const { result: deleteResult } = renderHook(() => useDeleteOrphanFiles(), { wrapper: Wrapper });
    deleteResult.current.mutate(["uploads/orphan.jpg"]);
    await waitFor(() => expect(deleteResult.current.isSuccess).toBe(true));

    await waitFor(() => expect(callCount).toBeGreaterThan(firstCallCount));
  });

  it("orphans() with no params and orphans({ page: 2 }) share the same 2-element prefix", () => {
    const withoutParams = cleanupKeys.orphans();
    const withParams = cleanupKeys.orphans({ page: 2 });

    expect(withoutParams).toEqual(["cleanup", "orphans"]);
    expect(withParams.slice(0, withoutParams.length)).toEqual(withoutParams);
  });
});
