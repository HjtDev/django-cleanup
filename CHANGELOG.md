# Changelog

## [0.1.0] — 2026-08-31

### Added
- `cleanup_app` Django app: `CleanupRun`/`CleanupRunFile` models, `CleanupService` (dry-run,
  grace period, exclude patterns, record-before-delete), `OrphanScanner`.
- Admin-only DRF endpoints under `/api/v1/cleanup/admin/` (`orphans/`, `orphans/delete/`,
  `runs/`, `runs/{id}/`, `summary/`), gated by `IsAppAdmin`.
- Jazzmin orphan-review admin page.
- `@hjtdev/django-cleanup` frontend SDK: `useOrphanFiles`, `useDeleteOrphanFiles`,
  `useTriggerCleanup`, `useCleanupRuns`, `useCleanupRun`, `useCleanupSummary`, and the
  `cleanupKeys` query-key factory.

### Fixed
- `GET /runs/` accepted `status`/`trigger` query filters
  (`CleanupRunListCreateView.get_queryset()`) that `schema.yml` never declared, so the
  generated frontend types were missing them. Declared both as `OpenApiParameter`s on the
  view; `RunListParams` now derives them from the schema.
