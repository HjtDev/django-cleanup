import { renderHook, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";
import { useCleanupRun } from "../../frontend/src/hooks/useCleanupRun.js";
import { server } from "./setup.js";
import { createWrapper, TEST_BASE_URL } from "./helpers.js";
import { makeCleanupRunDetail } from "./fixtures.js";

describe("useCleanupRun", () => {
  it("returns a single run with its files on success", async () => {
    const body = makeCleanupRunDetail();
    server.use(
      http.get(`${TEST_BASE_URL}/api/v1/cleanup/admin/runs/1/`, () => HttpResponse.json(body)),
    );

    const { result } = renderHook(() => useCleanupRun(1), { wrapper: createWrapper().Wrapper });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data).toEqual(body);
  });

  it("surfaces an error on a failed request", async () => {
    server.use(
      http.get(`${TEST_BASE_URL}/api/v1/cleanup/admin/runs/1/`, () =>
        HttpResponse.json({}, { status: 404 }),
      ),
    );

    const { result } = renderHook(() => useCleanupRun(1), { wrapper: createWrapper().Wrapper });

    await waitFor(() => expect(result.current.isError).toBe(true));
  });
});
