import type {
  CleanupRun,
  CleanupRunDetail,
  CleanupSummary,
  PaginatedCleanupRunList,
  PaginatedOrphanFileList,
} from "../../frontend/src/types.js";

export function makeCleanupRun(overrides: Partial<CleanupRun> = {}): CleanupRun {
  return {
    id: 1,
    status: "success",
    trigger: "api",
    dry_run: false,
    initiated_by: 1,
    started_at: "2026-08-31T10:00:00Z",
    finished_at: "2026-08-31T10:00:05Z",
    files_scanned: 10,
    files_deleted: 3,
    files_failed: 0,
    bytes_freed: 4096,
    error: "",
    ...overrides,
  };
}

export function makePendingCleanupRun(overrides: Partial<CleanupRun> = {}): CleanupRun {
  return makeCleanupRun({
    id: 2,
    status: "pending",
    finished_at: null,
    files_scanned: 0,
    files_deleted: 0,
    bytes_freed: 0,
    ...overrides,
  });
}

export function makeCleanupRunDetail(overrides: Partial<CleanupRunDetail> = {}): CleanupRunDetail {
  return {
    ...makeCleanupRun(),
    files: [
      {
        id: 1,
        file_path: "uploads/orphan.jpg",
        file_size: 2048,
        deleted: true,
        quarantined: false,
        error: "",
      },
    ],
    ...overrides,
  };
}

export function makePaginatedOrphanFileList(
  overrides: Partial<PaginatedOrphanFileList> = {},
): PaginatedOrphanFileList {
  return {
    count: 1,
    next: null,
    previous: null,
    results: [
      {
        file_path: "uploads/orphan.jpg",
        file_size: 2048,
        modified_at: "2026-08-30T00:00:00Z",
      },
    ],
    total_size: 2048,
    files_scanned: 42,
    truncated: false,
    ...overrides,
  };
}

export function makePaginatedCleanupRunList(
  overrides: Partial<PaginatedCleanupRunList> = {},
): PaginatedCleanupRunList {
  return {
    count: 1,
    next: null,
    previous: null,
    results: [makeCleanupRun()],
    ...overrides,
  };
}

export function makeCleanupSummary(overrides: Partial<CleanupSummary> = {}): CleanupSummary {
  return {
    total_runs: 5,
    files_deleted_total: 12,
    bytes_freed_total: 8192,
    last_run_at: "2026-08-31T10:00:05Z",
    last_run_status: "success",
    ...overrides,
  };
}
