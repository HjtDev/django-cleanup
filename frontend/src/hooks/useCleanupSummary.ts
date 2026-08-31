"use client";

import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { CleanupManager } from "../api/manager.js";
import { useCleanupConfig } from "../api/config.js";
import { cleanupKeys } from "./keys.js";

export function useCleanupSummary() {
  const { client, basePath } = useCleanupConfig();
  const manager = useMemo(() => new CleanupManager(client, basePath), [client, basePath]);

  return useQuery({
    queryKey: cleanupKeys.summary(),
    queryFn: () => manager.getSummary(),
  });
}
