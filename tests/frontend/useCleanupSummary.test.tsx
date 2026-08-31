import { renderHook, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";
import { useCleanupSummary } from "../../frontend/src/hooks/useCleanupSummary.js";
import { server } from "./setup.js";
import { createWrapper, TEST_BASE_URL } from "./helpers.js";
import { makeCleanupSummary } from "./fixtures.js";

const SUMMARY_URL = `${TEST_BASE_URL}/api/v1/cleanup/admin/summary/`;

describe("useCleanupSummary", () => {
  it("returns aggregate totals on success", async () => {
    const body = makeCleanupSummary();
    server.use(http.get(SUMMARY_URL, () => HttpResponse.json(body)));

    const { result } = renderHook(() => useCleanupSummary(), { wrapper: createWrapper().Wrapper });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data).toEqual(body);
  });

  it("surfaces an error on a failed request", async () => {
    server.use(http.get(SUMMARY_URL, () => HttpResponse.json({}, { status: 500 })));

    const { result } = renderHook(() => useCleanupSummary(), { wrapper: createWrapper().Wrapper });

    await waitFor(() => expect(result.current.isError).toBe(true));
  });
});
