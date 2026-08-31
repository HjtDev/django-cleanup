# Changelog

All notable changes to django-cleanup are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versioning is semantic across both
halves under one tag (`CLAUDE.md`'s Semver triggers).

## [1.0.0] — 2026-08-31

First tagged, published release — `hjtdev-django-cleanup` on PyPI and
`@hjtdev/django-cleanup` on npm. Everything below shipped across Phases 0–8; nothing was ever
tagged before this, so there is no earlier version to diff against.

### Added

**Models**
- `CleanupRun` — one row per cleanup pass (manual, scheduled, API-triggered, or upstream
  auto-deletion), tracking `status`, `trigger`, `initiated_by`, `dry_run`, timestamps, and
  `files_scanned`/`files_deleted`/`files_failed`/`bytes_freed` counters.
- `CleanupRunFile` — one row per file a run touched, linked to its `CleanupRun`, recording
  `file_path`, `file_size`, `deleted`, `quarantined`, and `error`.
- `OrphanFile` — an unmanaged admin-only proxy model over the live orphan scan snapshot, not a
  real table.

**Services — `cleanup_app.services`**
- `OrphanScanner.build_reference_set()` / `.scan(dry_run=False)` — walks every installed
  model's `FileField`/`ImageField` (via `_base_manager`, so a soft-delete default manager can't
  manufacture false orphans) and diffs it against configured storage. Cached per
  `CLEANUP["SCAN_CACHE_TIMEOUT"]`.
- `CleanupService.run()` / `.execute_run()` — the only code path that deletes or moves a file,
  honouring all four safety rails unconditionally:
  - **dry-run** — a `CleanupRunFile` row is written, but no storage call is made.
  - **grace period** (`CLEANUP["GRACE_PERIOD_SECONDS"]`, default 3600s) — a file modified more
    recently than the grace period is never considered a delete candidate.
  - **exclude patterns** (`CLEANUP["EXCLUDE_PATTERNS"]`) — `fnmatch` against both the full
    storage-relative path and the basename.
  - **record-before-delete** — the `CleanupRunFile` row is always created before the delete or
    quarantine attempt, never after.
- `CleanupService.purge_history(older_than_days=None)` — deletes old `CleanupRun`/
  `CleanupRunFile` rows only; never touches media storage.

**API — admin-only, under `/api/v1/cleanup/admin/`**
- `GET orphans/`, `POST orphans/delete/`, `GET/POST runs/`, `GET runs/<id>/`, `GET summary/` —
  six endpoints across five view classes, every one gated by `appkit.permissions.IsAppAdmin`
  with no exceptions. `urls.py` (the non-admin surface) ships intentionally empty.
- Six throttle scopes: `cleanup_orphans_list`, `cleanup_orphans_delete`, `cleanup_runs_list`,
  `cleanup_runs_trigger`, `cleanup_runs_retrieve`, `cleanup_summary` — a host must add rates for
  all six to `DEFAULT_THROTTLE_RATES` (see `README.md`).
- `POST runs/` optionally enqueues via Celery (`CLEANUP["USE_CELERY"]`) instead of running
  synchronously, when the `celery` extra is installed.

**Signals — frozen contract, payload changes are a MAJOR bump**
- `cleanup_run_started` — `run_id: int`, `trigger: str`, `dry_run: bool` (`sender=CleanupRun`).
- `cleanup_run_finished` — `run_id: int`, `status: str`, `files_deleted: int`,
  `bytes_freed: int` (`sender=CleanupRun`); fires on both the success and exception paths.

**Admin**
- Jazzmin orphan-review page (`OrphanFileAdmin`) with a confirm-then-delete flow: select
  files, confirm, and only then does `CleanupService.run()` execute — no accidental deletion
  from a single click. CSRF-protected twice over (template token + explicit
  `@method_decorator(csrf_protect)`).
- `CleanupRun`/`CleanupRunFile` admin views are read-only history — add/change/delete are all
  disabled; only `CleanupService.purge_history()` ever removes a history row.

**Celery / management command (optional)**
- `cleanup_app.tasks.run_scheduled_cleanup` and `cleanup_app.tasks.run_cleanup_run` — no worker
  required; the app is fully functional without Celery running.
- `manage.py cleanup_orphans [--dry-run] [--trigger ...]` — a cron-friendly alternative to
  Celery Beat.

**Settings — `CLEANUP` dict, all optional, all defaulted**
- `STORAGE_ALIAS`, `SCAN_ROOTS`, `EXCLUDE_PATTERNS`, `GRACE_PERIOD_SECONDS`, `QUARANTINE_DIR`,
  `MAX_FILES_PER_RUN`, `SCAN_CACHE_TIMEOUT`, `USE_CELERY`, `TRACK_AUTO_DELETIONS`,
  `HISTORY_RETENTION_DAYS`, `AUTO_CONNECT`, `SELECT_MODE`, `IGNORED_MODELS`. This app requires
  zero `.env` keys.

**Frontend — `@hjtdev/django-cleanup`**
- `useOrphanFiles`, `useCleanupRuns`, `useCleanupRun`, `useCleanupSummary` (queries) and
  `useDeleteOrphanFiles`, `useTriggerCleanup` (mutations), plus the `cleanupKeys` query-key
  factory. Both mutations fire only on an explicit user action — never on mount or a passive
  re-render.

**CI / release**
- `.github/workflows/ci.yml` — calls the org-level `HjtDev/.github` reusable workflow
  (backend tests on Postgres, frontend tests, resolution matrix, wheel smoke test, pip-audit,
  npm audit, README/version-lockstep/no-inter-app-import contract gates) plus this repo's own
  `publish-pypi` job.

**Host action:** add `cleanup_app` to `INSTALLED_APPS`, mount `cleanup_app.urls_admin` under
your admin API namespace, add the six throttle scopes above to `DEFAULT_THROTTLE_RATES`, and
run migrations. See `README.md` for the exact settings block.
