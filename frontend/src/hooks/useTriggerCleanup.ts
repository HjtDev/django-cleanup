"use client";

import { useMemo } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { CleanupManager } from "../api/manager.js";
import { useCleanupConfig } from "../api/config.js";
import { cleanupKeys } from "./keys.js";
import type { TriggerCleanupOptions } from "../types.js";

/**
 * Wraps `POST /runs/` — an irreversible action once `dry_run` is false. Only ever fires from an
 * explicit `mutate()`/`mutateAsync()` call, never on mount or a passive render; see
 * tests/frontend/mutations-do-not-fire-on-mount.test.tsx.
 *
 * Invalidation is unconditional (docs/CONTRACT.md §7's table, not the guide prose's stricter
 * "only once finished" reading — CONTRACT is the frozen document): under Celery, this endpoint
 * returns a PENDING run with 202, and the runs list genuinely changed the moment that row was
 * created, not only once it finishes.
 */
export function useTriggerCleanup() {
  const { client, basePath } = useCleanupConfig();
  const manager = useMemo(() => new CleanupManager(client, basePath), [client, basePath]);
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (options?: TriggerCleanupOptions) => manager.triggerCleanup(options),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: cleanupKeys.runs() });
      void queryClient.invalidateQueries({ queryKey: cleanupKeys.summary() });
      void queryClient.invalidateQueries({ queryKey: cleanupKeys.orphans() });
    },
  });
}
