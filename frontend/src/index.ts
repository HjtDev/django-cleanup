// The only file a host ever imports from — the "one entrypoint" rule. Note that CleanupManager
// and useCleanupConfig are never exported here, only hooks, the key factory, and types. There is
// no provider to export — the host mounts appkit's ApiClientProvider once and adds this app's
// `cleanup` basePath to its `basePaths` map (see README.md's "Usage" section).

export { useOrphanFiles } from "./hooks/useOrphanFiles.js";
export { useDeleteOrphanFiles } from "./hooks/useDeleteOrphanFiles.js";
export { useTriggerCleanup } from "./hooks/useTriggerCleanup.js";
export { useCleanupRuns } from "./hooks/useCleanupRuns.js";
export { useCleanupRun } from "./hooks/useCleanupRun.js";
export { useCleanupSummary } from "./hooks/useCleanupSummary.js";
export { cleanupKeys } from "./hooks/keys.js";

export type {
  CleanupRun,
  CleanupRunDetail,
  CleanupRunFile,
  CleanupRunStatus,
  CleanupRunTrigger,
  CleanupSummary,
  HttpClient,
  OrphanFile,
  OrphanListParams,
  PaginatedCleanupRunList,
  PaginatedOrphanFileList,
  RunListParams,
  TriggerCleanupOptions,
} from "./types.js";
