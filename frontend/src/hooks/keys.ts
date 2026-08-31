import type { OrphanListParams, RunListParams } from "../types.js";

/**
 * Exported from src/index.ts — a host sometimes needs to invalidate this app's cache from its
 * own composed code (docs/CONTRACT.md §7).
 *
 * `orphans(params)`/`runs(params)` deliberately drop the `params` slot from the key entirely
 * when called with no argument, rather than emitting `[...all, "orphans", undefined]`. React
 * Query's `invalidateQueries` matches by prefix with partial deep equality — a length-3 key
 * `["cleanup", "orphans", undefined]` would compare index 2 against every filtered query's own
 * `{ page, page_size }` object and never match, silently defeating every
 * `invalidateQueries({ queryKey: cleanupKeys.orphans() })` call both mutation hooks make. See
 * tests/frontend/invalidation.test.tsx for the regression this guards against.
 */
export const cleanupKeys = {
  all: ["cleanup"] as const,
  orphans: (params?: OrphanListParams) =>
    params === undefined
      ? ([...cleanupKeys.all, "orphans"] as const)
      : ([...cleanupKeys.all, "orphans", params] as const),
  runs: (params?: RunListParams) =>
    params === undefined
      ? ([...cleanupKeys.all, "runs"] as const)
      : ([...cleanupKeys.all, "runs", params] as const),
  run: (id: number) => [...cleanupKeys.all, "runs", id] as const,
  summary: () => [...cleanupKeys.all, "summary"] as const,
};
