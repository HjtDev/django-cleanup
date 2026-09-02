# django-cleanup

Finds and removes orphaned media files a Django host's `FileField`/`ImageField`s no longer
reference, with a Jazzmin review page, full cleanup history, and auto-hooking via upstream
[`django-cleanup`](https://pypi.org/project/django-cleanup/).

- **Importable module:** `cleanup_app` — never `django_cleanup`, which upstream `django-cleanup`
  already owns in the same `site-packages`.
- **PyPI distribution:** `hjtdev-django-cleanup`. **npm package:** `@hjtdev/django-cleanup`.
- Upstream `django-cleanup` (imported as `django_cleanup`) is a real, versioned *dependency* of
  this package, not something it reimplements — see "Compatibility" below for why it must never
  also appear in a host's own `INSTALLED_APPS`.
- No user-facing surface, ever: every endpoint and every admin page is gated by
  `appkit.permissions.IsAppAdmin` (`is_authenticated and is_staff`), with zero exceptions.

## Installation — backend

Published to PyPI:

```bash
uv add "hjtdev-django-cleanup>=1.0,<2.0"
```

Pinning an unreleased commit instead of a tagged release still works via the git+subdirectory
form:

```bash
uv add "git+https://github.com/HjtDev/django-cleanup.git@v1.0.1#subdirectory=backend"
```

Optional extra: `hjtdev-django-cleanup[celery]` adds `celery[redis]>=5.4,<6.0` and
`django-celery-beat>=2.7,<3.0`, for enqueuing `POST /runs/` and running a scheduled cleanup via
Celery beat. **This app is fully functional with no Celery worker running at all** — a host
without the extra installed uses the `cleanup_orphans` management command via plain cron instead
(see "Recommended periodic schedule" below).

## Prerequisite — wire `appkit` first

This app depends on [`hjtdev-appkit`](https://pypi.org/project/hjtdev-appkit/) for its error
envelope, pagination, and permission class, but does not wire appkit's own settings for a host —
that's the host's job, and skipping it fails **silently**. `appkit`'s own system checks
(`appkit.E001`/`E002`) only run if `appkit` is listed in `INSTALLED_APPS` at all; omitting it
entirely trips nothing. The only symptom is a wrong response shape: a non-staff request to any
endpoint below still 403s, but with DRF's bare `{"detail": "..."}` instead of appkit's documented
error envelope.

**Already on `base-scaffold`? This whole block is already done for you.** Every line below —
`appkit` in `INSTALLED_APPS`, `RequestIDMiddleware` positioned right after `SecurityMiddleware`,
both `REST_FRAMEWORK` keys, the `request_id` logging filter — ships in the scaffold's own
`backend/config/settings.py`/`logging.py` from a fresh clone. Verify it's there rather than
re-adding it; a second copy of the middleware entry is a silent duplicate, not an error. This
section exists for a host that isn't on `base-scaffold`, or that removed appkit's wiring. Before
adding the settings block further down, make sure a host already has:

```python
INSTALLED_APPS += ["appkit"]

MIDDLEWARE += ["appkit.request_id.RequestIDMiddleware"]  # right after SecurityMiddleware

REST_FRAMEWORK["EXCEPTION_HANDLER"] = "appkit.exceptions.standard_exception_handler"
REST_FRAMEWORK["DEFAULT_PAGINATION_CLASS"] = "appkit.pagination.DefaultPagination"

LOGGING["filters"]["request_id"] = {"()": "appkit.request_id.RequestIDFilter"}  # else appkit.W005
```

See `hjtdev-appkit`'s own README for its full settings surface (`APPKIT["TRUSTED_PROXY_COUNT"]`,
etc.).

## Compatibility

- Python 3.13+ · Django 5.2–6.x · DRF 3.15+ · `hjtdev-appkit` 2.x · `django-cleanup` 9.x
- Requires `django.contrib.contenttypes` (present by default with the admin).
- **Never add `django_cleanup` to `INSTALLED_APPS` yourself** — not `"django_cleanup"` and not
  `"django_cleanup.apps.CleanupConfig"`. `cleanup_app`'s own `AppConfig.ready()` calls
  `django_cleanup.cache.prepare()`/`handlers.connect()` directly via plain Python import, so
  upstream's auto-hook works with zero `INSTALLED_APPS` entry of its own. Listing `django_cleanup`
  explicitly makes *its* `ready()` populate the cache first, silently turning this app's own
  `SELECT_MODE`/`IGNORED_MODELS` settings into a no-op if either is set to something other than its
  default — `cleanup_app` detects that specific combination (cache already populated *and*
  `SELECT_MODE`/`IGNORED_MODELS` non-default) and raises `ImproperlyConfigured` rather than failing
  silently. With both settings left at their defaults there's nothing for the guard to protect, so
  it doesn't raise in that case either — the fix either way is simply: don't add `django_cleanup`.

## Settings — add to `backend/config/settings.py`

If your host runs mypy in strict mode with `django-stubs` (`base-scaffold` does), both the
`.update()` call and the bare `CLEANUP = {...}` below need the two small additions marked inline —
without them, strict mypy reports `"object" has no attribute "update"` and `Need type annotation
for "CLEANUP"` respectively, even though the file imports and runs correctly either way:

```python
INSTALLED_APPS += ["cleanup_app"]

MIDDLEWARE += []  # none required

REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"].update({  # type: ignore[attr-defined]  # only if your
    "cleanup_orphans_list": "60/min",              # host's REST_FRAMEWORK dict isn't itself
    "cleanup_orphans_delete": "20/min",             # annotated dict[str, Any] — see above
    "cleanup_runs_list": "60/min",
    "cleanup_runs_trigger": "20/min",
    "cleanup_runs_retrieve": "60/min",
    "cleanup_summary": "60/min",
})

CLEANUP: dict[str, Any] = {  # dict[str, Any] needed under mypy --strict; `Any` from `typing`
    "STORAGE_ALIAS": "default",       # which configured storage backend to scan;
                                       # "default" resolves to django's default_storage
    "SCAN_ROOTS": None,                # None = walk the whole storage backend; else a list
                                        # of path prefixes to scope the walk to
    "EXCLUDE_PATTERNS": [],            # fnmatch globs; a matching file is never a candidate
                                        # orphan regardless of reference status
    "GRACE_PERIOD_SECONDS": 3600,      # a file modified more recently than this is never a
                                        # candidate — protects in-progress uploads and files
                                        # referenced by an uncommitted transaction. Smoke-testing
                                        # right after creating a file? Lower this or wait — a
                                        # too-recent file silently scores 0 candidates, not an
                                        # error, and this default is a full hour.
    "QUARANTINE_DIR": None,            # None = hard delete via storage.delete(); set = move
                                        # the file there instead of deleting
    "MAX_FILES_PER_RUN": 5000,         # caps candidates per scan()/run() call;
                                        # OrphanScanResult.truncated reports whether the cap
                                        # was hit
    "SCAN_CACHE_TIMEOUT": 300,         # seconds the OrphanScanner.scan() snapshot is
                                        # cached — what makes GET /orphans/ pagination never
                                        # re-walk storage per page
    "USE_CELERY": False,               # True makes POST /runs/ enqueue instead of running
                                        # inline, if the celery extra is installed — the view
                                        # checks for celery's presence rather than hard-importing it
    "TRACK_AUTO_DELETIONS": True,      # connects the receiver logging what upstream
                                        # django_cleanup deletes on save/delete into
                                        # CleanupRun(trigger="auto") rows
    "HISTORY_RETENTION_DAYS": 90,      # default window for CleanupService.purge_history()
                                        # when older_than_days isn't passed
    "AUTO_CONNECT": True,              # whether this app's own AppConfig.ready() calls
                                        # django_cleanup.cache.prepare()/handlers.connect()
                                        # at all
    "SELECT_MODE": False,              # maps to upstream's CleanupSelectedConfig vs.
                                        # CleanupConfig: False = every model with a FileField
                                        # is auto-hooked except those explicitly marked
                                        # cleanup_ignore; True = only models explicitly
                                        # marked cleanup_select are hooked
    "IGNORED_MODELS": [],              # list of "app_label.ModelName" strings — protective,
                                        # not subtractive; see "Safety rails" below
}
```

Every key is optional — a host omitting `CLEANUP` entirely, or omitting any individual key, gets
the documented default above. `IGNORED_MODELS` marks a model via upstream's `cleanup.ignore()` so
upstream stops auto-deleting its files on save/delete, but the orphan scanner's own reference set
still includes that model's currently referenced files — a live row's file is never a
false-positive orphan, in either `SELECT_MODE`.

## Required `.env` keys

None. This app requires no `.env` keys, under any extra — it configures entirely through the
`CLEANUP` dict above.

## URL mounting — add to `backend/config/urls.py`

```python
path("api/v1/cleanup/admin/", include("cleanup_app.urls_admin")),
```

`urls_admin.py` is the only meaningful URLconf this app ships. `cleanup_app.urls` (the
conventional user-facing URLconf every app in this ecosystem also exposes) ships **intentionally
empty** — this app has no user-facing surface at all, so including it yields zero routes, not an
`ImportError`. The `admin/` segment above is part of the mount *prefix*, not something the
frontend SDK adds on your behalf beyond its own basePath: the SDK's basePath is only
`/api/v1/cleanup` (see "Usage — frontend" below), and its manager appends `admin/` itself when
building every request path.

Also add the one-line `banned-api` entry `INTEGRATION-GUIDE.md` §2 step 10 asks for from every
installed app, in `backend/pyproject.toml`:

```toml
"cleanup_app".msg = "Import app packages only from core/ or config/ — INTEGRATION-GUIDE.md §4"
```

## Migrations

```bash
docker compose exec backend python manage.py migrate cleanup_app   # containerized host
uv run python manage.py migrate cleanup_app                        # outside Docker
```

Two migrations: `CleanupRun`/`CleanupRunFile` (real tables), and `OrphanFile` (migration *state*
only — `OrphanFile.Meta.managed = False`, so this never creates a table; its rows come from a live
`OrphanScanner.scan()`, never a database).

## Safety rails

Every code path that removes or moves a file goes through `CleanupService` and honours all four of
these, unconditionally:

| Rail | Governed by | Where it's enforced |
|---|---|---|
| **Dry-run** | `dry_run=True` on `CleanupService.run()`/`execute_run()` | No `storage.delete()`/quarantine call is ever made; every `CleanupRunFile` row is written with `deleted=False` |
| **Grace period** | `CLEANUP["GRACE_PERIOD_SECONDS"]` | A file modified more recently than this is never a scan candidate at all — applied inside `OrphanScanner.scan()`, so every consumer (API, admin page, management command) inherits it from the same snapshot |
| **Exclude patterns** | `CLEANUP["EXCLUDE_PATTERNS"]` (fnmatch globs) | Same as above — a matching file is never a candidate, checked at scan time |
| **Record-before-delete** | always on | The `CleanupRunFile` row for a file is created *before* the delete/quarantine attempt, never after — one file's failure can never leave an undocumented deletion |

Two more settings shape what "delete" means, without weakening any rail above:
`CLEANUP["QUARANTINE_DIR"]` — if set, a candidate is moved there instead of hard-deleted via
`storage.delete()`. And as defence-in-depth, any client-supplied path not present in the *current*
cached scan snapshot (`POST /orphans/delete/`, the admin delete action) is rejected outright and
never touched on disk.

**Scope:** these four rails govern `CleanupService` specifically. Upstream `django_cleanup`'s own
per-save/per-delete deletion is a separate, pre-existing contract this package only *observes* —
via the `TRACK_AUTO_DELETIONS` receiver, which logs a `CleanupRun(trigger="auto")` row — and never
gates; the file is already gone by the time that receiver runs. A host that wants those files
rail-governed instead should add the model to `CLEANUP["IGNORED_MODELS"]` and let the scanner find
and clean the resulting dangling files on its own schedule, under its own rails.

## Endpoints

All under `urls_admin.py`, all `permission_classes = [IsAppAdmin]` (imported from
`appkit.permissions.IsAppAdmin`, never reimplemented — there is no lesser permission tier to fall
back to). Paths below are relative to wherever a host mounts `urls_admin.py`
(`/api/v1/cleanup/admin/` above).

| Method | Path | Throttle scope | Request | Response |
|---|---|---|---|---|
| `GET` | `orphans/` | `cleanup_orphans_list` | query: `page`, `page_size` | `200` — paginated `{file_path, file_size, modified_at}` list, served from the cached scan snapshot |
| `POST` | `orphans/delete/` | `cleanup_orphans_delete` | `{"file_paths": ["..."]}` | `202` with the resulting `CleanupRun`; `400` if any path isn't in the current snapshot |
| `GET` | `runs/` | `cleanup_runs_list` | query: `page`, `page_size`, optional `status`/`trigger` | `200` — paginated `CleanupRun` history |
| `POST` | `runs/` | `cleanup_runs_trigger` | `{"dry_run": bool}` (optional) | `200` with the finished run if synchronous, or `202` with a `PENDING` run if `CLEANUP["USE_CELERY"]` enqueued it |
| `GET` | `runs/<int:pk>/` | `cleanup_runs_retrieve` | — | `200` — a `CleanupRun` plus its `CleanupRunFile` rows |
| `GET` | `summary/` | `cleanup_summary` | — | `200` — `{total_runs, files_deleted_total, bytes_freed_total, last_run_at, last_run_status}` |

## Signals emitted (contract — payload changes are a MAJOR bump)

| Signal | Payload kwargs |
|---|---|
| `cleanup_run_started` | `run_id: int`, `trigger: str`, `dry_run: bool` |
| `cleanup_run_finished` | `run_id: int`, `status: str`, `files_deleted: int`, `bytes_freed: int` |

Both fire with `sender=CleanupRun` (the class, not an instance), so a host receiver filters with
`@receiver(cleanup_run_finished, sender=CleanupRun)`. Payloads are deliberately minimal — a
receiver that needs more (e.g. `initiated_by`, `error`) fetches the row by `run_id`.

## Services (public callables)

| Method | Signature |
|---|---|
| `OrphanScanner.build_reference_set` | `() -> set[str]` |
| `OrphanScanner.scan` | `(*, dry_run: bool = False) -> OrphanScanResult` |
| `CleanupService.run` | `(*, trigger: str = "manual", dry_run: bool = False, file_paths: list[str] \| None = None, initiated_by: AbstractBaseUser \| None = None) -> CleanupRun` |
| `CleanupService.execute_run` | `(run: CleanupRun, *, file_paths: list[str] \| None = None) -> CleanupRun` |
| `CleanupService.purge_history` | `(*, older_than_days: int \| None = None) -> int` |

`OrphanScanner.scan()` returns an `OrphanScanResult(files: list[OrphanFileInfo], total_size: int,
files_scanned: int, truncated: bool)`, where `OrphanFileInfo` is `(path: str, size: int,
modified_at: datetime)`. `truncated` is `True` when `CLEANUP["MAX_FILES_PER_RUN"]` capped the
result. `CleanupService.execute_run()` is the method `run()` delegates to once a `CleanupRun` row
already exists (e.g. the Celery-enqueued path); most callers only ever need `run()`.
`purge_history()` touches only history tables — it never removes anything from storage.

## Test helpers

`cleanup_app.factories` exports `CleanupRunFactory` and `CleanupRunFileFactory` for host tests. Add
`factory-boy` to your own test dependency group to use them — it is a contributor-only dependency
of this package, never installed by `pip install hjtdev-django-cleanup` or by the `[celery]`
extra. Neither factory sets `initiated_by` (nullable, defaults to `None`) — pass in a real user
from your own test fixtures.

## Recommended periodic schedule (optional)

Two equivalent paths — pick whichever fits your host, since Celery is optional here:

```
# Without Celery — plain cron:
0 3 * * * cd /path/to/project && python manage.py cleanup_orphans

# With the [celery] extra + django_celery_beat:
cleanup_orphans — daily at 03:00 — cleanup_app.tasks.run_scheduled_cleanup
```

Neither path self-registers — a cron host adds the crontab line above; a Celery host creates the
actual `django_celery_beat` schedule entry pointing at
`cleanup_app.tasks.run_scheduled_cleanup`. Both share the same concurrency guard: skipped (logged,
no-op) if a `CleanupRun` with `trigger="scheduled"` and `status` in `(pending, running)` already
exists, so a slow run is never doubled up. The management command also accepts `--dry-run` and
`--trigger {manual,scheduled,api,auto}` (default `scheduled`) for one-off use, and exits non-zero
via `CommandError` if the run it created ended up `FAILED`.

Separately, `cleanup_app.tasks.run_cleanup_run(run_id)` is the Celery task `POST /runs/` enqueues
when `CLEANUP["USE_CELERY"]` is on — it drives an already-created run, and is not itself something
a host schedules.

## Suggested Jazzmin icon

The orphan-review page (`/admin/cleanup_app/orphanfile/`) is a real, registered `ModelAdmin` — it
appears in the Jazzmin sidebar with **zero** `JAZZMIN_SETTINGS` edits required. Icons are purely
optional:

```python
JAZZMIN_SETTINGS = {
    "icons": {
        "cleanup_app.CleanupRun": "fas fa-broom",
        "cleanup_app.CleanupRunFile": "fas fa-file-circle-xmark",
        "cleanup_app.OrphanFile": "fas fa-trash-can",
    },
}
```

The page lists every candidate orphan from a live scan and deletes only through a same-page
confirm step (`action=delete` renders a confirmation; only the follow-up
`action=delete&confirm=yes` actually calls `CleanupService.run()`) — every selected path is
re-validated against the current scan snapshot first, same as the API's `POST /orphans/delete/`.

## Installation — frontend

```bash
npm install @hjtdev/appkit               # if not already installed
npm install @hjtdev/django-cleanup@1.0.1 # pin to the same tag as the backend half
```

## Usage — add this app's basePath to the shared provider, then import hooks from the package root

**basePath key: `cleanup`** — add it to the `basePaths` map on the `ApiClientProvider` every
installed app shares (one provider for the whole host, mounted once):

```tsx
// frontend/app/providers.tsx — one-time wiring per host, one basePaths entry per app
import { ApiClientProvider } from "@hjtdev/appkit";
import { apiClient } from "@/lib/api-client";

<ApiClientProvider
  client={apiClient}
  basePaths={{
    // ...entries for already-installed apps stay here
    cleanup: "/api/v1/cleanup",
  }}
>
  {children}
</ApiClientProvider>;
```

```tsx
import {
  useOrphanFiles,
  useDeleteOrphanFiles,
  useTriggerCleanup,
  useCleanupRuns,
  useCleanupRun,
  useCleanupSummary,
  cleanupKeys,
} from "@hjtdev/django-cleanup";

function OrphanReviewPanel() {
  const { data: orphans } = useOrphanFiles();
  const { mutate: deleteOrphans } = useDeleteOrphanFiles();
  const { data: runs } = useCleanupRuns();
  const { mutate: triggerCleanup } = useTriggerCleanup();
  const { data: summary } = useCleanupSummary();
  // useCleanupRun(id) fetches one run's detail (its CleanupRunFile rows) on demand.
  // cleanupKeys is exported too, for a host that needs to invalidate this app's
  // cache from its own composed code.
  // ...
}
```

Both mutation hooks (`useDeleteOrphanFiles`, `useTriggerCleanup`) only ever fire from an explicit
`mutate()`/`mutateAsync()` call — never on mount or a passive render, since both are irreversible
once `dry_run` is false.

Requires the host's `@tanstack/react-query` `QueryClientProvider` to already be mounted and
`appkit`'s `ApiClientProvider` mounted above wherever these hooks are used, with the `cleanup`
key above present in its `basePaths` map. No further frontend configuration needed.

Every endpoint behind these hooks is admin-only (`appkit.permissions.IsAppAdmin`) — a
non-staff user's request 403s at the API regardless of what the frontend renders.

Exported types: `CleanupRun`, `CleanupRunDetail`, `CleanupRunFile`, `CleanupRunStatus`,
`CleanupRunTrigger`, `CleanupSummary`, `HttpClient`, `OrphanFile`, `OrphanListParams`,
`PaginatedCleanupRunList`, `PaginatedOrphanFileList`, `RunListParams`, `TriggerCleanupOptions`.
