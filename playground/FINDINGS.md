# Phase 7 playground — findings

Phase 7, `docs/APP-DESIGN.md` §11.2 / `docs/CLAUDE-CODE-GUIDE-APP-MEDIA-CLEANUP.md`'s own Phase 7
brief: bring up a minimal Django + Next.js host with both halves of `hjtdev-django-cleanup` linked
by path, exercise every hook and the Jazzmin admin page against real data, and record what only a
live round trip shows. This is the one test nothing else in the suite gives — every backend test
mocks storage via `override_settings(STORAGES=...)`, every frontend test mocks HTTP via MSW.

The interactive debugging pass (§1–7 below, faster iteration on the two rewrite/settings bugs
found) ran against local venv/host processes; the real `docker compose -f playground/docker-
compose.yml up -d --wait` stack was then brought up separately against the same config and
re-verified end to end (full run through the frontend proxy, `pytest -m live`, the shared
`worker` media volume) — which is where findings 8 and 9 surfaced, specific to the containerized
path.

## Summary — where every fix belongs

| # | Finding | Fix belongs in |
|---|---|---|
| 1 | Next.js rewrite catch-all params (`:path*`) drop a trailing slash, colliding with Django's `APPEND_SLASH` into an infinite redirect loop | `docs/APP-DESIGN.md` §11.2 (playground guidance) — worked around in `playground/frontend/next.config.ts` |
| 2 | A host must wire `appkit` itself (`INSTALLED_APPS`, `RequestIDMiddleware`, `EXCEPTION_HANDLER`, `DEFAULT_PAGINATION_CLASS`, `NUM_PROXIES`/`APPKIT`) before `cleanup_app` — omitting it is silent until a live request shows DRF's bare `{"detail": ...}` instead of the documented error envelope | This app's own `README.md` §8 (Phase 8) — should say so explicitly, not just assume a host already did it |
| 3 | `LOGGING` needs `appkit.request_id.RequestIDFilter` wired or `appkit.W005` fires | Same as #2 — a one-line addition to the README's settings block |
| 4 | `django-jazzmin` resolves cleanly against Django 6.0.8 (this app's own range is `<7.0`) | No fix needed — recorded as a positive result |
| 5 | `cleanup_app`'s own `ready()`-driven auto-connect works with **zero** `django_cleanup` entry in `INSTALLED_APPS` | No fix needed — this was the headline claim Phase 7 exists to prove; confirmed live (§1 below) |
| 6 | The npm-workspace layout assumed by §11.2 (SDK-under-test lives *inside* `playground/`) doesn't hold here — this app's SDK is the repo's own `frontend/`, a sibling of `playground/frontend/` | `docs/APP-DESIGN.md` §11.2 — document the "extend the repo-root workspace" shape as a valid alternative |
| 7 | Every `cleanup_app` endpoint being `IsAppAdmin`-gated makes appkit's playground shape (a different origin, `NEXT_PUBLIC_API_URL`) awkward — same-origin via Next `rewrites()` avoids CORS/`credentials` plumbing entirely | `docs/APP-DESIGN.md` §11.2 — worth naming as the preferred shape for an all-admin app |
| 8 | `frontend/package.json`'s `prepare` script needs full source present at `npm install` time — a package.json-only Docker layer (copied for cache efficiency) fails the build outright | `playground/frontend/Dockerfile` — fixed by copying full source before the one workspace-wide `npm install` |
| 9 | `seed_media --reset`'s `shutil.rmtree(MEDIA_ROOT)` fails against a Docker named-volume mount point (`Device or resource busy`), silently aborting the reseed after clearing every file underneath | `playground/backend/demo/management/commands/seed_media.py` — fixed to clear MEDIA_ROOT's contents, never the directory itself |

## 1. `cleanup_app`'s auto-connect works with zero `django_cleanup` in `INSTALLED_APPS` — confirmed

This is Phase 7's headline requirement (`docs/CLAUDE-CODE-GUIDE-APP-MEDIA-CLEANUP.md`: "django_cleanup's own CleanupConfig NOT explicitly added ... in INSTALLED_APPS"). `playground/backend/config/settings.py` lists only `"cleanup_app"` — never `"django_cleanup"` in any form. Confirmed live, not just by reading `apps.py`:

```
>>> from django_cleanup import cache
>>> cache.FIELDS.keys()
dict_keys(['demo.document', 'demo.avatar'])
>>> from django.apps import apps
>>> apps.is_installed('django_cleanup')
False
```

`demo.Document`/`demo.Avatar` (the playground's own `FileField`/`ImageField` models) are hooked
via upstream's cache with **no** `INSTALLED_APPS` entry for `django_cleanup` at all —
`cleanup_app.apps.CleanupAppConfig.ready()`'s plain-Python `import django_cleanup.cache` /
`.handlers` is sufficient on its own, exactly as designed.

## 2. The trailing-slash redirect loop — a real, reproducible bug

**Fix belongs in: this playground** (`next.config.ts`), with a documentation note owed to
`docs/APP-DESIGN.md` §11.2 for the next app package that proxies same-origin to a Django backend
through Next.js `rewrites()`.

**Symptom**, found live while trying to load `/admin/login/` through the proxy: `curl -v` showed
an endless alternation of redirects, the query string growing by one URL-encoding layer every
hop:

```
> GET /admin/login/ HTTP/1.1
< HTTP/1.1 308 Permanent Redirect
< location: /admin/login
> GET /admin/login HTTP/1.1
< HTTP/1.1 302 Found
< location: /admin/login/?next=/admin/login
> GET /admin/login/?next=/admin/login HTTP/1.1
< HTTP/1.1 308 Permanent Redirect
< location: /admin/login?next=%2Fadmin%2Flogin
...
```
(never terminates — the real browser reported `net::ERR_TOO_MANY_REDIRECTS`).

**Root cause, isolated by bisecting each layer with direct `curl` calls against the Django
backend (bypassing Next entirely) and matching `Host` headers:**

1. `next.config.ts`'s first-draft rewrites used a **repeated** wildcard param, `:path*`
   (`{ source: "/admin/:path*", destination: "${BACKEND_URL}/admin/:path*" }`). A repeated param
   tokenizes the matched suffix into an array of **non-empty segments** before the destination
   template re-joins them with `/` — a trailing slash carries no segment of its own, so it is
   silently dropped on every proxied request. Confirmed directly: `curl -H "Host: localhost:3000"
   http://127.0.0.1:8001/admin/login` (no trailing slash, mimicking what Next actually forwards)
   reproduces the exact same 302 that `curl http://localhost:3000/admin/login/` produced through
   the proxy.
2. Two config flags were tried and **neither fixes it**, because both only affect what Next does
   at its own edge, not how the rewrite destination is *constructed*:
   - `skipTrailingSlashRedirect: true` stops **Next's own** 308 (its default behavior of
     redirecting `/foo/` → `/foo`) but the internal, already-stripped pathname is still what gets
     forwarded to the destination.
   - `trailingSlash: true` makes Next's *own* routes trailing-slash-canonical; it does not change
     how a repeated rewrite param reconstructs its destination string.
3. With the slash dropped, Django's own `CommonMiddleware` (`APPEND_SLASH`) and
   `AdminSite`'s `catch_all_view` (wrapped by the same `admin_view` permission check as every
   other admin URL) both fire redirects that **re-add** the slash — a plain `/admin` 301s cleanly
   back to `/admin/`, but `/admin/login` (no slash) doesn't match the exact
   `path("login/", ...)` pattern, falls through to `catch_all_view`'s wrapped `re_path(r"(?P<url>.*)$", ...)`, finds the requester unauthenticated, and 302s to `admin:login` with
   `next=<request.get_full_path()>` — i.e. back to the very same slash-dropped path, with the
   query string appended. The browser follows that through the **same** rewrite, which drops the
   slash again, forever.

**Fix**: a single named param with an explicit `(.*)` regex instead of a repeated `*` param.
`path-to-regexp`'s `(.*)` capture matches the remainder as **one raw string**, trailing slash
included verbatim — no segment-array round-trip to lose it:

```ts
// playground/frontend/next.config.ts
async rewrites() {
  return [
    { source: "/api/:path(.*)", destination: `${BACKEND_URL}/api/:path` },
    { source: "/admin/:path(.*)", destination: `${BACKEND_URL}/admin/:path` },
    { source: "/static/:path(.*)", destination: `${BACKEND_URL}/static/:path` },
    { source: "/media/:path(.*)", destination: `${BACKEND_URL}/media/:path` },
  ];
},
```

Verified fixed: `/admin/login/` now single-hops to 200; `/admin/` single-redirects (one hop, not
a loop) to `/admin/login/?next=/admin/` for an unauthenticated visitor, matching Django's own
direct behavior exactly.

**Why no unit test caught this**: neither half's own suite ever runs a request through a Next.js
rewrite — the backend suite talks to Django directly (`APIClient`/`Client`), the frontend suite
mocks HTTP via MSW at the `fetch` layer, never through a real Next.js server. Only a live round
trip through the actual proxy surfaces it.

## 3. A host must wire `appkit` itself before `cleanup_app` — not obvious until a live 403 shows the wrong shape

**Fix belongs in: this app's own `README.md`** (Phase 8) — it should say this explicitly rather
than assume a host has already done it.

First draft of `playground/backend/config/settings.py` wired `cleanup_app` (`INSTALLED_APPS`,
`CLEANUP` dict, the six throttle-rate entries) but never wired `appkit` itself — no
`INSTALLED_APPS` entry, no `RequestIDMiddleware`, no `EXCEPTION_HANDLER`/`DEFAULT_PAGINATION_CLASS`
override. `manage.py check` stayed silent (appkit's own system checks, `appkit.E001`/`E002`, only
run *if* `INSTALLED_APPS` lists `appkit` at all — omitting it entirely doesn't trip them), so
nothing caught this until a live `curl` against a non-staff request showed DRF's bare
`{"detail": "Authentication credentials were not provided."}` instead of the documented envelope:

```json
{"error": {"code": "not_authenticated", "message": "...", "details": {}, "request_id": "..."}}
```

`cleanup_app`'s own admin views raise `PermissionDenied`/`ValidationError` same as any other DRF
view — the envelope shape is entirely a function of the *host's* `REST_FRAMEWORK["EXCEPTION_
HANDLER"]`, which `cleanup_app` never sets itself (correctly — it isn't this app's setting to
own). This app's `README.md` §8 documents `CLEANUP` settings and the six throttle scopes in
detail but doesn't call out "and also finish appkit's own wiring first" as a checklist item;
Phase 8 should add one line making that dependency explicit, since a host that has appkit
installed as a *library* dependency but forgets the *settings* wiring gets no error at all — just
a silently wrong response shape.

Fixed here by adding `appkit` to `INSTALLED_APPS`, `RequestIDMiddleware` right after
`SecurityMiddleware`, `EXCEPTION_HANDLER`/`DEFAULT_PAGINATION_CLASS`/`NUM_PROXIES` to
`REST_FRAMEWORK`, and an `APPKIT = {"TRUSTED_PROXY_COUNT": 0}` (see finding 7 below for why 0, not
appkit's own default of 1). Also needed: `LOGGING["filters"]["request_id"]` wired to
`appkit.request_id.RequestIDFilter`, or `appkit.W005` fires (harmless warning, but another thing
this README could name up front).

## 4. `django-jazzmin` resolves cleanly against this app's own Django range

`playground/backend/pyproject.toml` adds `django-jazzmin>=3.0` alongside this app's own
`django>=5.2,<7.0` range. `uv sync` resolved `django==6.0.8` + `django-jazzmin==3.0.5` with no
conflict, and `manage.py check` stayed silent. The orphan-review page's Jazzmin sidebar entry,
icons (`JAZZMIN_SETTINGS["icons"]`, copied from `admin.py`'s own suggested snippet), and the full
confirm-then-delete flow all render and function identically to stock admin — see §5 below for the
live delete-flow proof. No fallback to stock admin was needed.

## 5. The verified round trip — what only a live stack proves

All of the following were run against real Postgres/Redis and a real `FileSystemStorage` disk
(the local venv + `uvicorn`/`celery`/`next dev` processes, then re-confirmed identical config
drives `docker-compose.yml`):

- **Orphan list vs. real disk**: `seed_media` wrote 2 referenced files (a `demo.Document`, a
  `demo.Avatar`), 30 genuinely orphaned files across four directories (proving the recursive
  `_walk()`), 1 grace-period file, and 1 excluded (`*.keep`) file. `GET /orphans/` returned
  exactly the 30 orphans — the referenced, grace-period, and excluded files were correctly never
  candidates. (The grace-period file *does* eventually appear once real wall-clock time exceeds
  `GRACE_PERIOD_SECONDS` — observed later in this same session, confirming the rail is genuinely
  time-relative, not a static flag.)
- **Deleting real files**: `POST /orphans/delete/` on 3 named paths removed exactly those 3 from
  disk, left the rest untouched, and `CleanupRunFile` rows (`deleted=True`) plus the run's
  `files_deleted`/`bytes_freed` matched the real byte counts (`45` bytes = 15+15+15, verified
  against each file's actual size before deletion).
- **A full run**: `POST /runs/` deleted every remaining real orphan (27 in this pass), left
  referenced/grace-period/excluded files on disk, and `files_scanned == files_deleted == 27`,
  `files_failed == 0`.
- **Pagination against real data**: `GET /orphans/` at the default page size (25) returned
  `next` pointing at page 2; page 2 returned the remaining 5 with `previous` set and `next: null`
  — real second-page data, not a mock.
- **The Celery path**: with `CLEANUP["USE_CELERY"]=True` and a real `celery -A config worker`
  running against the same Redis and the same `MEDIA_ROOT`, `POST /runs/` returned **202** with a
  `PENDING` run; polling `GET /runs/{id}/` showed it transition to `SUCCESS` with real
  `files_deleted`/`bytes_freed`, and the files were genuinely gone from disk — proving the worker
  process (a separate OS process) shares the same storage view as the web process, which is
  exactly what `docker-compose.yml`'s named `media` volume (shared between `backend` and
  `worker`) is designed to guarantee in the containerized path.
- **The management command**: `manage.py cleanup_orphans --dry-run` scanned 30 candidates,
  deleted 0, and disk was verified byte-for-byte unchanged before/after.
- **Auto-delete + `TRACK_AUTO_DELETIONS`**: deleting a `demo.Document` row removed its real file
  from disk via upstream `django_cleanup`'s own per-delete hook, and `cleanup_app`'s receiver
  logged it as a `CleanupRun(trigger="auto", status="success", files_deleted=1, bytes_freed=0)`
  — `bytes_freed=0` is documented, expected behavior (`receivers.py`'s own docstring: the file is
  already gone by the time the signal fires, so its size is unrecoverable), not a bug.
- **The 400 rejection path**: `POST /orphans/delete/` with a path absent from the current
  snapshot returned 400 with the full appkit error envelope (`validation_error`), and touched no
  file on disk.
- **Non-staff 403**: every admin endpoint, hit with no credentials, returned 403 with the appkit
  envelope (`not_authenticated`).
- **The Jazzmin admin page, end to end**: logged in via a real Django session, `GET
  /admin/cleanup_app/orphanfile/` rendered the same file list the API returned; a bare `POST
  action=delete` with no `confirm=yes` rendered the confirmation page and deleted nothing (file
  still present on disk, verified); the follow-up `POST` with `confirm=yes` deleted the real file
  and produced a `CleanupRun(trigger="manual", status="success", files_deleted=1,
  bytes_freed=15)` row — the same shape, same rails, as the API path.
- **The React round trip, driven by a real headless browser (`agent-browser`) against
  `http://localhost:3000`**, logged in through the proxied `/admin/login/`:
  - `useOrphanFiles` rendered the real list; pagination's Previous/Next buttons moved between
    real pages (`count=31` split 25/6 across two pages at one point in the session).
  - Selecting 2 files and clicking "Delete selected" — `useDeleteOrphanFiles` — updated the
    on-screen orphan count (31→29) **and** the summary panel (`total_runs` 0→1,
    `files_deleted_total` 0→2) **and** the run-history table (a new row appeared) with **zero**
    manual reload — the `onSuccess` `invalidateQueries` calls for `orphans()`, `summary()`, and
    `runs()` all genuinely fired and refetched.
  - `useCleanupRun` (the "Inspect" button) expanded a run's `CleanupRunFile` rows correctly,
    matching exactly the two paths just deleted.
  - `useTriggerCleanup` was exercised both with `dry_run` checked (run recorded, disk unchanged,
    orphan count unchanged) and unchecked (run recorded, disk emptied, orphan count → 0) — the
    same backend instance had `USE_CELERY=True` at the time, so both trigger clicks returned a
    `PENDING` run that transitioned to `SUCCESS` a moment later, once more proving the async path
    from the browser's own perspective, not just via `curl`.
  - The deliberate "Break it" button (`useDeleteOrphanFiles` on a path never in the current
    snapshot) rendered `validation_error (400): Validation failed.` — legible text, not
    `[object Object]` or a blank error.
  - Browser console: no errors, no warnings — in particular no `"No QueryClient set, use
    QueryClientProvider to set one"`, confirming the repo-root npm workspace (finding 6) actually
    dedupes `react`/`@tanstack/react-query`/`@hjtdev/appkit` between `frontend/` (the SDK) and
    `playground/frontend/` (the host) into one physical copy each.

No discrepancy was found between the API path's numbers and the Jazzmin admin path's numbers, or
between what the frontend displayed and what the backend/disk actually did, once findings 2 and 3
above were fixed.

## 8. The frontend Docker image's `prepare` script needs source present before `npm install`

**Fix belongs in: `playground/frontend/Dockerfile`.**

First draft copied only `package.json` files into the image before `npm install` (a standard
layer-caching trick: dependencies rarely change, source does). It failed outright:

```
npm error command failed
npm error command sh -c tsc -p tsconfig.build.json
npm error error TS5058: The specified path does not exist: 'tsconfig.build.json'.
```

`frontend/package.json`'s own `"prepare": "tsc -p tsconfig.build.json"` script runs automatically
as part of an `npm install` that touches that workspace member — and with only `package.json`
copied, `tsconfig.build.json` and `src/` don't exist yet in the image. Fixed by copying
`frontend/`'s and `playground/frontend/`'s full source before the one workspace-wide `npm
install`, trading some layer-cache efficiency for a build that actually completes. (Appkit's own
`playground/frontend/Dockerfile` avoids this by installing appkit's `frontend/` standalone,
*outside* the workspace `npm install`, before ever touching `playground/`'s own
`package.json`s — not applicable here, since this repo unified both into one workspace per
finding 6.)

## 9. `seed_media --reset` fails against a Docker volume mount point

**Fix belongs in: `playground/backend/demo/management/commands/seed_media.py`.**

First draft's `_reset()` called `shutil.rmtree(MEDIA_ROOT)` then `os.makedirs(MEDIA_ROOT)` to
clear old state. Worked fine on the bare host (venv-only) pass, but failed the moment `--reset`
ran inside the actual `docker compose` stack:

```
OSError: [Errno 16] Device or resource busy: PosixPath('/app/playground/backend/media')
```

`docker-compose.yml`'s named `media` volume — the thing that makes `backend` and `worker` share
one real disk (§5's Celery proof depends on it) — mounts *at* `MEDIA_ROOT` itself, so the
directory inode can't be removed, only its contents. `shutil.rmtree` walks bottom-up and deletes
every file first, so the failure came *after* all the old data was already gone — the command
then raised before reaching `_seed_referenced()`, leaving an **empty** media tree and silently
skipping the reseed. Caught by `pytest -m live` failing `test_orphans_excludes_referenced_and_
protected_files` with `count=0` rather than `>=25` — not by the bare-host pass, since a plain
directory has no such restriction. Fixed by clearing `MEDIA_ROOT`'s contents (`os.listdir` +
per-entry `shutil.rmtree`/`os.remove`) and leaving the mount point itself alone.

## 6–7. Layout deviations from §11.2's literal wording

`docs/APP-DESIGN.md` §11.2 describes a playground whose SDK-under-test (`demo-sdk` in appkit's own
Phase 6 playground) lives *inside* `playground/`, consumed by a separate `playground/package.json`
workspace, with `appkit` itself (`frontend/`, the package actually being tested) reached from
*outside* that workspace via `file:../../frontend`. That shape doesn't fit here as cleanly,
because this app's own `frontend/` **is** the thing under test, and it already lists
`react`/`@tanstack/react-query`/`@hjtdev/appkit` in its own `devDependencies` (needed for its own
`tsc`/Vitest) — exactly the duplicate-physical-copy hazard §12 warns about. The fix taken: extend
the *existing* repo-root workspace (`package.json: "workspaces": ["frontend",
"playground/frontend"]`) rather than create a second, separate one — one hoisted `node_modules`
dedupes everything in a single step, and `@hjtdev/appkit` is pulled from the npm registry (already
a real dependency here) rather than path-linked at all. Confirmed working: zero duplicate-copy
console warnings during the full browser pass in §5.

Similarly, §11.2's own template (appkit's playground) fronts the backend with nginx and points the
frontend at a different origin via `NEXT_PUBLIC_API_URL`, needing `credentials: "include"` and (in
a real cross-origin case) CORS. Every one of `cleanup_app`'s own endpoints is `IsAppAdmin`-gated —
there is no public surface at all — so a same-origin proxy via Next's own `rewrites()` was simpler
and needed no CORS package. Both are recorded as an alternative shape worth naming in §11.2 for
future admin-only app packages, not a defect in appkit's own choice (appkit's playground has a
genuine reason to test a real proxy chain — `client_ip()` — that doesn't apply here).
