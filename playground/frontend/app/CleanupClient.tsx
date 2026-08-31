"use client";

import { useState } from "react";
import { isApiError } from "@hjtdev/appkit";
import {
  useOrphanFiles,
  useDeleteOrphanFiles,
  useTriggerCleanup,
  useCleanupRuns,
  useCleanupRun,
  useCleanupSummary,
} from "@hjtdev/django-cleanup";

/** Renders appkit's error envelope legibly — code/status/detail, never `[object Object]`. */
function ErrorBanner({ error }: { error: unknown }) {
  if (!isApiError(error)) return <p style={{ color: "crimson" }}>Unknown error: {String(error)}</p>;
  return (
    <p style={{ color: "crimson" }}>
      {error.code} ({error.status}): {error.message}
    </p>
  );
}

export default function CleanupClient() {
  const [page, setPage] = useState(1);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [dryRun, setDryRun] = useState(false);
  const [expandedRunId, setExpandedRunId] = useState<number | null>(null);
  const [breakError, setBreakError] = useState<unknown>(null);

  const orphans = useOrphanFiles({ page });
  const runs = useCleanupRuns();
  const summary = useCleanupSummary();
  const runDetail = useCleanupRun(expandedRunId ?? Number.NaN);

  const deleteOrphans = useDeleteOrphanFiles();
  const triggerCleanup = useTriggerCleanup();

  function toggle(path: string) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(path)) next.delete(path);
      else next.add(path);
      return next;
    });
  }

  return (
    <main style={{ display: "grid", gap: "2rem" }}>
      <h1>Orphan review</h1>

      <section>
        <h2>Summary (useCleanupSummary)</h2>
        {summary.isLoading && <p>Loading…</p>}
        {summary.isError && <ErrorBanner error={summary.error} />}
        {summary.data && (
          <ul>
            <li>total_runs: {summary.data.total_runs}</li>
            <li>files_deleted_total: {summary.data.files_deleted_total}</li>
            <li>bytes_freed_total: {summary.data.bytes_freed_total}</li>
            <li>last_run_status: {summary.data.last_run_status ?? "—"}</li>
          </ul>
        )}
      </section>

      <section>
        <h2>Orphans (useOrphanFiles, page {page})</h2>
        {orphans.isLoading && <p>Loading…</p>}
        {orphans.isError && <ErrorBanner error={orphans.error} />}
        {orphans.data && (
          <>
            <p>
              count={orphans.data.count}, files_scanned={orphans.data.files_scanned},
              total_size={orphans.data.total_size}, truncated={String(orphans.data.truncated)}
            </p>
            <ul>
              {orphans.data.results.map((file) => (
                <li key={file.file_path}>
                  <label>
                    <input
                      type="checkbox"
                      checked={selected.has(file.file_path)}
                      onChange={() => toggle(file.file_path)}
                    />
                    {file.file_path} ({file.file_size} bytes, modified {file.modified_at})
                  </label>
                </li>
              ))}
            </ul>
            <div style={{ display: "flex", gap: "0.5rem" }}>
              <button disabled={!orphans.data.previous} onClick={() => setPage((p) => p - 1)}>
                Previous page
              </button>
              <button disabled={!orphans.data.next} onClick={() => setPage((p) => p + 1)}>
                Next page
              </button>
            </div>
          </>
        )}

        <div style={{ marginTop: "1rem", display: "flex", gap: "0.5rem" }}>
          <button
            disabled={selected.size === 0 || deleteOrphans.isPending}
            onClick={() => deleteOrphans.mutate(Array.from(selected), { onSuccess: () => setSelected(new Set()) })}
          >
            Delete selected ({selected.size})
          </button>
          <button
            onClick={() => {
              // Deliberately breaks the request — a path never present in the current snapshot,
              // per docs/CONTRACT.md §4's 400 rejection rule. Proves the error envelope renders
              // legibly rather than mocking the failure in a unit test.
              deleteOrphans.mutate(["not/a/real/file.txt"], {
                onError: (err) => setBreakError(err),
                onSuccess: () => setBreakError(null),
              });
            }}
          >
            Break it (delete an unknown path)
          </button>
        </div>
        {deleteOrphans.isError && <ErrorBanner error={deleteOrphans.error} />}
        {breakError !== null && <ErrorBanner error={breakError} />}
      </section>

      <section>
        <h2>Trigger a run (useTriggerCleanup)</h2>
        <label>
          <input type="checkbox" checked={dryRun} onChange={(e) => setDryRun(e.target.checked)} />
          dry_run
        </label>
        <button
          disabled={triggerCleanup.isPending}
          onClick={() => triggerCleanup.mutate({ dry_run: dryRun })}
        >
          Run full cleanup
        </button>
        {triggerCleanup.isError && <ErrorBanner error={triggerCleanup.error} />}
        {triggerCleanup.data && (
          <p>
            Run #{triggerCleanup.data.id}: status={triggerCleanup.data.status}, deleted=
            {triggerCleanup.data.files_deleted}, bytes_freed={triggerCleanup.data.bytes_freed}
          </p>
        )}
      </section>

      <section>
        <h2>Run history (useCleanupRuns)</h2>
        {runs.isLoading && <p>Loading…</p>}
        {runs.isError && <ErrorBanner error={runs.error} />}
        {runs.data && (
          <table border={1} cellPadding={4}>
            <thead>
              <tr>
                <th>id</th>
                <th>trigger</th>
                <th>status</th>
                <th>dry_run</th>
                <th>files_deleted</th>
                <th>bytes_freed</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {runs.data.results.map((run) => (
                <tr key={run.id}>
                  <td>{run.id}</td>
                  <td>{run.trigger}</td>
                  <td>{run.status}</td>
                  <td>{String(run.dry_run)}</td>
                  <td>{run.files_deleted}</td>
                  <td>{run.bytes_freed}</td>
                  <td>
                    <button onClick={() => setExpandedRunId(run.id)}>Inspect (useCleanupRun)</button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}

        {expandedRunId !== null && (
          <div style={{ marginTop: "1rem" }}>
            <h3>Run #{expandedRunId} detail</h3>
            {runDetail.isLoading && <p>Loading…</p>}
            {runDetail.isError && <ErrorBanner error={runDetail.error} />}
            {runDetail.data && (
              <ul>
                {runDetail.data.files.map((f) => (
                  <li key={f.id}>
                    {f.file_path} — deleted={String(f.deleted)}, quarantined={String(f.quarantined)}
                    {f.error ? ` — error: ${f.error}` : ""}
                  </li>
                ))}
              </ul>
            )}
          </div>
        )}
      </section>
    </main>
  );
}
