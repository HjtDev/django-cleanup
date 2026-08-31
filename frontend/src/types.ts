// Hand-written, and the SDK's public type surface — re-exports narrowed aliases from
// schema.d.ts (generated, never hand-edited) plus everything the schema can't express. Hooks
// and the manager import from here, never from ./schema.d.ts directly.

import type { components, operations } from "./schema.js";

/** `GET /orphans/` list-item shape: `{file_path, file_size, modified_at}`. */
export type OrphanFile = components["schemas"]["OrphanFile"];

/** `GET /orphans/` response — paginated `OrphanFile[]` plus the scan-snapshot extras
 * (`total_size`, `files_scanned`, `truncated`). */
export type PaginatedOrphanFileList = components["schemas"]["PaginatedOrphanFileList"];

/** A single `CleanupRun` row — the shape returned by the list endpoint and by both mutations. */
export type CleanupRun = components["schemas"]["CleanupRun"];

/** `GET /runs/{id}/` — a `CleanupRun` plus its `CleanupRunFile` rows. */
export type CleanupRunDetail = components["schemas"]["CleanupRunDetail"];

/** One file entry within a `CleanupRunDetail.files` array. */
export type CleanupRunFile = components["schemas"]["CleanupRunFile"];

/** `GET /runs/` response. */
export type PaginatedCleanupRunList = components["schemas"]["PaginatedCleanupRunList"];

/** `GET /summary/` response. */
export type CleanupSummary = components["schemas"]["CleanupSummary"];

/** `CleanupRun.status` — one of `StatusEnum`'s five values. */
export type CleanupRunStatus = components["schemas"]["StatusEnum"];

/** `CleanupRun.trigger` — one of `TriggerEnum`'s four values. */
export type CleanupRunTrigger = components["schemas"]["TriggerEnum"];

/** `POST /runs/`'s request body — the only client-writable field for a triggered run. */
export type TriggerCleanupOptions = components["schemas"]["CleanupTriggerRequestRequest"];

/** `GET /orphans/`'s query params. */
export type OrphanListParams = NonNullable<operations["orphans_list"]["parameters"]["query"]>;

/** `GET /runs/`'s query params — `page`/`page_size` plus the `status`/`trigger` filters
 * `admin_views.py`'s `CleanupRunListCreateView.get_queryset()` implements. */
export type RunListParams = NonNullable<operations["runs_list"]["parameters"]["query"]>;

// appkit owns the HttpClient interface; re-exported for convenience, never redeclared.
export type { HttpClient } from "@hjtdev/appkit";
