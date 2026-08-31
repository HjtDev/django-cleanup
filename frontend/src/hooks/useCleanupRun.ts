"use client";

import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { CleanupManager } from "../api/manager.js";
import { useCleanupConfig } from "../api/config.js";
import { cleanupKeys } from "./keys.js";

export function useCleanupRun(id: number) {
  const { client, basePath } = useCleanupConfig();
  const manager = useMemo(() => new CleanupManager(client, basePath), [client, basePath]);

  return useQuery({
    queryKey: cleanupKeys.run(id),
    queryFn: () => manager.getRun(id),
    enabled: Number.isFinite(id),
  });
}
