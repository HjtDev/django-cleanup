# CLAUDE-CODE-GUIDE-APP-MEDIA-CLEANUP.md — Building `hjtdev-django-cleanup`

Project-specific instance of `docs/CLAUDE-CODE-GUIDE-APP.md`, pre-customized so each phase is a
paste-and-go session instead of a re-derive-the-prompt-in-Opus session. **This file is what you
follow phase by phase.** The generic guide stays as reference for *why* each phase is shaped this
way; this one has already made every project-specific call the generic guide's §1.3 table asks
for (see §1 below), so no session needs to re-decide them.

> Companions: `docs/APP-DESIGN.md` (the architecture every app package follows),
> `docs/CLAUDE-CODE-GUIDE-APP.md` (the generic process this document instantiates),
> `docs/INTEGRATION-GUIDE.md` (the host side), `docs/BASE-DESIGN.md` (what a host provides).

---

## 0. What this app is, and the two constraints unique to it

A reusable Django + React app package that finds and removes **orphaned media files** — files
sitting in storage with no model row pointing at them anymore — and keeps a full history of every
cleanup it performs. It auto-hooks every model with a `FileField`/`ImageField` in the host
project, the same way upstream `django-cleanup` does, but adds the half upstream deliberately
doesn't have: **scanning storage for files nothing references at all**, a Jazzmin review page,
admin-only DRF endpoints, and frontend hooks.

Same operating principle as every app package (`CLAUDE-CODE-GUIDE-APP.md` §0): a contract before
code, machine-enforced boundaries from Phase 1. Two things are unique to *this* app and apply to
every phase below without exception:

1. **`django-cleanup` (upstream PyPI package, importable as `django_cleanup`) is a declared
   dependency, exactly like `appkit`.** It is not a sibling app package and is not a §6 boundary
   violation — `docs/APP-DESIGN.md` §1.1's test is mechanical: *is it in
   `[project.dependencies]`?* Yes → it's a normal dependency, imported freely
   (`from django_cleanup import cleanup`, `from django_cleanup.signals import
   cleanup_post_delete`). The only thing that must never happen is *this app's own importable
   module* being named `django_cleanup` — it collides with upstream in the same `site-packages`.
   This app's module is **`cleanup_app`** (§1).
2. **This app deletes files off disk.** Every phase that touches a delete path carries the safety
   rails (dry-run, grace period, exclude patterns, record-before-delete) as a hard requirement,
   not something added "later." A phase that ships a delete path without all four is not done,
   regardless of what else it accomplishes.

---

## 1. Decisions already made (the generic guide's §1.3 table, answered)

Read this once; every phase prompt below assumes it.

| Question | Decision |
|---|---|
| Importable module name | **`cleanup_app`** — upstream `django-cleanup` 9.0.0 owns `django_cleanup` (verified: `src/django_cleanup/`, `django_cleanup.apps.CleanupConfig`); we depend on it, so our module can't share that name |
| PyPI distribution | **`hjtdev-django-cleanup`** (verified free) |
| npm package | **`@hjtdev/django-cleanup`** (scoped, unaffected by the module-name collision) |
| GitHub repo | `HjtDev/django-cleanup` (unchanged — only the local directory and importable module are `cleanup_app`) |
| Namespacing (`APP-DESIGN.md` §1.2) | settings dict `CLEANUP`; throttle prefix `cleanup_`; cache namespace `cleanup`; frontend basePath key `cleanup` → default `/api/v1/cleanup`; Celery task names `cleanup_app.tasks.*` |
| Frontend half? | Yes |
| User-model need | `settings.AUTH_USER_MODEL` only, nullable `initiated_by` FK on `CleanupRun`. Nothing else. No `contenttypes` reference — not needed |
| Admin gating | `appkit.permissions.IsAppAdmin` (`is_authenticated and is_staff`) on **every** endpoint and admin surface — this app has no user-facing surface at all, `urls.py` ships empty |
| Delete mode | `storage.delete()` by default; `CLEANUP["QUARANTINE_DIR"]` set → move there instead. Both paths always honour grace period, exclude patterns, and dry-run |
| Execution | Synchronous by default. `celery` is an **optional extra** (`hjtdev-django-cleanup[celery]`); `CLEANUP["USE_CELERY"]=True` → the trigger endpoint enqueues and returns 202 with a pending `CleanupRun` |
| History | `CleanupRun` (per-run aggregates) + `CleanupRunFile` (per-file rows) + an opt-in `TRACK_AUTO_DELETIONS` receiver on upstream's `cleanup_post_delete`, logging the files upstream itself removes on save/delete into the same run tables |
| `.env` keys | None — required or optional. This app configures entirely through `CLEANUP` |
| `appkit` helpers used | `permissions.IsAppAdmin`, `pagination.DefaultPagination`, `mixins.CachedListMixin`, `cache.build_cache_key`/`cached_call`/`invalidate_namespace`, `throttling.throttle_scope`, `media.file_url`, `validation.validate_query_params`, `testing` (pytest plugin, `-p appkit.testing`). Frontend: `useApiClient`, `ApiError`/`isApiError`. No gap — no `appkit` release needed first |
| Coverage gate | 85% (the standard app-package bar — `appkit`'s 95% is its own blast-radius exception, not the default) |

**Upstream facts this guide already verified, so no phase re-derives them:**
`django_cleanup.handlers.connect()` guards every signal connection with a `dispatch_uid`, and
`django_cleanup.cache.prepare()` is a no-op if its internal `FIELDS` cache is already populated.
That means **this app's own `AppConfig.ready()` can call `django_cleanup.cache.prepare(select_mode)`
and `django_cleanup.handlers.connect()` directly**, so a host only ever adds `cleanup_app` to
`INSTALLED_APPS` (placed last) — it never has to also list
`django_cleanup.apps.CleanupConfig` itself, and nothing breaks if a host does anyway.

Upstream's `cleanup_post_delete` signal sends: `sender, file, file_name, model_name, field_name,
instance, default_file_name, deleted, updated, success, error`. That payload is exactly what
`TRACK_AUTO_DELETIONS`'s receiver logs.

---

## 2. The build, phase by phase

Fresh session per phase, same hygiene as always: `/clear` between phases, one phase's scope only,
review every diff, verification command's real output pasted before moving on.

### Phase 0 — The contract (no code)

```
Phase 0: design the public contract. Write it to docs/CONTRACT.md. No implementation code.

Read docs/APP-DESIGN.md fully first — especially §1 (package contract), §6 (inter-app
communication), and §8 (README contract). Also read docs/CLAUDE-CODE-GUIDE-APP-MEDIA-CLEANUP.md
§0 and §1 in full — this app's name, module, dependency rules, and every settings/endpoint/hook
decision are already made there; do not re-derive or change them, only formalize them into
CONTRACT.md's required shape.

This is hjtdev-django-cleanup (module: cleanup_app) — a Django + React app that auto-hooks every
model with a FileField/ImageField (via upstream django-cleanup, a declared dependency, imported
as django_cleanup), scans configured storage for orphaned files (on disk, referenced by nothing),
gives a Jazzmin admin page to review and delete them, and keeps a full history of every cleanup
run — automatic (per-save/per-delete, via upstream's signals) and manual (a full orphan scan).

Produce, using the specifics below as the starting point — refine names/shapes only where the
reasoning is genuinely better, and flag any change explicitly rather than silently drifting:

1. Models:
   - CleanupRun — status (pending/running/success/failed/partial), trigger
     (manual/scheduled/api), initiated_by (nullable FK to settings.AUTH_USER_MODEL,
     on_delete=SET_NULL), dry_run (bool), started_at (auto_now_add), finished_at (nullable),
     files_scanned, files_deleted, files_failed (PositiveIntegerField), bytes_freed
     (PositiveBigIntegerField), error (TextField, blank). Index on (status, -started_at) and on
     trigger.
   - CleanupRunFile — run (FK to CleanupRun, related_name="files", CASCADE), file_path
     (CharField), file_size (PositiveBigIntegerField), deleted (bool), quarantined (bool), error
     (TextField, blank). Index on (run, deleted).
   - A model backing the Jazzmin orphan-review page — evaluate an unmanaged (Meta.managed=False,
     no real table) model registered in admin.py with a fully overridden changelist_view, vs. a
     custom admin_views.py view reached through CleanupRunAdmin.get_urls() plus a documented
     Jazzmin custom_links entry for the host. Pick one, document why, and note it explicitly as a
     decision Phase 5 will implement — this is the one open design question in this list.
   Every FK-shaped reference in these models must be settings.AUTH_USER_MODEL or nothing —
   flag anything else immediately, it would be a boundary violation.

2. Signals — cleanup_run_started (sends: run_id, trigger, dry_run) and cleanup_run_finished
   (sends: run_id, status, files_deleted, bytes_freed). Argue for the minimum viable payload on
   both, per the versioned-contract rule.

3. services.py — OrphanScanner.scan(*, dry_run: bool = False) -> OrphanScanResult (a dataclass:
   files, total_size), OrphanScanner.build_reference_set() -> set[str], CleanupService.run(*,
   trigger: str = "manual", dry_run: bool = False, file_paths: list[str] | None = None,
   initiated_by=None) -> CleanupRun, CleanupService.purge_history(*, older_than_days: int | None
   = None) -> int. Full signatures, fully typed.

4. Endpoints — all under urls_admin.py, all gated by IsAppAdmin, all admin-throttle-scoped:
   GET /orphans/ (paginated, from a cached scan snapshot — never rescans per page), POST
   /orphans/delete/ (body: list of file paths to delete from the current snapshot), GET /runs/
   (paginated history) and POST /runs/ (trigger a new run — sync or, if CLEANUP["USE_CELERY"],
   enqueued+202), GET /runs/{id}/ (single run detail with its files), GET /summary/ (aggregate
   counts). urls.py (user-facing) ships intentionally empty — this app has no user-facing surface.
   For each: method, path, permission, throttle scope name (cleanup_ prefixed), request/response
   shape.

5. Settings dict CLEANUP with defaults (→ conf.py DEFAULTS): STORAGE_ALIAS ("default"),
   SCAN_ROOTS (None = whole storage), EXCLUDE_PATTERNS ([]), GRACE_PERIOD_SECONDS (3600),
   QUARANTINE_DIR (None = hard delete), MAX_FILES_PER_RUN (5000), SCAN_CACHE_TIMEOUT (300),
   USE_CELERY (False), TRACK_AUTO_DELETIONS (True), HISTORY_RETENTION_DAYS (90), AUTO_CONNECT
   (True), SELECT_MODE (False), IGNORED_MODELS ([]). No .env keys — this app has none. Explain
   what each key does and any interaction between them (e.g. AUTO_CONNECT/SELECT_MODE map onto
   upstream's CleanupConfig vs CleanupSelectedConfig; IGNORED_MODELS excludes a model from the
   *reference set* used by the scanner AND from upstream's per-save/per-delete auto-cleanup —
   state explicitly that it must apply to both or files belonging to an ignored model would look
   orphaned).

6. Frontend hooks — useOrphanFiles(params), useDeleteOrphanFiles(), useTriggerCleanup(),
   useCleanupRuns(params), useCleanupRun(id), useCleanupSummary(). Name + what each wraps + query
   key + invalidation behavior (a mutation must invalidate both the orphans list and, once a run
   finishes, the runs list/summary).

7. tasks.py — cleanup_app.tasks.run_scheduled_cleanup, calling CleanupService.run(trigger=
   "scheduled"). Behind the celery extra only; idempotent (safe if the previous scheduled run is
   still finishing — decide and document the concurrency guard, e.g. skip if a CleanupRun with
   status="running" and trigger="scheduled" already exists). Recommended schedule: daily.

8. Dependencies: "hjtdev-appkit>=2.0,<3.0" and "django-cleanup>=9.0,<10.0" in
   [project.dependencies] (both are declared-dependency exceptions to §6, not app-to-app
   imports); "celery[redis]>=5.4,<6.0" as an optional extra named "celery". Call out anything a
   host is also likely to depend on directly.

For each of 1–7: state explicitly whether it requires knowledge of another app package. It never
should — if something seems to, propose the decoupled alternative rather than accepting it.
```

**Review this yourself before Phase 1.** Specifically, beyond the generic guide's four checks:
does the orphan-review-page decision (item 1's open question) actually work with Jazzmin's
sidebar without the host editing `JAZZMIN_SETTINGS`? Is `IGNORED_MODELS` applied consistently to
both the scanner's reference set and upstream's auto-hook, or could a file "orphaned" by one path
and "protected" by the other?

### Phase 1 — Package skeleton, `pyproject.toml`, boundary enforcement

```
Phase 1: the package skeleton. docs/APP-DESIGN.md §2 and §3, this app's docs/CONTRACT.md.

Create the repo structure from APP-DESIGN.md §2 exactly (module directory is cleanup_app), then:
1. backend/pyproject.toml complete per §3.1 — dependencies from CONTRACT.md item 8 with WIDE
   RANGES: "django>=5.2,<7.0", "djangorestframework>=3.15,<4.0", "drf-spectacular>=0.27,<1.0",
   "django-cleanup>=9.0,<10.0", "hjtdev-appkit>=2.0,<3.0". [project.optional-dependencies]
   celery = ["celery[redis]>=5.4,<6.0", "django-celery-beat>=2.7,<3.0"]. [dependency-groups] dev
   + test per §3.1's template, PLUS "hjtdev-appkit" is already a dependency so its testing extra
   needs nothing extra. [tool.uv] default-groups = ["dev", "test"]. Coverage threshold 85 in
   addopts. Wire "-p appkit.testing" into [tool.pytest.ini_options] addopts, per
   CLAUDE-CODE-GUIDE-APP.md's note on appkit's opt-in pytest plugin.
2. The flake8-tidy-imports banned-api block: list every OTHER app package in the ecosystem (ask
   if unsure which exist yet), plus "cleanup_app.factories" test-only guard. Do NOT add lines for
   "appkit" or "django_cleanup" — both are declared dependencies per §0's rule above, not banned
   siblings.
3. backend/MANIFEST.in so locale/, templates/, and static/ ship in the wheel — this matters more
   than usual here, since Phase 5's Jazzmin page lives in templates/.
4. .python-version (3.14), .gitignore, .pre-commit-config.yaml per §3.6.
5. src/cleanup_app/__init__.py, apps.py — AppConfig with a translatable verbose_name, and a
   ready() that imports django_cleanup.cache and django_cleanup.handlers and calls
   cache.prepare(conf.get_setting("SELECT_MODE")) and handlers.connect() when
   conf.get_setting("AUTO_CONNECT") is true (default True) — document in a docstring why this is
   safe to call unconditionally (dispatch_uid-guarded, non-reentrant cache — see
   docs/CLAUDE-CODE-GUIDE-APP-MEDIA-CLEANUP.md §1). conf.py per §3.5 with the DEFAULTS from
   CONTRACT.md item 5.
6. Empty-but-present, each with a docstring stating its role per CONTRACT.md: models.py,
   views.py (docstring notes urls.py/views.py are intentionally unused — no user-facing surface),
   serializers.py, permissions.py, signals.py, services.py, urls.py, urls_admin.py, admin.py,
   admin_views.py, tasks.py, factories.py. utils.py only if a genuine private helper turns up
   with nowhere else to go.

Run `uv sync`, then `uv sync --extra celery` to prove the extra resolves, then `uv build`. Paste
all three outputs.
```

**Verify:** `uv sync`, `uv sync --extra celery`, and `uv build` all succeed; `dependencies` are
ranges, not `==`, including on `appkit` and `django-cleanup`.

**Review for:** exact pins anywhere; `include-package-data` present; `banned-api` populated and
**not** listing `appkit` or `django_cleanup`; `ready()` doesn't crash on a host with zero
`FileField` models (upstream's `cache.prepare` handles the empty case, but confirm rather than
assume).

### Phase 2 — Models, migrations, admin (history only — the orphan-review page is Phase 5)

```
Phase 2: data layer. docs/APP-DESIGN.md §2, this app's docs/CONTRACT.md item 1 (CleanupRun and
CleanupRunFile only — leave the orphan-review model/page for Phase 5, even if CONTRACT.md decided
its shape here).

Implement models.py:
- CleanupRun and CleanupRunFile exactly as CONTRACT.md specifies.
- settings.AUTH_USER_MODEL for initiated_by — never a concrete User import.
- Meta.indexes for every field used in filters/ordering (status+-started_at, trigger on
  CleanupRun; run+deleted on CleanupRunFile).
- No FK to any other app package's model, ever.

Then makemigrations, and verify 0001_initial uses
migrations.swappable_dependency(settings.AUTH_USER_MODEL) — add it if missing.

Then admin.py: ModelAdmin for CleanupRun (list_display incl. status, trigger, files_deleted,
bytes_freed, started_at; list_filter on status/trigger; readonly_fields on every computed field;
an inline or a link to its CleanupRunFile rows) and CleanupRunFile (readonly, list_filter on
deleted). select_related/prefetch_related on get_queryset. Do NOT touch JAZZMIN_SETTINGS — note
the suggested icon (fa fa-broom or similar) for the README instead.

Create tests/backend/settings.py per APP-DESIGN.md §7.1 (minimal INSTALLED_APPS — include
django_cleanup itself since this app's own models don't have FileFields, but the test app models
used elsewhere might, Postgres, cleanup_app in INSTALLED_APPS), then run `uv run pytest
--create-db` to prove migrations apply from zero. Paste the output.
```

**Verify:** migrations apply against real Postgres from zero; `swappable_dependency` present.

**Review for:** any concrete `User` import; missing indexes; a `ForeignKey` outside the package;
the orphan-review model accidentally implemented here instead of Phase 5.

### Phase 3 — Services, signals, tasks, safety rails

The phase where a mistake means silently deleting the wrong file. Read twice before writing.

```
Phase 3: business logic. docs/APP-DESIGN.md §6, this app's docs/CONTRACT.md items 2, 3, 7, and
docs/CLAUDE-CODE-GUIDE-APP-MEDIA-CLEANUP.md §0 item 2 (the safety-rails constraint).

Implement:

- services.py:
  - OrphanScanner.build_reference_set() -> set[str]: iterate apps.get_models(), find every
    models.FileField (ImageField included) via _meta.get_fields(), and for each collect
    referenced file names with .values_list(field_name, flat=True).iterator() — never load full
    rows. Exclude any model whose (app_label, model_name) appears in
    conf.get_setting("IGNORED_MODELS") — same exclusion upstream's auto-hook is configured to
    skip in Phase 1's apps.py, so a file's orphan status can never disagree between the two
    paths.
  - OrphanScanner.scan(*, dry_run=False) -> OrphanScanResult: walk the storage backend named by
    CLEANUP["STORAGE_ALIAS"] (default_storage if "default"), scoped to SCAN_ROOTS if set, listing
    files via storage.listdir() recursively. A file is a candidate orphan if: not in the
    reference set, not matching any glob in EXCLUDE_PATTERNS (fnmatch), and its
    storage.get_modified_time() is older than GRACE_PERIOD_SECONDS from now (protects
    in-progress uploads and files referenced by an uncommitted transaction). Cap results at
    MAX_FILES_PER_RUN, documenting the truncation in the result. Cache the resulting snapshot
    under appkit.cache.build_cache_key("cleanup", "orphans") via appkit.cache.cached_call, timeout
    CLEANUP["SCAN_CACHE_TIMEOUT"] — this is what makes the paginated admin/API list in Phase 4
    never re-walk storage per page.
  - CleanupService.run(*, trigger="manual", dry_run=False, file_paths=None, initiated_by=None) ->
    CleanupRun: create a CleanupRun(status="running"...), send cleanup_run_started. If
    file_paths is given, operate only on that subset of the current cached snapshot (the
    POST /orphans/delete/ case); otherwise run a fresh OrphanScanner.scan(). For every file: FIRST
    create its CleanupRunFile row (deleted=False), THEN attempt the delete/quarantine — record
    success/failure on that same row afterward. Never delete before the row recording it exists.
    dry_run=True writes every row with deleted=False and touches no storage at all. On completion
    set status ("success" if no failures, "partial" if some, "failed" if all failed or an
    unhandled exception occurred), finished_at, aggregate counts, send cleanup_run_finished.
    A single file's deletion failure must never abort the run for the remaining files.
  - CleanupService.purge_history(*, older_than_days=None) -> int: delete CleanupRun rows (and
    cascade CleanupRunFile) older than the given days, or CLEANUP["HISTORY_RETENTION_DAYS"] if
    None. Returns count deleted. This never touches media storage, only history rows.

- signals.py — cleanup_run_started and cleanup_run_finished as django.dispatch.Signal(), with the
  exact documented payload as a comment above each, matching CONTRACT.md character for character.

- A receiver (in services.py or a dedicated receivers.py, your call, document which) connected to
  django_cleanup.signals.cleanup_post_delete, active only when CLEANUP["TRACK_AUTO_DELETIONS"] is
  true: on every upstream deletion, write a CleanupRun(trigger="api" is wrong — use a new trigger
  value "auto") + a single CleanupRunFile row from that signal's payload (file_name, model_name,
  field_name, success, error). Batch these sanely — do not create a new CleanupRun per individual
  auto-deleted file if Django batch-deletes several at once in one request; decide and document
  the grouping strategy (e.g. one CleanupRun per request via a thread-local, or one row per event
  with a shared "auto" CleanupRun per calendar day — pick the simpler one and justify it).

- tasks.py — cleanup_app.tasks.run_scheduled_cleanup, behind the celery extra, calling
  CleanupService.run(trigger="scheduled"). Guard against overlapping runs: skip and log if a
  CleanupRun with status="running" already exists, per CONTRACT.md item 7.

- A management command, cleanup_app/management/commands/cleanup_orphans.py, wrapping
  CleanupService.run with --dry-run and --trigger flags — this is what a host without Celery
  schedules via plain cron, and what Phase 9's playground/CI can exercise without a worker.

Hard constraints, restated because this is the phase they matter most:
- No import of any other app package. django_cleanup and appkit ARE allowed (declared deps).
- No import from a host (core, tools, config).
- Every service method emitting a signal emits EXACTLY the documented payload.
- Anything configurable comes from conf.get_setting(), never a hardcoded literal.
- Every delete-capable code path goes through CleanupService — no second, ad hoc storage.delete()
  call anywhere in the package.

Then write tests: happy path + at least one failure path per service method; one test per signal
asserting the exact payload by connecting a receiver; a test proving a file modified within the
grace period is never returned as an orphan; a test proving dry_run=True deletes nothing but
still writes CleanupRunFile rows; a test proving a file referenced by ANY model (including one
only reachable via a reverse relation) is never treated as orphaned; a test for the
TRACK_AUTO_DELETIONS receiver firing off upstream's own signal. Run pytest.
```

**Verify:** `uv run pytest` green; `uv run ruff check .` clean.

**Review for:** signal payloads matching `CONTRACT.md` exactly; any hardcoded value that should
be a setting; **every delete path passing through the four rails** (grace period, exclude
patterns, dry-run, record-before-delete) — this is the single most important review in the whole
build; `IGNORED_MODELS` applied identically in the scanner and in Phase 1's `AUTO_CONNECT` hook.

### Phase 4 — API layer

```
Phase 4: the API. docs/APP-DESIGN.md §4 and §5, this app's docs/CONTRACT.md item 4.

Implement serializers.py, permissions.py, admin_views.py, urls_admin.py. urls.py stays empty
(user-facing surface — this app has none) but present.

permissions.py exposes IsAppAdmin — but prefer importing appkit.permissions.IsAppAdmin directly
rather than reimplementing it (it's a declared dependency exactly for this). Only add a class here
if this app genuinely needs object-level logic appkit's version doesn't cover; if it doesn't,
permissions.py re-exports appkit's class and says so in a docstring — do not duplicate its body.

Every view in admin_views.py, without exception:
- permission_classes = [IsAppAdmin] — no view in this package is ever reachable by a non-staff
  user, there is no "user-facing" tier to fall back to.
- a namespaced throttle_scope: cleanup_orphans_list, cleanup_orphans_delete, cleanup_runs_list,
  cleanup_runs_trigger, cleanup_runs_retrieve, cleanup_summary.
- a complete @extend_schema: summary, description, request/response serializers,
  tags=["cleanup-admin"] (every view here is admin-only, so there's no "cleanup" tag).
- GET /orphans/: paginated (appkit.pagination.DefaultPagination) from the cached scan snapshot
  (services.OrphanScanner — trigger a scan if no live snapshot, otherwise read the cache; never
  scan storage per page). appkit.mixins.CachedListMixin on this endpoint's own response caching,
  cache_namespace="cleanup".
- POST /orphans/delete/: body = list of file paths (validated against the current snapshot —
  reject a path not present in it, never accept an arbitrary path from the client), calls
  CleanupService.run(file_paths=...). Invalidates the cleanup cache namespace via
  appkit.cache.invalidate_namespace("cleanup") on completion.
- GET /runs/ (paginated, DefaultPagination) and POST /runs/ (trigger CleanupService.run(); if
  CLEANUP["USE_CELERY"] and the celery extra is installed, enqueue tasks.run_scheduled_cleanup-
  equivalent and return 202 with a pending CleanupRun instead of running inline — check for
  celery's presence, don't hard-import it if the extra isn't installed).
- GET /runs/{id}/: single run + its CleanupRunFile rows, select_related/prefetch_related so it's
  not N+1.
- GET /summary/: aggregate counts (total runs, files deleted all-time, bytes freed all-time,
  last run timestamp/status) — cached, short timeout.

Write serializers with explicit field lists — never fields = "__all__". Never expose anything
sensitive (there's nothing token-like here, but keep file_path handling honest — don't leak
absolute filesystem paths if MEDIA_ROOT differs from what a frontend should see; use
appkit.media.file_url where a client-consumable URL is more appropriate than a raw storage path).

Then tests: per APP-DESIGN.md §7.4 — every view gets 200 for a staff user, 403 for a
non-staff/non-superuser authenticated user (there's no "someone else's object" case since there's
no per-user ownership here — the IDOR-equivalent test is "an authenticated non-admin can reach
nothing"), 401 unauthenticated. Plus a test that POST /orphans/delete/ rejects a path not present
in the current snapshot. Plus one test per throttle scope asserting it's applied. Run pytest and
paste coverage.

Then generate the schema: DJANGO_SETTINGS_MODULE=tests.backend.settings uv run python manage.py
spectacular --file schema.yml --fail-on-warn, and commit schema.yml.
```

**Verify:** coverage over 85%; the "non-admin gets 403 everywhere" test exists and genuinely
fails when `IsAppAdmin` is temporarily swapped for `IsAuthenticated` (worth actually trying);
`--fail-on-warn` clean.

**Review for:** any endpoint missing `IsAppAdmin` (this app has zero tolerance for that — there's
no lesser permission tier to accidentally fall back to); `/orphans/delete/` accepting an arbitrary
path instead of validating against the snapshot; pagination reading from the cache, not
re-scanning.

### Phase 5 — The Jazzmin orphan-review page

Split out from the generic guide's Phase 2/4 because it's genuinely its own decision point —
this is the page a human clicks "delete" on, so its own review matters more than most admin pages.

```
Phase 5: the orphan-review admin page. docs/APP-DESIGN.md §5, this app's docs/CONTRACT.md's
Phase-5 design decision from item 1.

Implement per whichever of the two approaches CONTRACT.md decided:

Option A (unmanaged model): a Meta.managed=False model (no real table — Django never migrates it)
representing one orphan file row, registered in admin.py with a ModelAdmin whose changelist_view
is fully overridden to call services.OrphanScanner.scan() instead of querying a table, renders
django-admin's own changelist template with the results, and wires "select rows -> delete" through
an admin action calling CleanupService.run(file_paths=selected, initiated_by=request.user). This
gets a real Jazzmin sidebar entry for free, using the model's own permission machinery
(has_view_permission/has_delete_permission gated on is_staff — never touch has_add_permission,
there's nothing to add).　If DRF's queryset-free changelist plumbing fights this (Django admin
assumes a queryset backing the changelist in several internal places), fall back to Option B and
say so explicitly rather than fighting the framework.

Option B (custom admin view): a view in admin_views.py reached by adding a path in
CleanupRunAdmin.get_urls() (e.g. cleanup_app_orphanfile/), rendering a custom template at
templates/admin/cleanup_app/orphans.html extending admin/base_site.html, with the same scan +
select + delete flow as Option A, gated by request.user.is_staff in the view itself (Django admin
already enforces is_staff for anything registered on the AdminSite, but a bolted-on URL needs its
own check). Document the Jazzmin custom_links entry a host adds to JAZZMIN_SETTINGS to surface
this in the sidebar, since it isn't a real ModelAdmin.

Whichever is chosen:
- The delete action goes through CleanupService.run() — never a direct storage.delete() call in
  the admin code. Same rails as every other delete path: dry-run isn't offered in the UI (this is
  a human confirming real intent), but grace period and exclude patterns still apply, and a
  confirmation step (Django's own delete_selected-style intermediate page, or a simple "are you
  sure, N files, X bytes" template) is mandatory before anything is actually deleted.
- locale/ + at least one committed .mo (even a minimal one) — MANIFEST.in already declared it in
  Phase 1, but nothing has shipped translated strings yet; add translatable strings to this
  template/view and compile at least one locale so Phase 8's wheel-smoke-test has something real
  to find.
- templates/admin/cleanup_app/... namespaced per INTEGRATION-GUIDE.md's override convention.

Then a test: the confirmation step actually blocks a GET from deleting anything (only a POST with
the confirmation token/field does), and a non-staff request to the page 302s to login or 403s.
```

**Verify:** the page renders in `tests.backend`'s admin (or the playground, once it exists) and
the confirm-then-delete flow works against a real `CleanupService.run()` call, not a stub.

**Review for:** any delete triggered by a bare GET; the page reachable by a non-staff session;
`.mo` actually present in `locale/` (not just a `.po`) — `msgfmt`/`compilemessages` must have run.

### Phase 6 — Frontend SDK

```
Phase 6: the frontend half. docs/APP-DESIGN.md §12, this app's docs/CONTRACT.md item 6.

Create in frontend/:
- package.json: name "@hjtdev/django-cleanup", react/@tanstack/react-query/@hjtdev/appkit as
  peerDependencies ONLY, openapi-typescript as devDependency, generate:types script
  ("openapi-typescript ../backend/schema.yml -o src/schema.d.ts"), exports map with just ".",
  files: ["dist"], version matching backend/pyproject.toml.
- Run npm run generate:types (needs backend/schema.yml from Phase 4) -> src/schema.d.ts. Never
  hand-edit it.
- tsconfig.json (strict), tsconfig.build.json, vitest.config.ts, eslint config.
- src/types.ts — re-export narrowed aliases from schema.d.ts (CleanupRun, CleanupRunFile,
  OrphanFile, etc. as needed), re-export HttpClient from @hjtdev/appkit (never redeclare it).
  Given this app has no non-schema-expressible shapes, expect this file to be thin.
- src/api/config.ts: export const useCleanupConfig = () => useApiClient("cleanup",
  "/api/v1/cleanup"); — never exported from index.ts.
- src/api/manager.ts — CleanupManager, instance-based (constructor takes client + basePath),
  methods: listOrphans(params), deleteOrphans(paths), listRuns(params), getRun(id),
  triggerCleanup(options), getSummary(). The only place a raw HTTP call exists. Never exported
  from index.ts.
- src/hooks/: useOrphanFiles(params), useDeleteOrphanFiles(), useTriggerCleanup(),
  useCleanupRuns(params), useCleanupRun(id), useCleanupSummary() — thin react-query wrappers per
  APP-DESIGN.md §12's "Manager & hook conventions", each reading useCleanupConfig(), building the
  manager with useMemo. Export a cleanupKeys factory. useDeleteOrphanFiles and useTriggerCleanup
  invalidate cleanupKeys.orphans() and, once a run finishes, cleanupKeys.runs()/summary() too.
- src/index.ts — hooks, cleanupKeys, and this app's own types only. No provider, no manager, no
  config hook exported.

Then tests/frontend with Vitest + MSW: success AND error path per hook, onUnhandledRequest:
"error", retry: false. Wrap renders in appkit's ApiClientProvider with a stub client. Include a
test that useDeleteOrphanFiles and useTriggerCleanup only fire on an explicit mutate() call, never
on mount — this app's mutations are the "irreversible action" case APP-DESIGN.md §12's frontend
security checklist calls out by name.

Run npx tsc --noEmit, npm run lint, npm run test, npm run build. Paste all four.
```

**Verify:** all four pass; `dist/index.d.ts` exists; no `any` on any request/response type;
`git diff --exit-code src/schema.d.ts` after re-running `generate:types` is clean.

**Review for:** `react`/`@tanstack/react-query`/`@hjtdev/appkit` in `dependencies` instead of
`peerDependencies`; the manager or `useCleanupConfig` leaking through `index.ts`; a provider being
exported at all; a mutation hook firing on mount or a passive render.

### Phase 7 — Playground

```
Phase 7: the playground. docs/APP-DESIGN.md §11.2.

Create playground/ — a minimal Django + Next.js host, both halves linked by PATH:
- playground/backend/ — minimal Django project with cleanup_app AND django_cleanup's own
  CleanupConfig NOT explicitly added (prove the ready()-driven auto-connect from Phase 1 is
  sufficient on its own) in INSTALLED_APPS, MEDIA_ROOT pointed at a real local directory seeded
  with a few files: some referenced by a playground model, some genuinely orphaned, one written
  within the grace period. pyproject.toml with [tool.uv.sources] path-editable to ../../backend.
- playground/frontend/ — minimal Next app, QueryClientProvider + appkit's ApiClientProvider
  mounted with basePaths={{ cleanup: "/api/v1/cleanup" }}, one page exercising every hook: list
  orphans, trigger a full cleanup, trigger a partial cleanup on selected paths, view run history,
  view summary.
- playground/docker-compose.yml — Postgres, Redis (for the celery extra path), both halves.

Bring it up and exercise every hook through the UI, and report on what only a live round trip
shows:
- does the orphan list actually reflect real files on real disk, correctly excluding the
  grace-period file and any referenced file
- does triggering a cleanup actually delete real files off real disk, and does the run's
  files_deleted/bytes_freed match what actually happened
- does a mutation's onSuccess actually invalidate and refetch the orphan list and run history
- does pagination work against more orphans than one page
- does the celery extra path (CLEANUP["USE_CELERY"]=True, a worker running) actually return 202
  and produce a pending-then-finished run, if wired up in this environment
- does the Jazzmin admin page from Phase 5 work identically to the API path against the same data
- does the error envelope render correctly for a deliberately-broken request (e.g. deleting a
  path not in the current snapshot)

Report any discrepancy and which half is actually wrong.
```

**Verify:** a real orphaned file on disk is correctly identified and, on trigger, actually
removed, with `CleanupRun`/`CleanupRunFile` rows matching reality — this is the one test nothing
else in the suite can give you, since every other test mocks either storage or the HTTP layer.

### Phase 8 — README (the config block)

```
Phase 8: README.md. docs/APP-DESIGN.md §8 is the required structure — every section.

Fill it from what was actually built (code is the truth, not CONTRACT.md — report any
disagreement rather than papering over it). Include: installation (both halves, note the
optional [celery] extra), compatibility, the CLEANUP settings block with every key and its
default, "no .env keys required" stated explicitly (don't leave that section implying one exists),
URL mounting (note urls.py is intentionally unmounted / empty — only urls_admin.py is meaningful),
migrations, signals table (cleanup_run_started/cleanup_run_finished with exact payloads), services
table (OrphanScanner + CleanupService signatures), test helpers note (factory-boy in the host's
test group), recommended periodic schedule (cleanup_orphans daily via either the management
command + host cron, or cleanup_app.tasks.run_scheduled_cleanup if the celery extra + beat is in
use — document both paths since Celery is optional here), suggested Jazzmin icon + the Phase 5
custom_links snippet if Option B was chosen, frontend install and usage including the basePaths
entry.

The settings/URL blocks must be copy-pasteable into a host with zero edits — verify by copying
them into playground/backend and confirming it still boots.

Then list every place README, CONTRACT.md, and the code disagree.
```

**Verify:** copying the README's blocks into a fresh playground config, it still boots.

### Phase 9 — CI, changelog, first release

```
Phase 9: CI and release.

1. Confirm hjtdev-django-cleanup (PyPI) and @hjtdev/django-cleanup (npm) are still free — this
   guide verified both at the time this document was written; re-check before tagging, since
   time has passed.
2. README sync: backend/pyproject.toml readme = "README.md" (not "../README.md"). Copy the
   finished README.md into backend/README.md and frontend/README.md verbatim. Add [project.urls]
   and package.json homepage/bugs pointing at github.com/HjtDev/django-cleanup.
3. .github/workflows/ci.yml — the caller from docs/APP-DESIGN.md §10.2, package-name:
   cleanup_app, coverage-threshold: 85, publish-npm: true, plus the publish-pypi job verbatim per
   §10.2 (this cannot live in the shared reusable workflow — see that section for why).
4. CHANGELOG.md — Keep a Changelog format, 1.0.0 entry covering everything built in Phases 0-8.
5. Verify version lockstep: backend/pyproject.toml, frontend/package.json, CHANGELOG.md all at
   1.0.0.
6. Walk docs/APP-DESIGN.md §9's security checklist item by item, with evidence — pay particular
   attention to: "file uploads validate type and size server-side" (N/A here, this app doesn't
   accept uploads, say so explicitly rather than skipping the line silently) and "no unauthenticated
   access to write endpoints" (trivially true here since NOTHING is accessible without
   IsAppAdmin — confirm that's actually still the case after Phase 5/6's additions).
7. Walk §12's frontend security checklist the same way, with particular attention to the
   destructive-mutation-never-fires-on-mount item — this app's two mutations are both destructive.
8. Register both trusted publishers before the first tag, per §10.2's steps 2-4.

Then give the exact commands to tag and push v1.0.0.
```

**Verify:** CI green on a PR; after the tag push, both registry pages show a real, non-empty
description — check directly, not from green CI alone.

### Phase 10 — Install it into a real host

```
Phase 10: real-world verification. In a fresh clone of base-scaffold, install
hjtdev-django-cleanup at v1.0.0 following docs/INTEGRATION-GUIDE.md §2 — all steps, using only
README.md for configuration values. Don't use anything you know from building the package.

Specifically confirm: cleanup_app added to INSTALLED_APPS (last), no separate
django_cleanup.apps.CleanupConfig entry needed, urls_admin.py mounted, no .env changes needed,
CLEANUP settings block copy-pasted as-is boots cleanly, the Jazzmin sidebar entry appears without
further JAZZMIN_SETTINGS edits (Option A) or appears after the one documented custom_links edit
(Option B), and a manually-created orphan file in the host's real MEDIA_ROOT is correctly found
and removable through both the admin page and the API.

Report every step that didn't work as documented, every value the README omitted, and every
place you had to guess. Then fix the README.
```

Finally: add the app to the registry (`BASE-DESIGN.md` §11.3).

---

## 3. Prompt patterns for this app

The generic guide's boundary/host-perspective/version-impact questions all apply unchanged
(`CLAUDE-CODE-GUIDE-APP.md` §3) — run them at the end of Phases 3, 4, and 6. Two more, specific
to a package whose entire job is deleting files, worth running at the end of Phase 3 and again
before tagging v1.0.0:

> "List every code path in this package that can delete or move a file on disk. For each, name
> the function, and confirm it goes through `CleanupService` and honours dry-run, the grace
> period, and exclude patterns. If any path doesn't, that's not a style issue — fix it before
> continuing."

> "Describe a realistic scenario where this app would delete a file a user still needs. What
> currently prevents it, and is that protection tested?"

## 4. Failure modes specific to this app

| Symptom | Cause | Guard |
|---|---|---|
| A just-uploaded file vanishes | Scanned before its model row committed | `GRACE_PERIOD_SECONDS` — tested in Phase 3 |
| A thumbnail cache directory gets wiped | Treated as orphaned because nothing points at it by name | `EXCLUDE_PATTERNS` |
| Orphan list is stale on page 2 | Pagination re-scans storage per page instead of reading the cached snapshot | Phase 3's `cached_call` snapshot, Phase 4's pagination reading from it |
| A file "belonging" to an ignored model is deleted anyway | `IGNORED_MODELS` applied to the scanner's reference set but not to upstream's auto-hook (or vice versa) | Phase 1's `AUTO_CONNECT` hook and Phase 3's `build_reference_set()` must read the same setting |
| Migration tries to create a table for the orphan-review model | Unmanaged model missing `Meta.managed = False` | Checked explicitly in Phase 5's review |
| A non-staff user reaches any endpoint | A view missing `IsAppAdmin`, or `permissions.py` accidentally reimplementing `appkit`'s class with a bug | Phase 4's "403 everywhere for non-admin" test, tried against a temporarily-weakened permission |

## 5. Done means

Everything in `CLAUDE-CODE-GUIDE-APP.md` §7, plus:

- [ ] A test proves the grace period protects a file modified within the window.
- [ ] A test proves `dry_run=True` deletes nothing but still writes history rows.
- [ ] A test proves a file referenced by any model (including via a reverse relation) is never
      treated as orphaned.
- [ ] Every delete-capable code path goes through `CleanupService` — confirmed by the boundary
      question in §3, not assumed.
- [ ] `IGNORED_MODELS` verified to apply identically to the scanner and the auto-hook.
- [ ] The Jazzmin orphan-review page's delete action is unreachable via a bare GET.
- [ ] Playground Phase 7 actually deleted a real file off real disk and the run's recorded counts
      matched reality.
