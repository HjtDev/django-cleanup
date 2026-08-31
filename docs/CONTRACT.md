# CONTRACT.md — hjtdev-django-cleanup

The frozen public contract for `hjtdev-django-cleanup` (module: `cleanup_app`). Every later build
phase (`docs/CLAUDE-CODE-GUIDE-APP-MEDIA-CLEANUP.md` §2) implements exactly what's written here —
it does not re-derive model shapes, signal payloads, service signatures, endpoints, settings, or
hooks. If code and this file ever disagree, that disagreement is a bug in one of them, not a
license to improvise; `docs/APP-DESIGN.md` §11 requires resolving it and updating whichever side
is wrong before a release.

**Sources checked while writing this**, not assumed from the guide's prose: `django-cleanup`
9.0.0's actual installed source (`django_cleanup/{cleanup,apps,cache,handlers,signals}.py`) and
`hjtdev-appkit` 2.0.1's actual source (`appkit/{permissions,pagination,mixins,cache,throttling,
media}.py`). Every upstream fact and every appkit symbol named below was read from those files,
not recalled from documentation. §9 records the five places that reading changed or sharpened what
`docs/CLAUDE-CODE-GUIDE-APP-MEDIA-CLEANUP.md` says.

---

## §0. Identity & boundary

| | |
|---|---|
| Importable module | `cleanup_app` (never `django_cleanup` — upstream owns that name in the same `site-packages`) |
| PyPI distribution | `hjtdev-django-cleanup` |
| npm package | `@hjtdev/django-cleanup` |
| GitHub repo | `HjtDev/django-cleanup` |
| Declared dependencies (not app packages, §1.1's named exceptions) | `hjtdev-appkit>=2.0,<3.0`, `django-cleanup>=9.0,<10.0` |
| User-facing surface | **None.** `urls.py` ships empty. Every endpoint and admin surface is gated by `appkit.permissions.IsAppAdmin` (`is_authenticated and is_staff`) with zero exceptions — there is no lesser permission tier to fall back to. |
| The four delete rails | Every code path that removes or moves a file goes through `services.CleanupService`, unconditionally: **dry-run** (no storage call when `dry_run=True`), **grace period** (a file modified within `CLEANUP["GRACE_PERIOD_SECONDS"]` is never a candidate), **exclude patterns** (`CLEANUP["EXCLUDE_PATTERNS"]` fnmatch globs are never candidates), **record-before-delete** (the `CleanupRunFile` row is written *before* the delete is attempted, never after). These four rails govern `CleanupService` specifically — see §9 item 4 for why upstream's own per-save/per-delete deletion is a separate, pre-existing contract this package only *observes*, never gates. |

---

## §1. Models

Every FK-shaped reference below is `settings.AUTH_USER_MODEL` or nothing. None reaches outside
this package. **Requires another app package: No.**

### `CleanupRun`

```python
class CleanupRun(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending"
        RUNNING = "running"
        SUCCESS = "success"
        FAILED = "failed"
        PARTIAL = "partial"

    class Trigger(models.TextChoices):
        MANUAL = "manual"        # a human clicked "run" in the admin or API
        SCHEDULED = "scheduled"  # tasks.run_scheduled_cleanup or the management command
        API = "api"              # POST /runs/ from an external caller
        AUTO = "auto"            # upstream's own per-save/per-delete deletions, logged (§9.4)

    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)
    trigger = models.CharField(max_length=10, choices=Trigger.choices)
    initiated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="cleanup_runs",
    )
    dry_run = models.BooleanField(default=False)
    started_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    files_scanned = models.PositiveIntegerField(default=0)
    files_deleted = models.PositiveIntegerField(default=0)
    files_failed = models.PositiveIntegerField(default=0)
    bytes_freed = models.PositiveBigIntegerField(default=0)
    error = models.TextField(blank=True)

    class Meta:
        indexes = [
            models.Index(fields=["status", "-started_at"]),
            models.Index(fields=["trigger"]),
        ]
```

`initiated_by` types as `settings.AUTH_USER_MODEL | None` at runtime; in type hints elsewhere in
this contract it's written `AbstractBaseUser | None` (`django.contrib.auth.base_user` — Django
core, not a concrete `User` import and not another app package).

**`Trigger` has four values, not the three the build guide's prompt lists** — see §9.4. An `AUTO`
run can never carry `PENDING`/`RUNNING` status (§9.4), which is what keeps it from ever tripping
the `SCHEDULED` concurrency guard in §3.

### `CleanupRunFile`

```python
class CleanupRunFile(models.Model):
    run = models.ForeignKey(CleanupRun, on_delete=models.CASCADE, related_name="files")
    file_path = models.CharField(max_length=1024)
    file_size = models.PositiveBigIntegerField(default=0)
    deleted = models.BooleanField(default=False)
    quarantined = models.BooleanField(default=False)
    error = models.TextField(blank=True)

    class Meta:
        indexes = [models.Index(fields=["run", "deleted"])]
```

### The orphan-review page's backing model — decision

**Option A: an unmanaged model**, evaluated against Option B (a custom `admin_views.py` view) and
chosen. Full reasoning and implementation shape in §6 (it's an admin surface, not a data model —
`Meta.managed = False` means no migration, no table, ever).

---

## §2. Signals

```python
# cleanup_app/signals.py
import django.dispatch

cleanup_run_started = django.dispatch.Signal()
"""Sent when CleanupService.run() begins. sender=CleanupRun.
Payload: run_id: int, trigger: str, dry_run: bool"""

cleanup_run_finished = django.dispatch.Signal()
"""Sent when CleanupService.run() completes (success, partial, or failed). sender=CleanupRun.
Payload: run_id: int, status: str, files_deleted: int, bytes_freed: int"""
```

**Minimality argument** (`APP-DESIGN.md` §6: adding a kwarg later is a minor bump, removing one is
major — err toward too few):

- `cleanup_run_started` carries just enough for a host receiver to log or gate on the run without
  a query: which run (`run_id`), why it started (`trigger`), and whether it will touch storage
  (`dry_run`). `initiated_by` is deliberately omitted — a host that needs it can fetch the row by
  `run_id`; including a nullable FK-shaped value in a signal payload invites a receiver to treat it
  as more stable than it is.
- `cleanup_run_finished` carries the four numbers a host dashboard or alert would otherwise have to
  query for: outcome (`status`), and the two headline metrics (`files_deleted`, `bytes_freed`).
  `files_scanned`/`files_failed`/`error` are omitted — all three are reachable via
  `CleanupRun.objects.get(pk=run_id)`, and `error` in particular is exactly the kind of
  free-text field that grows over time in ways a fixed signal payload shouldn't be coupled to.

Both signals fire with `sender=CleanupRun` (a class, not an instance — the model this event is
about, following `APP-DESIGN.md` §6's own `sender=Notification` example) so a host's
`core/signals.py` receiver can filter with `@receiver(cleanup_run_finished, sender=CleanupRun)`.

**Requires another app package: No.**

---

## §3. `services.py`

```python
from dataclasses import dataclass
from datetime import datetime
from django.contrib.auth.base_user import AbstractBaseUser


@dataclass(frozen=True)
class OrphanFileInfo:
    path: str
    size: int
    modified_at: datetime


@dataclass(frozen=True)
class OrphanScanResult:
    files: list[OrphanFileInfo]
    total_size: int
    files_scanned: int
    truncated: bool


class OrphanScanner:
    @staticmethod
    def build_reference_set() -> set[str]:
        """Every file name any installed model's FileField/ImageField currently points at,
        across every model — including one only reachable via a reverse relation, since this
        walks apps.get_models() directly rather than following relations from a starting model.
        A model in CLEANUP["IGNORED_MODELS"] is still included here (§9.1) — this set is purely
        protective, and dropping a model from it would make every file its live rows reference
        into a false-positive orphan.
        """
        ...

    @staticmethod
    def scan(*, dry_run: bool = False) -> OrphanScanResult:
        """Walk CLEANUP["STORAGE_ALIAS"] (default_storage if "default"), scoped to SCAN_ROOTS if
        set. A file is a candidate orphan iff: not in build_reference_set(), not matching any
        CLEANUP["EXCLUDE_PATTERNS"] glob, and storage.get_modified_time() is older than
        CLEANUP["GRACE_PERIOD_SECONDS"] ago. Capped at CLEANUP["MAX_FILES_PER_RUN"]; truncated=True
        on the result if the cap was hit. Caches the snapshot under
        appkit.cache.build_cache_key("cleanup", "orphans") via appkit.cache.cached_call, timeout
        CLEANUP["SCAN_CACHE_TIMEOUT"]. dry_run is accepted for signature symmetry with
        CleanupService.run() but scan() never writes to storage regardless of its value — it only
        reads and lists.
        """
        ...


class CleanupService:
    @staticmethod
    def run(
        *,
        trigger: str = "manual",
        dry_run: bool = False,
        file_paths: list[str] | None = None,
        initiated_by: AbstractBaseUser | None = None,
    ) -> "CleanupRun":
        """Create a CleanupRun(status=RUNNING, trigger=trigger, dry_run=dry_run,
        initiated_by=initiated_by), send cleanup_run_started. If file_paths is given, operate only
        on that subset of the CURRENT cached OrphanScanner snapshot (rejecting any path not
        present in it is the caller's job — see §4's POST /orphans/delete/ — this method trusts
        its input); otherwise run a fresh OrphanScanner.scan(). For every candidate file: create
        its CleanupRunFile row (deleted=False) FIRST, then attempt delete-or-quarantine
        (CLEANUP["QUARANTINE_DIR"] set -> move there; otherwise storage.delete()), then update that
        same row with the outcome. dry_run=True writes every row with deleted=False and performs
        no storage operation at all. One file's failure never aborts the remaining files. On
        completion: status=SUCCESS if zero failures, PARTIAL if some failed, FAILED if all failed
        or an unhandled exception occurred; sets finished_at and the four aggregate counts; sends
        cleanup_run_finished. Returns the finished CleanupRun.
        """
        ...

    @staticmethod
    def purge_history(*, older_than_days: int | None = None) -> int:
        """Delete CleanupRun rows (cascading their CleanupRunFile rows) older than
        older_than_days, or CLEANUP["HISTORY_RETENTION_DAYS"] if None. Returns the count of
        CleanupRun rows deleted. Touches only history tables — never media storage.
        """
        ...
```

**`OrphanScanResult` carries `files_scanned` and `truncated` beyond the build guide's stated
`files, total_size`** — see §9.5; without them, hitting `MAX_FILES_PER_RUN` is invisible to both
the API response and the admin page.

**`OrphanScanResult.files` is `list[OrphanFileInfo]`, not `list[str]`** — see §9.7; `scan()`
already stats every candidate to apply the grace-period rail and compute `total_size`, so a bare
path would discard data this module has already paid to fetch and force §4's `GET /orphans/`
(`{file_path, file_size, modified_at}`) to re-stat every file on every page instead of reading it
from the cached snapshot.

**Requires another app package: No.**

---

## §4. Endpoints

All under `urls_admin.py`, all `permission_classes = [IsAppAdmin]` (imported from
`appkit.permissions`, not reimplemented — §5's rule), all with an `@extend_schema` and
`tags=["cleanup-admin"]`. `urls.py` is present and intentionally empty.

| Method | Path | Throttle scope | Request | Response |
|---|---|---|---|---|
| `GET` | `/orphans/` | `cleanup_orphans_list` | query: `page`, `page_size` | Paginated list of `{file_path, file_size, modified_at}`, served from the cached `OrphanScanner` snapshot — a miss triggers exactly one scan, a hit never re-scans storage |
| `POST` | `/orphans/delete/` | `cleanup_orphans_delete` | `{"file_paths": ["..."]}` | `202` with the resulting `CleanupRun` id + summary. Rejects (`400`) any path not present in the current snapshot — never accepts an arbitrary client-supplied path. Calls `CleanupService.run(trigger="api", file_paths=...)`, then `appkit.cache.invalidate_namespace("cleanup")` **after** the run completes (validation happens first, invalidation last, so a rejected request never busts a good snapshot) |
| `GET` | `/runs/` | `cleanup_runs_list` | query: `page`, `page_size`, optional `status`/`trigger` filters | Paginated `CleanupRun` history |
| `POST` | `/runs/` | `cleanup_runs_trigger` | `{"dry_run": bool}` (optional) | If `CLEANUP["USE_CELERY"]` and celery is importable: enqueue, return `202` with a `PENDING` `CleanupRun`. Otherwise run `CleanupService.run(trigger="api", ...)` synchronously and return `200` with the finished run |
| `GET` | `/runs/{id}/` | `cleanup_runs_retrieve` | — | Single `CleanupRun` + its `CleanupRunFile` rows (`select_related`/`prefetch_related`, no N+1) |
| `GET` | `/summary/` | `cleanup_summary` | — | `{total_runs, files_deleted_total, bytes_freed_total, last_run_at, last_run_status}`, cached short-lived |

**The six throttle scope strings above are literals, not `appkit.throttling.throttle_scope(...)`
calls** — see §9.3; that helper rejects any argument containing `_`, and every name here has one.
`appkit.checks`' W004 system check still validates each literal against
`REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"]` regardless of how the string was produced.

`GET /orphans/` additionally uses `appkit.mixins.CachedListMixin` with
`cache_namespace="cleanup"` for its own response caching (a second, independent cache layer from
the scan snapshot — one caches "the scan result," the other caches "this serialized page of it").

**Requires another app package: No.**

---

## §5. Settings — `CLEANUP` dict, → `conf.py` `DEFAULTS`

| Key | Default | Meaning |
|---|---|---|
| `STORAGE_ALIAS` | `"default"` | Which configured storage backend to scan; `"default"` resolves to `django.core.files.storage.default_storage` |
| `SCAN_ROOTS` | `None` | `None` = walk the whole storage backend; else a list of path prefixes to scope the walk to |
| `EXCLUDE_PATTERNS` | `[]` | `fnmatch` globs; a matching file is never a candidate orphan regardless of reference status |
| `GRACE_PERIOD_SECONDS` | `3600` | A file modified more recently than this is never a candidate — protects in-progress uploads and files referenced by an uncommitted transaction |
| `QUARANTINE_DIR` | `None` | `None` = hard delete via `storage.delete()`. Set = move the file there instead of deleting |
| `MAX_FILES_PER_RUN` | `5000` | Caps candidates per `scan()`/`run()` call; `OrphanScanResult.truncated` reports whether the cap was hit |
| `SCAN_CACHE_TIMEOUT` | `300` | Seconds the `OrphanScanner.scan()` snapshot is cached — this is what makes `GET /orphans/` pagination never re-walk storage per page |
| `USE_CELERY` | `False` | `True` makes `POST /runs/` enqueue instead of running inline, **if** the `celery` extra is installed — the view checks for celery's presence rather than hard-importing it |
| `TRACK_AUTO_DELETIONS` | `True` | Connects the receiver in §9.4 to upstream's `cleanup_post_delete`, logging what upstream deletes on save/delete into `CleanupRun(trigger="auto")` rows |
| `HISTORY_RETENTION_DAYS` | `90` | Default window for `CleanupService.purge_history()` when `older_than_days` isn't passed |
| `AUTO_CONNECT` | `True` | Whether this app's own `AppConfig.ready()` calls `django_cleanup.cache.prepare()`/`handlers.connect()` at all. `False` means a host wires upstream itself (rare — only useful if a host also lists `django_cleanup.apps.CleanupConfig` explicitly and wants to own the call order) |
| `SELECT_MODE` | `False` | Maps to upstream's `CleanupSelectedConfig` vs. `CleanupConfig`: `False` = every model with a FileField is auto-hooked except those explicitly marked `cleanup_ignore`; `True` = only models explicitly marked `cleanup_select` are hooked. `IGNORED_MODELS` below still applies as the ignore-list in `False` mode (its literal purpose) and, in `True` mode, as the mechanism to keep those models permanently un-hooked regardless of whether something later marks them `cleanup_select` |
| `IGNORED_MODELS` | `[]` | List of `"app_label.ModelName"` strings. Marks each via upstream's `cleanup.ignore()` in `ready()` — see §9.1 for exactly what this does and does not exclude |

**`IGNORED_MODELS` semantics — the one place this contract departs from a literal reading of the
build guide, confirmed with the project owner (§9.1):** it is **protective, not subtractive**. A
model's `FileField` values are marked in upstream so upstream stops auto-deleting them on
save/delete — but `OrphanScanner.build_reference_set()` still includes that model's currently
referenced files, so a *live* row's file is never a false-positive orphan. The two paths therefore
always agree: neither path deletes a file a live, ignored-model row still points at. A file left
dangling after an ignored model's row is deleted is a genuine orphan in both views and remains
cleanable — that's the scanner's whole job, and the failure mode `IGNORED_MODELS` exists to prevent
is losing a file a database row still needs, not permanently protecting every file an ignored model
ever touched.

**`AUTO_CONNECT` has an ordering hazard, not just an on/off switch** — see §9.2. This app's
`AppConfig.ready()` must apply `IGNORED_MODELS`/`SELECT_MODE` *before* calling
`cache.prepare()`, and must detect (and raise `ImproperlyConfigured` on) the case where upstream's
own cache was already populated by an earlier-loaded `django_cleanup.apps.CleanupConfig`, since
`prepare()` is non-reentrant and a second call is silently a no-op.

No `.env` keys — required or optional. This app configures entirely through `CLEANUP`.

**Requires another app package: No.**

---

## §6. The orphan-review admin page — Option A (unmanaged model), decision recorded

Chosen over a custom `admin_views.py` view (Option B) because it earns a real Jazzmin sidebar
entry with **zero** `JAZZMIN_SETTINGS` edits by the host — Jazzmin renders its sidebar from
registered `ModelAdmin`s, so anything reached only via a bolted-on URL (Option B) requires the host
to hand-add a `custom_links` entry, whereas a real (if unmanaged) model registration doesn't.

```python
# cleanup_app/admin.py (sketch — Phase 5 implements)
class OrphanFile(models.Model):
    """Represents one row of an OrphanScanner.scan() result. No table — changelist_view is
    fully overridden to call the scanner instead of querying the database."""
    file_path = models.CharField(max_length=1024, primary_key=True)
    file_size = models.PositiveBigIntegerField()

    class Meta:
        managed = False       # no migration, no table, ever
        app_label = "cleanup_app"


@admin.register(OrphanFile)
class OrphanFileAdmin(admin.ModelAdmin):
    def has_module_permission(self, request) -> bool:
        return request.user.is_staff   # a staff user with no assigned model perms would
                                        # otherwise not see this app in the sidebar at all
    def has_view_permission(self, request, obj=None) -> bool:
        return request.user.is_staff
    def has_add_permission(self, request) -> bool:
        return False                   # nothing to add — rows come from a live scan
    def has_delete_permission(self, request, obj=None) -> bool:
        return request.user.is_staff

    def changelist_view(self, request, extra_context=None):
        """Calls services.OrphanScanner.scan(), never Model.objects.all()."""
        ...
```

Delete goes through an admin action calling `CleanupService.run(file_paths=selected,
initiated_by=request.user)` — never a direct `storage.delete()` in admin code — behind a
confirmation step (grace period and exclude patterns still apply; dry-run is not offered in the
UI, since this is a human confirming real intent, not an automated path).

**Fallback, documented rather than silently substituted:** if Django admin's queryset-backed
changelist internals fight `changelist_view`'s full override in ways Phase 5 can't cleanly work
around, fall back to Option B (a view via `CleanupRunAdmin.get_urls()`, gated by an explicit
`is_staff` check in the view, `templates/admin/cleanup_app/orphans.html`) and document the
`JAZZMIN_SETTINGS["custom_links"]` entry a host then must add. Phase 5 states explicitly which
option it shipped.

**Shipped: Option A, with one amendment.** The registration itself is exactly the sketch above —
an unmanaged `OrphanFile`, `changelist_view` fully overridden to call `OrphanScanner.scan()`,
`has_module_permission`/`has_view_permission`/`has_delete_permission` on `is_staff`,
`has_add_permission` always `False` — and it earns the zero-`JAZZMIN_SETTINGS` sidebar entry this
option exists for. **Amendment:** `changelist_view` renders this app's own template
(`templates/admin/cleanup_app/orphanfile/change_list.html`, extending `admin/base_site.html`),
not django admin's stock `admin/change_list.html`. That template is driven entirely by a real
`ChangeList` object — `cl.result_list`, `cl.get_queryset()`, `cl.formset`, filter specs, all
queryset-backed — and `OrphanFile` has no table to back one with; fabricating a fake `ChangeList`
is exactly the "fighting the framework" case this section's own escape hatch names, for no
visible benefit. `get_urls()` is also narrowed to expose only the changelist route — Django's
default add/change/delete/history routes assume a real table and would hit a database error
before their own permission check ever ran. The delete flow is a same-page POST/confirm/POST
cycle (`action=delete` renders a confirmation step; `action=delete&confirm=yes` is the only path
that calls `CleanupService.run(trigger=CleanupRun.Trigger.MANUAL, ...)`), re-validating every
selected path against the live `OrphanScanner.scan()` snapshot before the call, mirroring
`serializers.OrphanDeleteRequestSerializer`'s same rule for the API.

**Requires another app package: No** (Django admin + Jazzmin, both host-provided infrastructure
this package integrates with, not app packages it imports).

---

## §7. Frontend hooks

| Hook | Wraps | Query key | Invalidation |
|---|---|---|---|
| `useOrphanFiles(params)` | `GET /orphans/` | `cleanupKeys.orphans(params)` | — (query) |
| `useDeleteOrphanFiles()` | `POST /orphans/delete/` | — (mutation) | `cleanupKeys.orphans()`, and once the returned run reports finished, `cleanupKeys.runs()` + `cleanupKeys.summary()` |
| `useTriggerCleanup()` | `POST /runs/` | — (mutation) | `cleanupKeys.runs()`, `cleanupKeys.summary()`, and `cleanupKeys.orphans()` (a completed run changes what's orphaned) |
| `useCleanupRuns(params)` | `GET /runs/` | `cleanupKeys.runs(params)` | — (query) |
| `useCleanupRun(id)` | `GET /runs/{id}/` | `cleanupKeys.run(id)` | — (query) |
| `useCleanupSummary()` | `GET /summary/` | `cleanupKeys.summary()` | — (query) |

`cleanupKeys` factory (exported from `index.ts` per `APP-DESIGN.md` §12's "Manager & hook
conventions" — a host sometimes needs to invalidate this app's cache from its own composed code):

```ts
export const cleanupKeys = {
  all: ["cleanup"] as const,
  orphans: (params?: OrphanListParams) => [...cleanupKeys.all, "orphans", params] as const,
  runs: (params?: RunListParams) => [...cleanupKeys.all, "runs", params] as const,
  run: (id: number) => [...cleanupKeys.all, "runs", id] as const,
  summary: () => [...cleanupKeys.all, "summary"] as const,
};
```

Both mutation hooks are the "destructive action never fires on mount" case
`APP-DESIGN.md` §12's frontend security checklist calls out by name — they fire only from an
explicit `mutate()` call, per Phase 6's test requirement.

**Requires another app package: No.**

---

## §8. `tasks.py` (celery extra only)

```python
# cleanup_app.tasks
@shared_task(name="cleanup_app.tasks.run_scheduled_cleanup")
def run_scheduled_cleanup() -> int | None:
    """Calls CleanupService.run(trigger=CleanupRun.Trigger.SCHEDULED). Returns the created run's
    id, or None if skipped due to the concurrency guard below.

    Concurrency guard: skip (log, return None) if a CleanupRun with
    status in (PENDING, RUNNING) and trigger=SCHEDULED already exists. Narrower than gating on
    status alone (any status) so a stuck AUTO or API run never blocks the schedule — and per §9.4,
    an AUTO run can never carry PENDING/RUNNING status, so it can never trip this guard regardless.
    """
    ...
```

Recommended schedule: daily, via `django_celery_beat` on the host side (this app never
self-registers a schedule). Behind the `celery` extra only — a host without Celery uses the
equivalent `cleanup_orphans` management command via plain cron instead, same underlying
`CleanupService.run()` call, same concurrency guard logic re-implemented against the same query.

**Requires another app package: No.**

---

## Dependencies

```toml
dependencies = [
    "django>=5.2,<7.0",
    "djangorestframework>=3.15,<4.0",
    "drf-spectacular>=0.27,<1.0",
    "hjtdev-appkit>=2.0,<3.0",
    "django-cleanup>=9.0,<10.0",
]

[project.optional-dependencies]
celery = ["celery[redis]>=5.4,<6.0", "django-celery-beat>=2.7,<3.0"]
```

`django`, `djangorestframework`, and `drf-spectacular` are the shared-platform ranges every app in
the ecosystem declares identically (`APP-DESIGN.md` §1.1) — a host almost certainly depends on all
three directly already. `hjtdev-appkit` and `django-cleanup` are both declared-dependency
exceptions to the no-inter-app-import rule (§1.1's mechanical test: *is it in
`[project.dependencies]`?* — yes for both), not sibling app packages. No exact pins anywhere.

---

## §9. Deviations register

Everything not listed here is unchanged from
`docs/CLAUDE-CODE-GUIDE-APP-MEDIA-CLEANUP.md`'s Phase 0 prompt.

1. **`IGNORED_MODELS` reinterpreted as protective, not subtractive** (§5, §1). The prompt's item 5
   says it "excludes a model from the *reference set* used by the scanner." Read literally, that
   makes every file a live, ignored-model row points at into a false-positive orphan — worse, under
   `SELECT_MODE=True` the same wording would orphan every non-selected model's files by default.
   The reference set is purely protective; removing entries from it can only ever make files *more*
   deletable, never less, which is backwards for a setting whose stated purpose is exemption.
   Confirmed with the project owner before writing this contract. Fixed reading: `IGNORED_MODELS`
   only marks a model via upstream's `cleanup.ignore()` so it's exempt from *auto-hook* deletion;
   the scanner's reference set always includes it. This directly answers the build guide's own
   Phase-0 review question ("is `IGNORED_MODELS` applied consistently to both... or could a file
   be 'orphaned' by one path and 'protected' by the other?") — under this reading, no: a live
   ignored-model row's file is protected by both paths, and a dangling one is an orphan in both.

2. **`AUTO_CONNECT` has an install-order hazard the guide's §1 table calls harmless.** Verified
   against `django_cleanup/cache.py:26-29`: `prepare()` returns immediately if `FIELDS` is already
   populated. If a host lists `django_cleanup` (with its own default `CleanupConfig`) *before*
   `cleanup_app` in `INSTALLED_APPS`, upstream's own `ready()` populates `FIELDS` first, and this
   app's later `cache.prepare(SELECT_MODE)` call is then a silent no-op — `IGNORED_MODELS` and
   `SELECT_MODE` never take effect, with no error. §5 now requires `AppConfig.ready()` to raise
   `ImproperlyConfigured` if it detects the cache was already populated while either setting is
   non-default, rather than the guide's assumption that "nothing breaks if a host does anyway."

3. **The six throttle scope names are literals, not `throttle_scope()` calls.** Verified against
   `appkit/throttling.py:20-33`: the helper raises `ValueError` if either argument contains an
   underscore. Every name the guide specifies (`cleanup_orphans_list`, etc.) has one on the action
   side (`orphans_list`), so `throttle_scope("cleanup", "orphans_list")` cannot produce them. §4
   fixes the names as plain string literals instead — `appkit.checks`'s W004 system check still
   validates them against `DEFAULT_THROTTLE_RATES` independent of how the string was written.

4. **A fourth `Trigger` value, `AUTO`, plus its status/grouping rules, made explicit now instead of
   surfacing as a surprise in Phase 3.** The guide's item 1 lists only
   manual/scheduled/api, but its own Phase 3 section requires an `AUTO`-triggered run for the
   `TRACK_AUTO_DELETIONS` receiver. Decided here rather than left to Phase 3 improvisation:
   - **Grouping: one `CleanupRun(trigger=AUTO)` per UTC calendar day**, `get_or_create` on first
     event of the day, one `CleanupRunFile` per upstream deletion event. Chosen over a
     thread-local-per-request run because it needs no middleware and behaves identically whether
     the deletion happens in a request, a Celery task, a management command, or a shell.
   - **Status: never `PENDING`/`RUNNING`.** An `AUTO` run's status is `SUCCESS` until any event
     reports `success=False`, at which point it becomes `PARTIAL`; `finished_at` is bumped on every
     event. This is load-bearing, not cosmetic: a day-spanning `RUNNING` row would permanently trip
     §8's `SCHEDULED`-only concurrency guard if the guard's status check weren't also
     trigger-scoped — it is (§8), but the two facts must hold together, so both are stated here.
   - **Payload types:** verified against `django_cleanup/handlers.py:91-118` — the
     `cleanup_post_delete` signal's `error` kwarg is an `Exception` instance or `None`, not a
     string; the receiver stores `str(error)` when present.
   - **Scope of the four rails, restated precisely:** `CleanupService` (§3) is the only thing the
     dry-run/grace-period/exclude-pattern/record-before-delete rails govern. Upstream's own
     per-save/per-delete deletion (verified: it deletes inside `on_commit`, *then* sends
     `cleanup_post_delete` — `handlers.py:105-120`) already happened by the time this app's
     receiver runs; the receiver is a **log**, not a gate, and cannot retroactively apply a rail to
     a delete that's already committed. A host that wants those files rail-governed instead adds
     the model to `IGNORED_MODELS` (§5) and lets the scanner find and clean them on its own
     schedule, under its own rails.

5. **Concurrency guard resolved to the narrower reading.** The guide's own text contradicts
   itself — item 7 says skip if a run with `status="running"` **and** `trigger="scheduled"`
   exists; Phase 3's prose drops the trigger qualifier and says `status="running"` alone. §8 freezes
   the narrower, trigger-scoped version (`status in (PENDING, RUNNING) and trigger=SCHEDULED`),
   which is also the only version consistent with item 4 above — an unscoped guard would let a
   long-lived `AUTO` row block every future scheduled run, and per item 4, an `AUTO` row is never
   long-lived in `RUNNING` status anyway, so the two facts reinforce rather than merely coexist.

6. **`OrphanScanResult` gains `files_scanned: int` and `truncated: bool`** beyond the guide's
   stated `files, total_size`. Without them, `MAX_FILES_PER_RUN` truncation is invisible to both
   the API response (`GET /orphans/`) and the admin page — a host would have no way to know the
   orphan list it's looking at is incomplete.

7. **`OrphanScanResult.files` is `list[OrphanFileInfo]` (a new frozen dataclass: `path`, `size`,
   `modified_at`), not the guide's/§3's originally literal `list[str]`.** Decided in Phase 3:
   `scan()` must already call `storage.get_modified_time()` on every candidate to apply the
   grace-period rail, and `storage.size()` to compute `total_size` — a bare path throws that data
   away and forces `GET /orphans/` (§4's `{file_path, file_size, modified_at}` response shape)
   and `CleanupService.run()`'s byte accounting to re-stat every file again, once per page and
   once per delete, for data the scan already had in hand. Named `OrphanFileInfo`, not
   `OrphanFile`, specifically to avoid colliding with §6's unmanaged admin model of that name.
   This is a `list[str]` → `list[OrphanFileInfo]` element-type change on a frozen dataclass field
   — a **MAJOR** bump per §10, same as any other `OrphanScanResult`/`OrphanScanner.scan()`
   signature change, legitimate to make now at 0.1.0 before the contract's first tagged release.

---

## §10. Semver triggers (concrete, against the names frozen above)

Per `CLAUDE.md`'s list, made specific to this contract — each of these is a **MAJOR** bump with a
`Host action:` line in `CHANGELOG.md`:

- Removing/renaming `cleanup_run_started`, `cleanup_run_finished`, any kwarg on either.
- Changing `OrphanScanner.scan`/`build_reference_set`, `CleanupService.run`/`purge_history`'s
  signature, return type, or `OrphanScanResult`'s fields.
- Renaming `CleanupRun.Trigger.AUTO` (or any other trigger/status value) or a `CleanupRun`/
  `CleanupRunFile` field a host might query directly.
- Making `build_reference_set()` exclude `IGNORED_MODELS` after all (reversing §9.1's decision) —
  a stricter or looser orphan definition without a settings key to opt back into the old behavior.
- Renaming any `CLEANUP` key, or renaming `hjtdev-django-cleanup`/`@hjtdev/django-cleanup`.
- Shortening the default `GRACE_PERIOD_SECONDS`, changing the default delete mode (hard delete vs.
  quarantine), or changing the default `AUTO_CONNECT`/`TRACK_AUTO_DELETIONS` value — a host that
  never overrode it inherits new behavior silently.
- Changing which of Option A/B backs the orphan-review page in a way that changes the host-side
  Jazzmin wiring requirement (e.g. switching from A to B would newly require a `custom_links` edit
  every existing host would have to add).

---

## §11. Open items for later phases

- **Resolved in Phase 5: Option A shipped**, with one amendment to §6's own text (below) — the
  unmanaged-model registration and its free Jazzmin sidebar entry are exactly as §6 describes;
  only the rendering target changed.
- **Phase 1's `AppConfig.ready()` ordering check (§9.2)** needs a concrete way to detect "was
  `FIELDS` already populated by someone else" — likely inspecting
  `django_cleanup.cache.FIELDS` truthiness before this app's own `prepare()` call, but the exact
  mechanism is Phase 1's to implement and test.
- **Resolved in Phase 3: the `AUTO`-trigger receiver lives in a dedicated `cleanup_app/receivers.py`**,
  not `services.py` — keeps `services.py` as purely the rail-governed delete surface, and a
  separate file makes "this is a log, not a gate" (§9.4) impossible to misread as one of the four
  delete rails. Connected from `CleanupAppConfig.ready()` independently of `AUTO_CONNECT`, gated
  only on `TRACK_AUTO_DELETIONS`.
- **Phase 9's security-checklist walk** should explicitly re-verify §9.2's `ImproperlyConfigured`
  guard actually fires in a deliberately-misordered `INSTALLED_APPS` test, not just at review time.
