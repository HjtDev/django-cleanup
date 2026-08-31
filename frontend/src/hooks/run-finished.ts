import type { CleanupRun } from "../types.js";

/**
 * Shared by useDeleteOrphanFiles and useTriggerCleanup — neither exported from index.ts.
 *
 * `POST /runs/` (and `POST /orphans/delete/`, which also creates a CleanupRun) returns 200 with
 * a finished run when the cleanup ran synchronously, or 202 with a PENDING run when
 * CLEANUP['USE_CELERY'] queued it instead (backend/src/cleanup_app/admin_views.py:244-268).
 * `finished_at` is null until the run completes either way, so it's the one field that
 * distinguishes the two cases regardless of status code.
 */
export function isRunFinished(run: CleanupRun): boolean {
  return run.finished_at !== null;
}
