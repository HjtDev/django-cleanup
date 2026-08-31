import { renderHook, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";
import { useOrphanFiles } from "../../frontend/src/hooks/useOrphanFiles.js";
import { server } from "./setup.js";
import { createWrapper, TEST_BASE_URL } from "./helpers.js";
import { makePaginatedOrphanFileList } from "./fixtures.js";

const ORPHANS_URL = `${TEST_BASE_URL}/api/v1/cleanup/admin/orphans/`;

describe("useOrphanFiles", () => {
  it("returns the paginated orphan list on success", async () => {
    const body = makePaginatedOrphanFileList();
    server.use(http.get(ORPHANS_URL, () => HttpResponse.json(body)));

    const { result } = renderHook(() => useOrphanFiles(), { wrapper: createWrapper().Wrapper });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data).toEqual(body);
  });

  it("sends page/page_size as a query string, appended after the admin/ segment", async () => {
    let observedUrl: string | undefined;
    server.use(
      http.get(ORPHANS_URL, ({ request }) => {
        observedUrl = request.url;
        return HttpResponse.json(makePaginatedOrphanFileList());
      }),
    );

    const { result } = renderHook(() => useOrphanFiles({ page: 2, page_size: 10 }), {
      wrapper: createWrapper().Wrapper,
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(observedUrl).toBe(`${ORPHANS_URL}?page=2&page_size=10`);
  });

  it("surfaces an error on a failed request", async () => {
    server.use(http.get(ORPHANS_URL, () => HttpResponse.json({}, { status: 500 })));

    const { result } = renderHook(() => useOrphanFiles(), { wrapper: createWrapper().Wrapper });

    await waitFor(() => expect(result.current.isError).toBe(true));
  });

  it("omits an explicitly-undefined param from the query string instead of sending 'undefined'", async () => {
    let observedUrl: string | undefined;
    server.use(
      http.get(ORPHANS_URL, ({ request }) => {
        observedUrl = request.url;
        return HttpResponse.json(makePaginatedOrphanFileList());
      }),
    );

    const { result } = renderHook(() => useOrphanFiles({ page: 1, page_size: undefined }), {
      wrapper: createWrapper().Wrapper,
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(observedUrl).toBe(`${ORPHANS_URL}?page=1`);
  });
});
