// Instance-based manager — the ONLY place a raw HTTP call happens in this SDK. Never exported
// from src/index.ts; a host only ever reaches it indirectly, through a hook.
//
// Every path below carries an `admin/` segment the injected basePath does NOT — useCleanupConfig
// binds `/api/v1/cleanup`, but every route this app registers lives under
// `/api/v1/cleanup/admin/...` (backend/src/cleanup_app/urls_admin.py, mounted by the host under
// that sub-prefix). Dropping `admin/` here 404s at runtime with no compile-time signal, since
// basePath is a plain string.

import type { HttpClient } from "@hjtdev/appkit";
import type {
  CleanupRun,
  CleanupRunDetail,
  CleanupSummary,
  OrphanListParams,
  PaginatedCleanupRunList,
  PaginatedOrphanFileList,
  RunListParams,
  TriggerCleanupOptions,
} from "../types.js";

/**
 * Builds a query string from a plain params object, skipping `undefined`/`null` values.
 * `HttpClient` (appkit) has no params channel of its own — `get`/`delete` take only a path and
 * `RequestInit` — so this is the one place a query string is assembled, via `URLSearchParams`
 * rather than raw template interpolation, per the frontend security checklist's "manager methods
 * never build a URL by concatenating unescaped user input" rule.
 */
function toQueryString(params: Record<string, unknown> | undefined): string {
  if (!params) return "";
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value === undefined || value === null) continue;
    search.set(key, String(value));
  }
  const query = search.toString();
  return query ? `?${query}` : "";
}

export class CleanupManager {
  constructor(
    private readonly client: HttpClient,
    private readonly basePath: string,
  ) {}

  listOrphans(params?: OrphanListParams): Promise<PaginatedOrphanFileList> {
    return this.client.get<PaginatedOrphanFileList>(
      `${this.basePath}/admin/orphans/${toQueryString(params)}`,
    );
  }

  deleteOrphans(paths: string[]): Promise<CleanupRun> {
    return this.client.post<CleanupRun>(`${this.basePath}/admin/orphans/delete/`, {
      file_paths: paths,
    });
  }

  listRuns(params?: RunListParams): Promise<PaginatedCleanupRunList> {
    return this.client.get<PaginatedCleanupRunList>(
      `${this.basePath}/admin/runs/${toQueryString(params)}`,
    );
  }

  getRun(id: number): Promise<CleanupRunDetail> {
    return this.client.get<CleanupRunDetail>(`${this.basePath}/admin/runs/${id}/`);
  }

  triggerCleanup(options?: TriggerCleanupOptions): Promise<CleanupRun> {
    return this.client.post<CleanupRun>(`${this.basePath}/admin/runs/`, options ?? {});
  }

  getSummary(): Promise<CleanupSummary> {
    return this.client.get<CleanupSummary>(`${this.basePath}/admin/summary/`);
  }
}
