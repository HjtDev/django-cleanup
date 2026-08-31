"use client";

// Internal — never exported from src/index.ts. Every real app SDK's api/config.ts follows this
// exact shape: a thin call to appkit's useApiClient(key, defaultBasePath), never anything
// host-specific. Namespace key `cleanup`, default basePath `/api/v1/cleanup`
// (docs/CONTRACT.md §0 / CLAUDE.md's namespacing table).
import { useApiClient } from "@hjtdev/appkit";

export const useCleanupConfig = () => useApiClient("cleanup", "/api/v1/cleanup");
