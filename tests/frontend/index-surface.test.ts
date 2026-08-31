import { describe, expect, it } from "vitest";

import * as cleanupApp from "../../frontend/src/index.js";

// The complete export list — value exports only (type-only exports leave no runtime binding to
// enumerate). Kept as a literal list, not derived from the module itself, so this app can't
// silently widen or narrow the public surface without this test failing. Mirrors
// ../appkit/tests/frontend/index-surface.test.ts.
const EXPECTED_VALUE_EXPORTS = [
  "useOrphanFiles",
  "useDeleteOrphanFiles",
  "useTriggerCleanup",
  "useCleanupRuns",
  "useCleanupRun",
  "useCleanupSummary",
  "cleanupKeys",
].sort();

describe("src/index.ts — the complete export list", () => {
  it("exports exactly the hooks and cleanupKeys — no more, no less", () => {
    expect(Object.keys(cleanupApp).sort()).toEqual(EXPECTED_VALUE_EXPORTS);
  });

  it("never exports the manager, the config hook, or a provider", () => {
    expect(Object.keys(cleanupApp)).not.toContain("CleanupManager");
    expect(Object.keys(cleanupApp)).not.toContain("useCleanupConfig");
    expect(Object.keys(cleanupApp)).not.toContain("ApiClientProvider");
  });
});
