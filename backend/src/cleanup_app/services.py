"""This app's public callable interface, and the ONLY place a file is ever removed or moved.

Phase 3 implements ``OrphanScanner`` (``scan()``, ``build_reference_set()``) and
``CleanupService`` (``run()``, ``purge_history()``) exactly as ``docs/CONTRACT.md`` §3 specifies.

Every code path in this module that deletes or moves a file honours all four safety rails,
unconditionally, per this repo's ``CLAUDE.md`` rule 3 and ``docs/CONTRACT.md`` §0:

* **dry-run** — no storage call when ``dry_run=True``.
* **grace period** — a file modified within ``CLEANUP["GRACE_PERIOD_SECONDS"]`` is never a
  candidate.
* **exclude patterns** — ``CLEANUP["EXCLUDE_PATTERNS"]`` fnmatch globs are never candidates.
* **record-before-delete** — the ``CleanupRunFile`` row is written *before* the delete is
  attempted, never after.

These four rails govern ``CleanupService`` specifically. Upstream ``django_cleanup``'s own
per-save/per-delete deletion is a separate, pre-existing contract this package only observes
(logs, via the ``TRACK_AUTO_DELETIONS`` receiver) and never gates — it has already committed by
the time any receiver here runs (``docs/CONTRACT.md`` §9.4).
"""
