"use client";

import { useMemo } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { CleanupManager } from "../api/manager.js";
import { useCleanupConfig } from "../api/config.js";
import { cleanupKeys } from "./keys.js";
import { isRunFinished } from "./run-finished.js";

/**
 * Wraps `POST /orphans/delete/` — an irreversible action (real files are removed from disk).
 * `mutationFn` only ever runs from an explicit `mutate()`/`mutateAsync()` call react-query
 * itself never fires on mount or a passive render, so this hook never deletes anything on its
 * own; see tests/frontend/mutations-do-not-fire-on-mount.test.tsx.
 */
export function useDeleteOrphanFiles() {
  const { client, basePath } = useCleanupConfig();
  const manager = useMemo(() => new CleanupManager(client, basePath), [client, basePath]);
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (paths: string[]) => manager.deleteOrphans(paths),
    onSuccess: (run) => {
      void queryClient.invalidateQueries({ queryKey: cleanupKeys.orphans() });
      // Deleting via this endpoint always runs synchronously (docs/CONTRACT.md §4 — unlike
      // POST /runs/, there is no celery-queued path here), so isRunFinished(run) is true in
      // practice; checked anyway rather than assumed, in case that ever changes.
      if (isRunFinished(run)) {
        void queryClient.invalidateQueries({ queryKey: cleanupKeys.runs() });
        void queryClient.invalidateQueries({ queryKey: cleanupKeys.summary() });
      }
    },
  });
}
