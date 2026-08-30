# BASE-DESIGN.md — Starter Scaffold Architecture

> **Companion documents:** `APP-DESIGN.md` (the installable app packages), `INTEGRATION-GUIDE.md` (how a host wires them in), `CLAUDE-CODE-GUIDE-BASE.md` (how to actually build this scaffold with an AI agent).

## Table of contents

1. [Purpose & Ownership Model](#1-purpose--ownership-model)
2. [Monorepo Directory Structure](#2-monorepo-directory-structure)
3. [Pre-Configured Base Stack](#3-pre-configured-base-stack)
4. [Toolchain, Dependencies & Environment Strategy](#4-toolchain-dependencies--environment-strategy)
5. [Code Quality & Testing Setup](#5-code-quality--testing-setup)
6. [Inter-App Integration Layer (`core/`)](#6-inter-app-integration-layer-core)
7. [Continuous Integration](#7-continuous-integration)
8. [Docker & Compose (dev / prod)](#8-docker--compose-dev--prod)
9. [Deployment](#9-deployment)
10. [Bootstrapping & Setup Walkthrough](#10-bootstrapping--setup-walkthrough)
11. [Ecosystem Tooling](#11-ecosystem-tooling)

---

## 1. Purpose & Ownership Model

The base repository is a **one-time starter kit**, not a living upstream dependency. It bundles a Django 6 (ASGI) backend, a Next.js App Router frontend, and Docker Compose orchestration into a single monorepo template. A new project clones it, deletes its `.git` history, and starts its own — there is no ongoing `git pull` from this template into existing projects.

That one decision simplifies ownership considerably. There are only two categories of code in a running project, not three:

| Category | What it is | Editable? |
|---|---|---|
| **Project code** (`backend/`, `frontend/`, everything cloned from this scaffold plus everything written afterward) | Yours from the moment `.git` is deleted — there's no distinction between "scaffold-origin" and "written later" | Freely editable, always |
| **Installed backend app packages** (`.venv/…/site-packages`, via `uv`) | Versioned, third-party, read-only reusable apps — see `APP-DESIGN.md` | Never edited directly — see `INTEGRATION-GUIDE.md` §1 |
| **Installed frontend app packages** (`frontend/node_modules`, via `npm`) | The same reusable apps' TypeScript/React half — typed hooks, fetchers — see `APP-DESIGN.md` | Never edited directly — same rule, same reasoning |

If the scaffold itself improves later (a better `Dockerfile`, a new `tools/` helper), that's backported by hand into existing projects if wanted — never pulled automatically. This trades "automatic updates" for "no merge-conflict risk, ever," which is the right trade once the base stops being a dependency and becomes a starting point.

**One consequence worth stating outright:** because there's no upstream pull, the scaffold's own quality bar has to be high on day one — a mistake baked in here propagates into every project cloned from it and then has to be fixed N times. That's the reasoning behind §5 and §7 existing at all: the scaffold ships with its own linting, typing, tests, and CI configured, so a new project inherits the guardrails rather than being asked to add them later.

## 2. Monorepo Directory Structure

```
my-client-project/
├── .git/                            # single top-level git repository for the whole project
├── .gitignore                       # .env*, node_modules, .venv, __pycache__, .next, media/
├── .env.example                     # [tracked] template for compose-level vars
├── .env.prod.example                # [tracked] template — real .env.prod lives only on the server
├── .pre-commit-config.yaml          # ruff, mypy, prettier, eslint — see §5.1
├── .python-version                  # e.g. "3.14" — matches the Docker base image
├── README.md                        # day-one reference — see §10
├── CLAUDE.md                        # agent instructions — rendered at clone time, see §10.1
├── CLAUDE.md.template               # source rename-project.sh renders CLAUDE.md from, §10.1
├── renovate.json                    # dependency-update bot config — see §7
├── scripts/
│   └── rename-project.sh            # names the project — see §11.1, run once at clone time
├── docs/
│   ├── APP-DESIGN.md                # copied in at clone time so agents can read them locally
│   ├── BASE-DESIGN.md
│   ├── INTEGRATION-GUIDE.md
│   ├── CLAUDE-CODE-GUIDE-BASE.md    # how this scaffold itself was built — reference only
│   ├── CLAUDE-CODE-GUIDE-APP.md     # same treatment for an app package — reference only
│   └── CORRECTIONS.md               # log of repo/spec divergences found after each doc update
├── .github/
│   └── workflows/
│       └── ci.yml                   # host-project CI, see §7
├── docker-compose.yml               # local dev orchestration
├── docker-compose.prod.yml          # production orchestration — see §8.2
├── docker-compose.test.yml          # ephemeral Postgres/Redis for the test suite, §5.3
├── Makefile                         # one memorable entrypoint per common task, see §10.2
├── deploy/                          # [project-owned] deployment tooling, see §9
│   ├── deploy-prod.sh
│   └── deploy.prod.env.example      # template — real deploy.prod.env is gitignored
├── frontend/                        # Next.js App Router (TypeScript), pre-wired to backend
│   ├── Dockerfile                   # dev image
│   ├── Dockerfile.prod              # production image, see §8.1
│   ├── .dockerignore
│   ├── .env.example
│   ├── .prettierrc                  # prettier config — see §5.1
│   ├── .prettierignore
│   ├── package.json
│   ├── package-lock.json            # committed; `npm ci` everywhere, never `npm install` in CI
│   ├── tsconfig.json                # "strict": true
│   ├── next.config.ts               # output: "standalone" — see §8.1
│   ├── eslint.config.mjs
│   ├── vitest.config.ts
│   ├── app/
│   │   ├── layout.tsx               # mounts QueryClientProvider
│   │   ├── page.tsx                 # placeholder — calls /healthz/, shows backend status
│   │   ├── providers.tsx            # mounts QueryClientProvider + appkit's ApiClientProvider
│   │   └── api/health/route.ts      # frontend healthcheck target, see §8.2
│   ├── lib/
│   │   └── api-client.ts            # shared fetcher: base URL, credentials, appkit's
│   │                                  HttpClient/envelope helpers — see §3. makeQueryClient
│   │                                  itself now comes straight from @hjtdev/appkit (no
│   │                                  local copy)
│   ├── tests/                       # vitest — at least one real test per lib/ module
│   └── public/
└── backend/
    ├── pyproject.toml               # deps, dependency-groups, ruff/mypy/pytest config — §4
    ├── uv.lock                      # COMMITTED — the reproducibility guarantee
    ├── .env.example
    ├── .env.prod.example
    ├── Dockerfile                   # dev image
    ├── Dockerfile.prod              # production image, see §8.1
    ├── .dockerignore
    ├── manage.py
    ├── conftest.py                  # project-wide pytest fixtures, see §5.2
    ├── config/                      # settings.py, urls.py, asgi.py, wsgi.py, celery.py
    │   ├── settings.py
    │   ├── urls.py
    │   ├── asgi.py                  # get_asgi_application() — see "WebSockets" below
    │   ├── wsgi.py                  # present for tooling that expects it; never served — §3
    │   ├── celery.py                # Celery app, autodiscovers installed apps' tasks.py
    │   ├── checks.py                # startup validation system checks — see §4.3
    │   ├── logging.py               # dev=colored console, prod=JSON — see §3
    │   ├── views.py                 # cross-cutting views — the /healthz/ endpoint §8.2 uses
    │   └── tests/                   # wiring smoke tests — see §5.4
    ├── core/                        # project-owned integration & glue layer
    │   ├── apps.py                  # AppConfig; ready() imports core/signals.py
    │   ├── signals.py               # inter-app signal listeners
    │   ├── services/                # cross-app business logic orchestrators
    │   ├── views/                   # subclasses/overrides of an installed app's views
    │   └── tests/                   # tests for signals, services, view overrides, plus
    │       └── conftest.py          #   cross-app fixtures using installed apps' factories
    ├── tools/                       # host-owned helpers only — see §3's "The tools/ vs
    │   │                              appkit boundary". crypto.py wraps FERNET_KEY;
    │   │                              caching, the error envelope, and request-ID
    │   │                              correlation moved to the appkit app package
    │   └── tests/                   # crypto round-trip only — see §3
    ├── templates/                   # override point for an installed app's templates
    └── locale/
```

No `.gitmodules`, no `apps/` folder, no dynamic settings-composition machinery, and **no `requirements.txt`**. Everything a previous iteration of this design solved with auto-discovery is now solved simply by this being a normal, explicit Django project — because nothing here needs to survive being merged with an upstream update anymore.

Two additions to the tree worth explaining:

- **`docs/`** — the design documents are copied into every project at clone time. Not for humans (who can read them in the template repo) but for agents: Claude Code can read a local file cheaply and reliably, and `CLAUDE.md` pointing at `docs/INTEGRATION-GUIDE.md` is far more likely to actually be followed than a URL. `CORRECTIONS.md` and the two `CLAUDE-CODE-GUIDE-*.md` files travel along for the same reason but describe how *this* scaffold was built, not anything a cloned project needs day to day.
- **`Makefile`** — a thin, memorable interface over the real commands. Its real value is that `CLAUDE.md` can say "run `make test`" once instead of restating a six-flag `uv run pytest` invocation everywhere, and the invocation can then change in one place.

**No root `.dockerignore`** — only `backend/.dockerignore` and `frontend/.dockerignore` exist; each Dockerfile builds from its own subdirectory as build context, so a root-level file would never apply to either build. See §8.1's code blocks.

## 3. Pre-Configured Base Stack

- **Django 6 on ASGI**, served by Uvicorn (not Gunicorn/WSGI). `uvicorn[standard]` already speaks WebSocket and works fine with Channels if a project needs one later — see "WebSockets" below. `daphne` is the reference ASGI server in Channels' own docs, not a requirement.
- **Django REST Framework + `drf-spectacular`** for the API and its OpenAPI/Swagger schema.
- **`appkit`** — app package #1, the shared dependency every other installed app declares
  (`APP-DESIGN.md` §1.1), installed here regardless of whether any *other* app is
  installed yet. Owns caching helpers, the DRF error envelope, request-ID correlation, DRF
  pagination/permissions/throttling helpers, and the frontend `HttpClient`
  interface/`ApiClientProvider` pair — see "The `tools/` vs `appkit` boundary" below for
  exactly what moved here versus what a host keeps. Full detail: `INTEGRATION-GUIDE.md` §2.
- **Postgres 17** as the only supported database, in dev, test, and prod. No SQLite anywhere, including tests — see §5.3.
- **Celery + Redis** for background jobs needing chaining, retries, or scheduling, with `django-celery-beat`'s `DatabaseScheduler` for periodic tasks (see §6); Django's native `django.tasks` framework for simple one-off jobs (single email, single notification) that don't need Celery's overhead.
- **`django-jazzmin`** for the admin theme, configured via `JAZZMIN_SETTINGS` in `config/settings.py`.
- **`django-cors-headers`, `whitenoise`**, preconfigured.
- **Email**, env-driven via `EMAIL_BACKEND`/`EMAIL_HOST`/`EMAIL_PORT`/`EMAIL_HOST_USER`/`EMAIL_HOST_PASSWORD`/`EMAIL_USE_TLS`/`DEFAULT_FROM_EMAIL` in `config/settings.py`. Code default is the SMTP backend pointed at `mailpit` (the dev-only tooling-profile container, §8.2); `backend/.env.example` ships the console backend live instead, since a plain `docker compose up` (no `--profile tooling`) has no `mailpit` host for the code default to resolve. `config/checks.py`'s `config.E004` fails loudly if `DEBUG=False` and `EMAIL_HOST` is still empty or `mailpit` — the one prod trap a dev-correct code default creates.
- **Logging split by environment** — `config/logging.py` returns a colored, human-readable console config when `DEBUG` is on and a `structlog`-based JSON config when it isn't. This is deliberate: JSON in dev is unreadable to a person, and colored text in prod is unparseable by any log aggregator, so a single config is wrong in one environment no matter which you pick. Both configs include a request ID so a single request's log lines can be correlated — `build_logging_config()` and the structlog processor that stamps it stay here, since the console-vs-JSON choice is host policy; the `ContextVar`, the request-ID middleware, and the `logging.Filter` that reads it live in `appkit.request_id` (see "The `tools/` vs `appkit` boundary" below), imported back into `config/logging.py`'s `LOGGING` dict.

  `appkit.request_id.RequestIDMiddleware` is a raw, non-`MiddlewareMixin` async-only class (`async_capable = True`, `sync_capable = False`, `async def __call__`). Those two class attributes only tell Django's `load_middleware` how to build *that* middleware's own wrapper — they say nothing to `inspect.iscoroutinefunction(instance)`, the separate check any *other* middleware wrapping it (e.g. `SecurityMiddleware`) uses to decide whether to `await` it. `MiddlewareMixin`-based middleware calls `inspect.markcoroutinefunction(self)` internally to make itself visible to that check; a raw async-only middleware class has to do the same in its own `__init__`, or every outer middleware calls it without awaiting and crashes on the returned coroutine. Any future raw async middleware added to `core/` or `config/` needs this same `markcoroutinefunction(self)` call — appkit's own already does.
- **Sentry**, initialized in `config/settings.py` behind a `SENTRY_DSN` env var that's empty by default (so it's inert locally and in CI, active the moment a DSN is set). This is included rather than left out because the combination of Celery workers, ASGI concurrency, and N installed third-party app packages makes "an exception happened somewhere and nobody knew" the default failure mode otherwise. Wire the Django, Celery, and Redis integrations, and set `traces_sample_rate` low (0.1) rather than off, so slow-endpoint data exists when someone asks.
- **`tools/`** — host-owned helpers only, for `config/` and `core/` to use; see `INTEGRATION-GUIDE.md` §6 for why installed app packages don't reach into this folder. As of the appkit v1.0.0 integration this holds only `crypto.py`, a thin wrapper over `appkit.crypto.Cipher` built from `FERNET_KEY` in `.env` — appkit's `Cipher` takes its key as a constructor argument and reads no Django setting or env var of its own, so *something* has to own reading `FERNET_KEY`, permanently. Caching, the DRF error envelope, and request-ID correlation all moved to `appkit` — see the boundary rule directly below.

  `appkit.exceptions.standard_exception_handler` is wired as `REST_FRAMEWORK["EXCEPTION_HANDLER"]` in `config/settings.py`, so every DRF-raised error — not only views that opt into a mixin — renders in one envelope:

  ```json
  {"error": {"code": "validation_error", "message": "...", "details": {}, "request_id": "..."}}
  ```

  `details` is always present (`{}` when nothing is field-level, so a client never has to branch on whether the key exists). `request_id` is the same correlation ID `config/logging.py` stamps on every log line, via `appkit.request_id.request_id_var`. `code` is a stable, machine-readable string clients branch on — adding one is a minor change, renaming one is breaking. The full set is **ten** values, not nine — `"error"` is a documented catch-all in its own right (covering any `APIException` that isn't one of the other nine), not an omission: `validation_error`, `parse_error`, `not_authenticated`, `authentication_failed`, `permission_denied`, `not_found`, `method_not_allowed`, `throttled`, `server_error`, `error`. An unhandled exception is logged (`logger.exception`) before being turned into a `server_error` envelope, so it still reaches Sentry; `message` on a `server_error` is generic with `DEBUG` off and carries the real exception text with it on. Headers DRF already sets — `Retry-After` on `throttled`, `WWW-Authenticate` on `not_authenticated` — are untouched, since the handler rewrites only `response.data`. This is the shape `APP-DESIGN.md` §4 asks every installed app package to bundle an equivalent of.

  #### The `tools/` vs `appkit` boundary

  > **Does an app package need a given helper to behave correctly in any host?** If yes, it belongs in `appkit`. If it depends on host configuration — a host `.env` key, a host setting, a host policy decision — it belongs in `backend/tools/`.

  | Helper | Where | Why |
  |---|---|---|
  | `build_cache_key`, `cached_call`, `invalidate_namespace`, `namespace_version` | `appkit.cache` | Pure functions over Django's cache API. No host config involved. |
  | `CachedListMixin` | `appkit.mixins` | Built on the above; every app's list views need it. `cache_namespace` has no class-name fallback here — it's required, raising `ImproperlyConfigured` if left empty (the scaffold's own pre-appkit version of this mixin had that fallback, which was a bug: two apps each shipping a same-named list view would silently share cache entries in the host's one Redis). |
  | `standard_exception_handler` + the ten error codes | `appkit.exceptions` | The envelope is an ecosystem-wide contract, not host policy — one definition, or different apps' clients see two different shapes for the same kind of error. |
  | `request_id_var`, `RequestIDMiddleware`, `RequestIDFilter` | `appkit.request_id` | The envelope carries `request_id`; an app logging from its own `services.py` has to stamp the same correlation ID the host's views use, which only works if both import the same `ContextVar` object. |
  | `encrypt`/`decrypt` (`tools/crypto.py`) | **stays in `tools/`, permanently** | Wraps the host's own `FERNET_KEY`. An app needing encryption uses its own documented `.env` key and its own cipher (`appkit.crypto.Cipher`, requiring the `crypto` extra) — never the host's `tools.crypto`. |
  | `build_logging_config()`, the structlog `_add_request_id` processor | **stays in `config/logging.py`, permanently** | The dev-console-vs-prod-JSON choice is host policy, not something an app package has any business deciding. |

  **Naming-collision note.** `backend/tools/` (host-owned, never importable by an app package) and `appkit` (shared, always importable by an app package — and explicitly exempt from the `banned-api` rule that keeps other app packages out of `core/`/`config/`, `INTEGRATION-GUIDE.md` §2 step 10) are adjacent concepts with opposite rules — the exact kind of thing that's easy to get backwards under time pressure. The package is named `appkit`, not `tools-app`, specifically so the import line makes the ownership obvious at a glance: `from tools.crypto import encrypt` (host-only) reads nothing like `from appkit.cache import build_cache_key` (shared), where a name like `tools_app` would sit one character from `tools` in a tree where the two have opposite ownership rules.

  **Three settings describe the same physical proxy-hop count and must be changed together**: `APPKIT["TRUSTED_PROXY_COUNT"]` and `REST_FRAMEWORK["NUM_PROXIES"]` in `config/settings.py`, and `UVICORN_FORWARDED_ALLOW_IPS` in `docker-compose.prod.yml`. `appkit.net.client_ip` reads the first; DRF's own `SimpleRateThrottle.get_ident()` (used by `ScopedRateThrottle`) reads the second — appkit's `client_ip` can't be injected into DRF's throttle ident logic, so this has to be set independently, or a throttled view keys off the client's own spoofable leftmost `X-Forwarded-For` entry instead of the trusted, proxy-appended one; uvicorn's `--proxy-headers` reads the third to decide which hosts it trusts to set `X-Forwarded-For`/`X-Forwarded-Proto` at all.

  `appkit.W006` (a real Django system check as of appkit 2.x, run by `manage.py check`) fires on two independent conditions: `NUM_PROXIES` set and disagreeing with `TRUSTED_PROXY_COUNT`, or `NUM_PROXIES` left unset (`None`, whether omitted or explicit) while any `SimpleRateThrottle` subclass is configured — not only `ScopedRateThrottle`; the spoofable-bucket flaw lives in `SimpleRateThrottle.get_ident()` itself, so `AnonRateThrottle`, `UserRateThrottle`, and any host-defined subclass inherit it unchanged, and the check triggers on all of them, whether wired globally via `DEFAULT_THROTTLE_CLASSES` or on any view reachable by walking `ROOT_URLCONF`. Two scoping gaps, both deliberate rather than an oversight: a subclass that overrides `get_ident()` itself is excluded (its own parsing may already be safe, and warning about it would be a false positive this check can't resolve without re-implementing that subclass's logic), and a throttle wired up via `get_throttles()` overridden at runtime, or a permission class doing its own rate limiting outside DRF's throttle machinery entirely, is invisible to it — **a clean `appkit.W006` run is not proof neither exists somewhere.**

  What W006 can't see at all: `UVICORN_FORWARDED_ALLOW_IPS`, a Compose/uvicorn-level env var invisible to Django's own check framework. A host that adds a CDN in front of nginx and updates only that third setting still silently gets a spoofable throttle bucket or a wrong `client_ip`, with no error anywhere — this paragraph is the only thing enforcing that one.
- **Frontend baseline** — Next.js App Router (TypeScript, `strict`) with `@tanstack/react-query` and a shared API client already set up in `frontend/lib/`, so an installed frontend app-package's hooks have a consistent client to plug into out of the box instead of every app package bootstrapping its own.
- **Analytics (optional)** — self-hosted [Umami](https://umami.is), `umami` + its own `umami-db` Postgres instance, behind the dev-only `analytics` compose profile (§8.2), same pattern as the `tooling` profile's `flower`/`mailpit`. Off by default: a plain `docker compose up` never starts it, and with `NEXT_PUBLIC_UMAMI_WEBSITE_ID` unset `frontend/app/layout.tsx` renders no script tag. `NEXT_PUBLIC_UMAMI_SCRIPT_URL`/`NEXT_PUBLIC_UMAMI_WEBSITE_ID` are frontend build ARGs, same build-time-only caveat as `NEXT_PUBLIC_API_URL` (§8.1). See `README.md`'s "Analytics (optional)" section for enabling it and the admin-password warning — Umami's default `admin`/`umami` login cannot be overridden by env.

**Deliberately not included: authentication.** `SIMPLE_JWT` or any other auth configuration does not belong in the base scaffold — auth is its own standalone, versioned app package (per `APP-DESIGN.md`), installed into a project the same way payments or notifications would be. This keeps the scaffold auth-agnostic and keeps a project free to swap auth strategies without touching the base at all.

### WebSockets

**Deliberately excluded, for the same reason as auth.** Django has no WebSocket handling of
its own — adding it means `django-channels` plus a channel layer (Redis-backed, same as
everything else here), and most projects never open a socket. `config/asgi.py` as shipped by
this scaffold only calls `get_asgi_application()`, which handles the `http` scope and nothing
else. That's the full ASGI foundation a project gets by default: real WebSocket support is an
opt-in a project adds when it actually needs one, not baked in speculatively.

`uvicorn[standard]` — already the pinned ASGI server, see above — speaks WebSocket out of the
box and works with Channels; nothing about the server needs to change to add it.

**When a project does need it**, the protocol is the same shape as everything else in this
scaffold: add the dependency, then wire it explicitly in `config/`, never by auto-discovery.

1. `uv add channels channels-redis` to `backend/pyproject.toml`.
2. Compose `http` and `websocket` scopes in `config/asgi.py` with `ProtocolTypeRouter` — the
   host is the mediator for the `websocket` scope in exactly the same sense `config/urls.py`
   is the mediator for `http`:

   ```python
   # config/asgi.py
   import os

   from django.core.asgi import get_asgi_application

   os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

   # get_asgi_application() MUST run before any consumer is imported — consumers pull in
   # models, and importing a model before Django's app registry is populated raises
   # AppRegistryNotReady. This ordering is the one part of this file that isn't optional.
   django_asgi_app = get_asgi_application()

   from channels.auth import AuthMiddlewareStack
   from channels.routing import ProtocolTypeRouter, URLRouter

   # from notifications_app.routing import websocket_urlpatterns as notifications_ws

   application = ProtocolTypeRouter(
       {
           "http": django_asgi_app,
           "websocket": AuthMiddlewareStack(
               URLRouter(
                   [
                       # *notifications_ws,
                   ]
               )
           ),
       }
   )
   ```

3. Update `docker-compose*.yml`'s `backend` service — no change needed to the run command
   itself (`uvicorn config.asgi:application` already serves both scopes once `channels` is
   installed), but production nginx needs an explicit block for the WebSocket path that
   forwards the `Upgrade`/`Connection` headers nginx doesn't pass through by default. This is
   a deploy-side change, not only an application-code one, and easy to forget because
   everything works locally without it (`runserver`/Uvicorn don't need it).

See `APP-DESIGN.md` §6 ("Realtime") for how an installed app package contributes routes and
consumers into this composition.

### Auth integration

**Deliberately excluded, same reasoning as above** — see "Deliberately not included:
authentication" above. This subsection exists because the base stack, as shipped, is
*not* configured for it: `CORS_ALLOW_CREDENTIALS` defaults to `False`,
`CSRF_TRUSTED_ORIGINS` is empty, and `frontend/lib/api-client.ts`'s default
`ApiClient` instance sends `credentials: "same-origin"`. Cross-origin cookie auth
silently does nothing until all of the following change together — an installed
cookie-session auth app's setup instructions (its own `README.md`, per
`INTEGRATION-GUIDE.md` §2) must say to:

1. Set `CORS_ALLOW_CREDENTIALS=True` in `.env`/`.env.prod`
   (`backend/config/settings.py`). This is incompatible with a wildcard origin — the
   browser rejects a wildcard `Access-Control-Allow-Origin` on a credentialed request —
   so `CORS_ALLOWED_ORIGINS` must stay an explicit list, never `CORS_ALLOW_ALL_ORIGINS`,
   in every environment where this is on.
2. Set `CSRF_TRUSTED_ORIGINS` to the frontend's origin(s).
3. Construct the frontend's `ApiClient` with `credentials: "include"`
   (`new ApiClient({ credentials: "include" })` in `frontend/lib/api-client.ts`) instead
   of relying on the `"same-origin"` default — once, at construction, not per call site.
4. Nothing else to add for CSRF itself: `frontend/lib/api-client.ts` already reads the
   `csrftoken` cookie and sends it as `X-CSRFToken` on unsafe methods whenever
   `credentials !== "omit"`. This works specifically because `CSRF_COOKIE_HTTPONLY = False`
   in `backend/config/settings.py` keeps that cookie JS-readable — don't flip that back to
   `True`, it would silently break every write request.

See `APP-DESIGN.md` §12's frontend security checklist for the cross-reference: an app's
own frontend package must rely on this host-level handling rather than inventing its own
token storage.

## 4. Toolchain, Dependencies & Environment Strategy

### 4.1 `uv` is the only Python package manager

One tool, one lockfile, one install command — in local dev, in Docker, in CI, and on the production server. `requirements.txt` does not exist in this scaffold. The reasons this matters more here than in a typical project:

- Installed app packages resolve from PyPI/npm version ranges (`INTEGRATION-GUIDE.md` §2). `uv.lock`/`package-lock.json` pin those to an exact resolved version and hash, so "we're on v1.4.2" means the same bytes everywhere. A `requirements.txt` line with no lockfile does not guarantee that.
- All apps resolve into **one shared environment** (see `APP-DESIGN.md` §1.1). A real resolver that fails loudly on a conflict is worth a great deal compared to `pip`'s first-wins-then-breaks-at-runtime behavior.
- Dependency groups (PEP 735) keep test/lint tooling out of production images with a single `--no-default-groups` flag, instead of a second requirements file that drifts. (Not `--no-dev` — see §4.2's note on why that flag alone is not enough.)

### 4.2 `backend/pyproject.toml`

```toml
[project]
name = "my-client-project"
version = "0.1.0"
requires-python = ">=3.14"           # a HOST may pin tightly; app packages must not (§APP 1.1)

dependencies = [
    # ---- platform: the host decides the exact versions everyone runs against
    "django>=6.0,<6.1",
    "djangorestframework>=3.15,<4.0",
    "drf-spectacular>=0.27,<1.0",
    "django-cors-headers>=4.6,<5.0",
    "django-jazzmin>=3.0,<4.0",
    "django-celery-beat>=2.7,<3.0",
    "celery[redis]>=5.4,<6.0",
    "psycopg[binary]>=3.2,<4.0",
    "python-decouple>=3.8,<4.0",
    "whitenoise>=6.8,<7.0",
    "uvicorn[standard]>=0.34,<1.0",
    # Deliberately redundant with hjtdev-appkit[crypto]'s own `cryptography` dependency below:
    # tools/crypto.py wraps appkit.crypto.Cipher rather than importing `cryptography`
    # directly, but FERNET_KEY is a first-class, always-required env var (config/settings.py)
    # and shouldn't depend on an app's extras selection to keep working.
    "cryptography>=50,<51",
    "structlog>=25,<26",
    "sentry-sdk[django,celery]>=2.20,<3.0",
    # ---- installed app packages get appended here by `uv add`, one line each
    "hjtdev-appkit[crypto]>=2.0,<3.0",
]

[dependency-groups]
dev = [
    "ruff>=0.12",
    "mypy>=1.14",
    "django-stubs[compatible-mypy]>=5.1",
    "djangorestframework-stubs>=3.15",
    "pre-commit>=4.0",
    "django-debug-toolbar>=5.0",
    "django-extensions>=3.2",        # shell_plus, show_urls
]
test = [
    "pytest>=8.3",
    "pytest-django>=4.9",
    "pytest-cov>=6.0",
    "pytest-xdist>=3.6",
    "factory-boy>=3.3",              # needed to use installed apps' factories, APP-DESIGN §7.3
    "freezegun>=1.5",
]

[tool.uv]
default-groups = ["dev", "test"]
```

Both groups are the right default for local `uv sync`. It's a trap in Docker, though:
`uv sync --no-dev` is only an alias for `--no-group dev` — with `default-groups` set to both,
that flag leaves `test` (pytest, pytest-django, factory-boy, freezegun) installed in what's
meant to be the production image. `backend/Dockerfile.prod`'s builder stage uses
`--no-default-groups` instead, which disables every default group regardless of what's in
the list. See §8.1 for the Dockerfile block.

```toml
# Uncomment ONE of these blocks while developing an app package against this project.
# Swap it back out before committing — see INTEGRATION-GUIDE.md §7.
# [tool.uv.sources]
# notifications-app = { path = "../notifications-app/backend", editable = true }
```

Ruff, mypy, pytest and coverage config live in this same file — see §5. The commented local-checkout block is load-bearing documentation: it's the sanctioned way to point a host at a local app checkout, and having it present-but-commented is what stops someone inventing a worse method. There is no `[tool.uv.sources]` entry for `appkit` itself — `hjtdev-appkit` is published to PyPI, so it resolves transitively like any other dependency (`INTEGRATION-GUIDE.md` §2).

**Extras: this scaffold takes `hjtdev-appkit[crypto]`, not `hjtdev-appkit[images]`.** The scaffold ships `FERNET_KEY` and `tools/crypto.py` — exactly the case the `crypto` extra exists for (`appkit.crypto.Cipher`/`generate_key`). It accepts no file uploads of its own, so `appkit.files.validate_image`'s raster-format checks (the `images` extra) have nothing to validate here; an app that accepts uploads declares `appkit[images]` itself.

### 4.3 Settings & environment

`config/settings.py` is a single, standard Django settings file — no settings package, no composer, no filesystem scanning. Values come from `.env` via `python-decouple`:

```python
from decouple import Csv, config

DEBUG = config("DEBUG", default=False, cast=bool)
SECRET_KEY = config("SECRET_KEY")                       # no default — fail loudly
ALLOWED_HOSTS = config("ALLOWED_HOSTS", cast=Csv())
FERNET_KEY = config("FERNET_KEY")
SENTRY_DSN = config("SENTRY_DSN", default="")

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": config("POSTGRES_DB"),
        "USER": config("POSTGRES_USER"),
        "PASSWORD": config("POSTGRES_PASSWORD"),
        "HOST": config("POSTGRES_HOST", default="db"),
        "PORT": config("POSTGRES_PORT", default="5432"),
        "CONN_MAX_AGE": config("CONN_MAX_AGE", default=60, cast=int),
    }
}

CACHES = {"default": {"BACKEND": "django.core.cache.backends.redis.RedisCache",
                      "LOCATION": config("REDIS_URL")}}

REST_FRAMEWORK = {
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "DEFAULT_THROTTLE_CLASSES": ["rest_framework.throttling.ScopedRateThrottle"],
    "DEFAULT_THROTTLE_RATES": {},     # app installs add their own scopes here
}

INSTALLED_APPS = [
    # jazzmin MUST precede django.contrib.admin — it overrides the admin templates via
    # Django's app-directories loader, which resolves to the first match in this list.
    # Reversed, the admin still renders, just silently unthemed, with nothing to catch it.
    "jazzmin",
    "django.contrib.admin",
    "rest_framework",
    "drf_spectacular",
    "corsheaders",
    "django_celery_beat",
    "core",
    # ---- installed app packages get added here, one line each, per their own README
]

# Env-driven, defaulting to "secure unless DEBUG says otherwise" — SECURE_HSTS_SECONDS below
# is the one exception that does NOT inherit that default; see its own comment for why.
_SECURE_DEFAULT = not DEBUG
SECURE_SSL_REDIRECT = config("SECURE_SSL_REDIRECT", default=_SECURE_DEFAULT, cast=bool)
SESSION_COOKIE_SECURE = config("SESSION_COOKIE_SECURE", default=_SECURE_DEFAULT, cast=bool)
CSRF_COOKIE_SECURE = config("CSRF_COOKIE_SECURE", default=_SECURE_DEFAULT, cast=bool)
# Defaults to 0 in every environment, including prod: a year of HSTS is effectively
# irreversible for the domain and every subdomain, so turning it on is a deliberate,
# explicit act (backend/.env.prod.example sets 31536000), never an inherited default.
SECURE_HSTS_SECONDS = config("SECURE_HSTS_SECONDS", default=0, cast=int)
SECURE_HSTS_INCLUDE_SUBDOMAINS = SECURE_HSTS_SECONDS > 0
SECURE_HSTS_PRELOAD = SECURE_HSTS_SECONDS > 0
# Only trust X-Forwarded-Proto when we know a proxy sits in front — trusting it
# unconditionally is a spoofing vector the moment the container is reachable directly.
TRUST_PROXY_SSL_HEADER = config("TRUST_PROXY_SSL_HEADER", default=_SECURE_DEFAULT, cast=bool)
if TRUST_PROXY_SSL_HEADER:
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SESSION_COOKIE_HTTPONLY = True
CSRF_COOKIE_HTTPONLY = False  # must stay JS-readable — the Next.js frontend sends it as a header
X_FRAME_OPTIONS = "DENY"
SECURE_CONTENT_TYPE_NOSNIFF = True

LOGGING = build_logging_config(debug=DEBUG)   # from config/logging.py, see §3
```

**Startup validation is worth the twenty lines it costs.** Add a Django system check (or a short block at the end of `settings.py`) asserting that, when `DEBUG` is off: `SECRET_KEY` isn't the example value, `ALLOWED_HOSTS` isn't empty or `["*"]`, and every `.env` key the installed apps declared as required is actually set. A misconfigured production deploy that boots and *then* misbehaves costs far more than one that refuses to boot.

**Installed app packages are configured by copy-pasting the block from that app's own `README.md`** into this file — `INSTALLED_APPS`, `MIDDLEWARE`, and `REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"]` entries, plus adding any required keys to `.env`/`.env.example`. There's no dynamic merge step; the full protocol is in `INTEGRATION-GUIDE.md` §2, and it's the same protocol whether a human or an AI agent is doing the wiring.

### 4.4 Env file inventory

Five `.env` files, each with a tracked `.example`, and a clear rule about which is which:

| File | Scope | Committed? |
|---|---|---|
| `.env` | Compose-level interpolation only — `PROJECT_NAME`, host ports | No (`.env.example` is) |
| `.env.prod` | Same scope, production values (`PROJECT_NAME`, `NEXT_PUBLIC_API_URL`, host ports, `UVICORN_WORKERS`, `UVICORN_FORWARDED_ALLOW_IPS`) — required by `docker-compose.prod.yml`'s `PROJECT_NAME:?` guard and passed via `--env-file` (§9) | No — **lives only on the server**, never synced |
| `backend/.env` | Django dev settings, DB creds, Redis URL, app package keys | No (`.env.example` is) |
| `backend/.env.prod` | Same keys, production values | No — **lives only on the server**, never synced |
| `frontend/.env.local` | `NEXT_PUBLIC_API_URL` and friends | No |

There is deliberately **no** `frontend/.env.prod` — `frontend/Dockerfile.prod` takes `NEXT_PUBLIC_API_URL` as a build **ARG** sourced from the root `.env.prod`, not a runtime env file, because `NEXT_PUBLIC_*` is inlined into the client bundle at build time.

The "lives only on the server" rule for `.env.prod` files is enforced by `deploy-prod.sh`'s rsync excludes (§9) and is worth keeping strict: the moment production secrets exist on a developer laptop, they exist in that laptop's backups.

## 5. Code Quality & Testing Setup

The scaffold ships with all of this configured, so a new project starts with the guardrails rather than acquiring them later.

### 5.1 Lint, format, type-check

Same toolchain as the app packages (`APP-DESIGN.md` §3), configured in `backend/pyproject.toml`, plus one host-specific addition worth calling out:

**This table ships commented out.** The scaffold contains no project-specific content, so it can't name apps a project may never install — and a partially-populated list reads as authoritative when it isn't. Ship the `per-file-ignores` block live (it's app-agnostic and needed from day one) and the `banned-api` entries as commented examples; `INTEGRATION-GUIDE.md` §2 step 10 is what adds a real line per installed app. `appkit` (`APP-DESIGN.md` §1.1) never gets one — it's a declared dependency every app is expected to import, not a sibling app this table exists to keep out.

```toml
[tool.ruff.lint.flake8-tidy-imports.banned-api]
# Machine-enforces the mediator rule: only core/ and config/ may import app packages.
# Add one line per installed app — INTEGRATION-GUIDE.md §2 step 10 makes this a wiring step.
# Do NOT add appkit here — every app is expected to import it, see APP-DESIGN.md §1.1.
"notifications_app".msg = "Import app packages only from core/ or config/ — INTEGRATION-GUIDE.md §4"
"payments_app".msg = "Import app packages only from core/ or config/ — INTEGRATION-GUIDE.md §4"

[tool.ruff.lint.per-file-ignores]
"core/**" = ["TID251"]       # core/ is the mediator — it's ALLOWED to know two apps exist
"config/**" = ["TID251"]     # settings.py/urls.py reference app modules by design
"*/migrations/*" = ["E501", "RUF012"]
```

This turns the "zero direct imports between two app packages" checklist item in `INTEGRATION-GUIDE.md` §9 from a grep somebody has to remember into a lint error somebody cannot merge past. It's the single highest-leverage config line in this scaffold.

Frontend: ESLint (`next/core-web-vitals` + `@typescript-eslint`), Prettier, and `tsc --noEmit` in CI. `tsconfig.json` sets `"strict": true` and, ideally, `"noUncheckedIndexedAccess": true`.

`.pre-commit-config.yaml` uses **`repo: local` hooks with `language: system`** for ruff, ruff-format, mypy, eslint and prettier, invoked through `uv run` / `npx` so they resolve from `uv.lock` and `package-lock.json`. Mirror-based hooks with a pinned `rev` are wrong for these: mypy here is `strict` with `mypy_django_plugin` and a `django_settings_module`, so it needs Django and the whole backend importable, which pre-commit's isolated venv doesn't provide — and a pinned `rev` means pre-commit and CI can run two different formatter versions. Only genuinely environment-independent hooks stay as pinned mirrors: `check-merge-conflict`, `end-of-file-fixer`, `trailing-whitespace`, `check-added-large-files`, `detect-private-key`, `check-yaml`, `check-toml`. Add the factories grep from §5.2 as a local hook too. `uv run --directory backend pre-commit install` is step 6 of the bootstrap in §10.

### 5.2 pytest configuration & conftest hierarchy

```toml
[tool.pytest.ini_options]
DJANGO_SETTINGS_MODULE = "config.settings"
pythonpath = ["."]
testpaths = ["core/tests", "config/tests", "tools/tests"]
python_files = ["test_*.py"]
addopts = """
  -ra --strict-markers --strict-config -p appkit.testing
  --cov=core --cov=tools --cov=config
  --cov-report=term-missing --cov-fail-under=80
"""
markers = [
    "slow: excluded from the default run, opt in with -m slow",
    "integration: crosses a real DB/broker boundary rather than mocking it",
]
filterwarnings = ["error::DeprecationWarning"]
```

**`testpaths` deliberately excludes installed app packages.** An app's own suite is its own repo's CI gate (`APP-DESIGN.md` §10); re-running it here would test third-party code you can't fix from this repo and would slow every local run. What this project tests is *its own* code — `core/`, `tools/`, `config/` — which is exactly the code no app's test suite covers.

**`-p appkit.testing` is enabled scaffold-wide**, not left for each installed app to opt into separately. appkit's own plugin is opt-in by design (its README: auto-loading would inject its fixtures into every consuming app's namespace whether asked for or not) — but at the *host* level that reasoning doesn't apply, since the host is the one place already reading and writing `core/tests/conftest.py`/`backend/conftest.py` directly. Confirmed empirically before enabling it: every fixture the plugin registers (`appkit_api_client`, `appkit_user`, `appkit_admin_user`, `appkit_auth_client`, `appkit_admin_client`, `appkit_frozen_request_id`, `appkit_clear_cache`) is a lazy `@pytest.fixture` — nothing executes at plugin-load time, so it collects cleanly even in a fresh scaffold with no auth app installed and no custom user model. `appkit_user`/`appkit_admin_user` build through `get_user_model().USERNAME_FIELD` reflectively, so they work against the scaffold's default `django.contrib.auth` user today and against a future auth app's custom user model with no changes here. Measured load-cost delta running this suite with and without the flag: noise-level (~7.8s either way over three runs each) — not a reason to reconsider.

Fixture hierarchy:

```
backend/conftest.py                # empty — see its own docstring; use appkit_* fixtures
backend/core/tests/conftest.py     # cross-app fixtures — a seeded cart + payment, etc.
```

`backend/conftest.py` used to define `api_client`/`user`/`admin_user`/`auth_client` directly; those were deleted in the appkit v1.0.0 integration in favor of the `appkit_`-prefixed equivalents above. Two reasons beyond "don't maintain two copies of the same fixture": appkit's versions are reflective (work against any user model, not a hardcoded `username=` call), and the scaffold's own `admin_user` collided by name with a fixture pytest-django ships natively — verified directly, pytest-django's version wins that collision **silently**, the exact hazard appkit's `appkit_` prefix exists to prevent. Keeping a same-named local fixture only recreates that ambiguity one file away instead of removing it.

Cross-app fixtures are where installed apps' `factories.py` (`APP-DESIGN.md` §7.3) earns its place:

```python
# backend/core/tests/conftest.py
import pytest
from cart_app.factories import CartFactory, CartItemFactory
from payments_app.factories import PaymentMethodFactory


@pytest.fixture
def checkout_ready_user(appkit_user):
    cart = CartFactory(user=appkit_user)
    CartItemFactory.create_batch(3, cart=cart)
    PaymentMethodFactory(user=appkit_user, is_default=True)
    return appkit_user
```

Importing another app's factories from `core/tests/` is sanctioned and expected; importing them from `core/services/` or any other production code is a bug.

**This rule can't be enforced with ruff in a host project**, and it's worth understanding why, because the reasoning applies to any future rule of this shape. `banned-api` violations all report as `TID251`, and `per-file-ignores` disables a rule *code* for a path. Since `core/**` must already ignore `TID251` (production `core/` legitimately imports app packages — that's its purpose), any factories entry in `banned-api` is silently disabled throughout `core/`, including the production code you wanted to catch. There's no way to re-enable a rule for a subpath. So enforce it with grep instead, in pre-commit and in CI:

```bash
# fails if production core/ imports factories; core/tests/ is fine
! grep -rn '\.factories' backend/core --include='*.py' | grep -v '/tests/'
```

Note this asymmetry with app packages: in an app repo the same rule *does* work via ruff, because its test tree lives outside `src/` and can be cleanly exempted (`APP-DESIGN.md` §3.1). The host's problem is that `core/` and `core/tests/` share one subtree.

### 5.3 Tests run on Postgres

`docker-compose.test.yml` provides an ephemeral Postgres + Redis on non-default ports, so a test run never collides with the dev stack:

```yaml
services:
  test-db:
    image: postgres:17-alpine
    environment:
      POSTGRES_DB: test_db
      POSTGRES_USER: postgres
      POSTGRES_PASSWORD: postgres
    ports: ["55432:5432"]
    tmpfs: /var/lib/postgresql/data     # RAM-backed: meaningfully faster, nothing to clean up
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U postgres"]
      interval: 5s
      timeout: 3s
      retries: 10
  test-redis:
    image: redis:7-alpine
    ports: ["56379:6379"]
    # `up -d --wait` only blocks on services that declare a healthcheck — without one,
    # test-redis could still be starting when pytest connects.
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 5s
      timeout: 3s
      retries: 10
```

```make
test:
	docker compose -f docker-compose.test.yml up -d --wait
	cd backend && POSTGRES_HOST=localhost POSTGRES_PORT=55432 \
	  POSTGRES_DB=test_db POSTGRES_USER=postgres POSTGRES_PASSWORD=postgres \
	  REDIS_URL=redis://localhost:56379/0 \
	  uv run pytest -n auto -m "not slow"
	docker compose -f docker-compose.test.yml down
```

The extra `POSTGRES_DB`/`POSTGRES_USER`/`POSTGRES_PASSWORD`/`REDIS_URL` exports above are
required, not optional: without them the suite falls back to `backend/.env`'s dev credentials
and `redis://redis:6379/0`, neither of which exists against the `test-db`/`test-redis`
containers this target just started.

`--reuse-db` (pytest-django) is worth adding to the local loop once migrations stabilize; CI always builds fresh.

### 5.4 What the host project's tests must cover

Everything in `core/` is custom, project-owned code that no app's test suite covers — because no app knows `core/` exists. Concretely:

- **Signal receivers** — fire the signal directly and assert the receiver's effect, rather than driving a full request cycle. See `INTEGRATION-GUIDE.md` §4 for the worked example.
- **`core/services/` orchestrators** — call them as plain functions against a test DB; assert both the return value and the side effects.
- **`core/views/` overrides** — `APIClient`, status codes, response shape.
- **`config/` wiring smoke tests** — one test asserting `/api/schema/` returns 200 and contains every mounted app's tag, and one asserting every scope referenced by a `throttle_scope` in the codebase exists in `DEFAULT_THROTTLE_RATES`. These two catch the most common integration mistakes in this whole architecture, and they cost about fifteen lines.

## 6. Inter-App Integration Layer (`core/`)

Installed app packages must stay 100% decoupled from one another — no app ever imports another app. Anything that connects two apps (payments completing and triggering a notification, checkout reading the cart) is wired in `backend/core/`:

- **`core/signals.py`** — receivers that listen for one app's Django signal and call another app's service method in response. Fire-and-forget, event-driven.
- **`core/services/`** — orchestration functions for workflows that need a direct, synchronous composition of multiple apps' own `services.py` interfaces (e.g. a checkout flow).

`core` is registered in `INSTALLED_APPS` with its own `AppConfig`, whose `ready()` imports `core/signals.py` so every receiver connects at startup. Full worked examples of both patterns live in `INTEGRATION-GUIDE.md` §4 — the short version is: apps expose events and callables, `core/` is the only code allowed to know two apps exist at once.

**A receiver that does real work belongs in a task, not in the receiver.** A signal receiver runs synchronously inside the sender's transaction. If the work is slow or can fail independently (sending an email, calling a payment provider), the receiver should enqueue a Celery task and return — and it should enqueue with `transaction.on_commit(...)` so the task never runs against a transaction that later rolls back. This is the most common source of "the notification fired for a payment that didn't actually complete."

Periodic tasks follow the same "app recommends, host wires in" pattern rather than auto-registering: an app's `README.md` documents any schedule it needs (`APP-DESIGN.md` §8), but nothing about installing the app creates the schedule automatically. The host explicitly creates the corresponding `django_celery_beat.models.PeriodicTask` entry — via Django admin, or better, a data migration in `core/` so it's reproducible and code-reviewed rather than clicked into a production admin panel once and forgotten. That keeps the actual beat schedule project-owned and inspectable in one place.

## 7. Continuous Integration

The host project's CI is smaller than an app package's — it doesn't build wheels or check version lockstep — but it exists for the same reason: the checklists in `INTEGRATION-GUIDE.md` §9 shouldn't depend on a human remembering them.

```yaml
# .github/workflows/ci.yml
#
# Requires ZERO configured GitHub repository secrets — a freshly cloned project (and every
# fork PR) goes green on the first push. SECRET_KEY and FERNET_KEY are generated fresh
# inside backend-tests rather than read from secrets.*: a value committed to this repo, even
# in a workflow file, is a value someone eventually copies into a real .env, and this
# scaffold is copied into every future project. App package repos are
# public, so installing one never needs a secret either.
name: CI
on:
  push: { branches: [main] }
  pull_request:

env:
  # PYTHON_VERSION is deliberately not declared here: the root .python-version is the single
  # source of truth and astral-sh/setup-uv already reads it — a second declaration is a
  # second place the version could drift.
  NODE_VERSION: "24"
  # Tracks the toolchain that writes backend/uv.lock (uv 0.11.19, lockfile revision 3) — see
  # CLAUDE.md's pinned-versions table and backend/Dockerfile.prod. `uv sync --locked` refuses
  # a lockfile revision newer than it supports, so this pin is not cosmetic.
  UV_VERSION: "0.11.19"

jobs:
  backend-quality:
    runs-on: ubuntu-latest
    env:
      # mypy's django-stubs plugin calls django.setup() to introspect models, which imports
      # config/settings.py — every decouple.config(...) call with no default (SECRET_KEY,
      # ALLOWED_HOSTS, FERNET_KEY, POSTGRES_*, REDIS_URL) raises at import time if unset, and
      # this job never connects to a real DB/cache, so these are placeholder literals, not
      # real credentials.
      SECRET_KEY: mypy-django-plugin-needs-a-value-not-a-real-secret
      ALLOWED_HOSTS: localhost
      FERNET_KEY: mypy-only-placeholder-not-a-real-fernet-key
      POSTGRES_DB: mypy
      POSTGRES_USER: mypy
      POSTGRES_PASSWORD: mypy
      REDIS_URL: redis://localhost:6379/0
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v5
        with:
          version: ${{ env.UV_VERSION }}
          enable-cache: true
          cache-dependency-glob: backend/uv.lock
      - run: uv sync --locked
        working-directory: backend
      # --locked is the point: it FAILS if pyproject.toml and uv.lock disagree, which is
      # how a hand-edited dependency line without a re-lock gets caught. Plain `uv sync`,
      # not `--no-default-groups` — this job needs the dev and test tool groups.
      - run: uv run ruff check --output-format=github .
        working-directory: backend
      - run: uv run ruff format --check .
        working-directory: backend
      - run: uv run mypy .
        working-directory: backend

  backend-tests:
    runs-on: ubuntu-latest
    services:
      postgres:
        # services: does not expand the env: context — this tag must stay a literal in step
        # with CLAUDE.md's pinned-versions table (Postgres 17).
        image: postgres:17-alpine
        env: { POSTGRES_DB: test_db, POSTGRES_USER: postgres, POSTGRES_PASSWORD: postgres }
        options: >-
          --health-cmd pg_isready --health-interval 10s
          --health-timeout 5s --health-retries 5
        ports: ["5432:5432"]
      redis:
        image: redis:7-alpine
        options: >-
          --health-cmd "redis-cli ping" --health-interval 10s
          --health-timeout 5s --health-retries 5
        ports: ["6379:6379"]
    env:
      POSTGRES_HOST: localhost
      POSTGRES_DB: test_db
      POSTGRES_USER: postgres
      POSTGRES_PASSWORD: postgres
      REDIS_URL: redis://localhost:6379/0
      ALLOWED_HOSTS: localhost
      DEBUG: "False"
      # Without this, `check --deploy --fail-level WARNING` fails on security.W004. The app
      # itself never defaults this to non-zero (§4.3) — a year of HSTS is effectively
      # irreversible, so it's set explicitly here rather than inherited.
      SECURE_HSTS_SECONDS: "31536000"
      # locmem, not console/smtp: config/checks.py's config.E004 rejects an empty or
      # still-default (`mailpit`) EMAIL_HOST once DEBUG is off, and locmem is the correct
      # backend for a test run regardless — no message should leave the process at all.
      EMAIL_BACKEND: django.core.mail.backends.locmem.EmailBackend
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v5
        with:
          version: ${{ env.UV_VERSION }}
          enable-cache: true
          cache-dependency-glob: backend/uv.lock
      - run: uv sync --locked
        working-directory: backend
      - name: Generate ephemeral CI keys
        # SECRET_KEY and FERNET_KEY must NOT be literals in this file — see the workflow's
        # top comment. Generated with the runner's system python3 (stdlib only), before any
        # step imports Django settings. A short SECRET_KEY trips security.W009 in the
        # deployment check below, which is why token_urlsafe(64) is used rather than a
        # shorter, "obviously fake" literal.
        run: |
          echo "SECRET_KEY=$(python3 -c 'import secrets; print(secrets.token_urlsafe(64))')" >> "$GITHUB_ENV"
          echo "FERNET_KEY=$(python3 -c 'import base64, os; print(base64.urlsafe_b64encode(os.urandom(32)).decode())')" >> "$GITHUB_ENV"
      - name: Missing migrations check
        run: uv run python manage.py makemigrations --check --dry-run
        working-directory: backend
      - name: Django deployment checks
        run: uv run python manage.py check --deploy --fail-level WARNING
        working-directory: backend
      - run: uv run pytest -n auto
        working-directory: backend
        env:
          # Job-level DEBUG=False makes SECURE_SSL_REDIRECT default to True (config/settings.py's
          # _SECURE_DEFAULT = not DEBUG) — correct for the deploy check above, but Django's test
          # client makes plain-HTTP requests, so every view under SecurityMiddleware 301-redirects
          # instead of returning the status the test asserts. The suite tests business logic
          # (db/cache down -> 503, schema 200), not TLS-redirect enforcement, so this is scoped to
          # only the pytest step — the deployment check above still runs under the strict default.
          SECURE_SSL_REDIRECT: "False"

  frontend:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: ${{ env.NODE_VERSION }}
          cache: npm
          cache-dependency-path: frontend/package-lock.json
      - run: npm ci
        working-directory: frontend
      - run: npx tsc --noEmit
        working-directory: frontend
      - run: npm run lint
        working-directory: frontend
      - run: npm run format:check
        working-directory: frontend
        # Backend enforces formatting with `ruff format --check` above; without this step
        # prettier was only enforced by pre-commit, which is opt-in per clone and therefore
        # not a real gate.
      - run: npm run test -- --run
        working-directory: frontend
      - run: npm run build
        working-directory: frontend
        env: { NEXT_PUBLIC_API_URL: http://localhost:8000 }

  docker-build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: docker/setup-buildx-action@v3
      - name: Build production images (proves the prod path still builds)
        run: |
          docker buildx build -f backend/Dockerfile.prod backend --load -t app-backend:ci
          docker buildx build -f frontend/Dockerfile.prod frontend --load -t app-frontend:ci \
            --build-arg NEXT_PUBLIC_API_URL=http://localhost:8000
      - name: Smoke-test the backend image boots
        run: |
          docker run --rm app-backend:ci python -c "import django; print(django.get_version())"

  security-audit:
    runs-on: ubuntu-latest
    continue-on-error: true       # advisory until the noise level is known; then promote
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v5
        with:
          version: ${{ env.UV_VERSION }}
      - name: Audit backend dependencies
        # --no-default-groups, NOT --no-dev: backend/pyproject.toml sets
        # [tool.uv] default-groups = ["dev", "test"], and --no-dev is only an alias for
        # --no-group dev — it would leave pytest/factory-boy/freezegun in the audited set.
        # --locked fails loudly on a stale lockfile instead of silently auditing last week's
        # dependencies. --no-deps on pip-audit's side because the export is already fully
        # resolved, so re-resolving would be redundant work.
        #
        # --no-hashes: found empirically on a real run — with hashes present, pip-audit's
        # internal `pip install --dry-run --report` switches pip into hash-checking mode,
        # and for at least one wheel (psycopg-binary 3.3.4's cp312 manylinux2014_x86_64
        # build) the hash uv.lock recorded does not match the file real PyPI currently
        # serves (confirmed against PyPI's own JSON API — PyPI's copy is the one uv's own
        # install already trusts via `uv sync --locked` elsewhere in this workflow). Hash
        # integrity of the resolved set is already uv's job, not pip-audit's; this job only
        # needs versions to check against the vulnerability database.
        #
        # `uvx --python "$(cat ../.python-version)"` is still required: `uvx` builds
        # pip-audit's own ephemeral tool environment independently of any project context, so
        # it does NOT walk up to this repo's `.python-version` the way `uv run`/`uv sync` do —
        # it falls back to whatever `python3` is first on the runner's PATH. GitHub's Ubuntu
        # runner defaults to 3.12, and pip-audit's internal `pip install --dry-run --report`
        # (which needs to actually resolve hjtdev-appkit's `requires-python = ">=3.13"`) fails
        # outright under it before a single dependency is audited — confirmed by a real CI
        # failure when this pin was first dropped. A local rerun of the bare command can pass
        # even without this flag if the local machine's own default `python3` happens to
        # already be ≥3.13 — that's an environment coincidence, not proof the pin is
        # unnecessary.
        run: |
          uvx --python "$(cat ../.python-version)" pip-audit --no-deps --strict \
            -r <(uv export --locked --no-default-groups --no-hashes --format requirements-txt)
        shell: bash
        working-directory: backend
      - uses: actions/setup-node@v4
        with:
          node-version: ${{ env.NODE_VERSION }}
      - run: npm audit --audit-level=high
        working-directory: frontend
```

**Why `docker-build` is a job and not an afterthought:** in this architecture, installing an app package changes `uv.lock`, which changes what gets baked into the image. A PR that adds an app can pass every test and still produce an image that fails to build (a native dependency needing a system library, a private git ref CI can't reach). Catching that in CI rather than in `deploy-prod.sh` is worth the two minutes.

**Renovate** (`renovate.json`) keeps the pins fresh: `uv.lock`, `package-lock.json`, the Docker base image digests (pinned automatically — `pinDigests: true`, see §8.1), GitHub Action versions, pre-commit `rev`s, and — most importantly for this architecture — the `git+…@vX.Y.Z` app package refs. Group patch/minor/digest into a weekly PR; keep majors separate. A pinned-everything architecture without an update bot doesn't stay pinned, it stays *stale*, which is worse.

**Required vs. advisory status checks:** set `backend-quality`, `backend-tests`, `frontend`, and `docker-build` as required in the branch protection rule for `main`. Leave `security-audit` advisory-only — it already declares `continue-on-error: true` for exactly this reason, but that flag only protects the *workflow run's* overall conclusion, not the individual job's. Confirmed empirically on this repo's first real PR: `gh api .../jobs` reported `security-audit`'s own `conclusion` as `"failure"` — because `pip-audit` correctly found real, unrelated CVEs in a pinned dependency — while the *run's* conclusion was `"success"`. A branch protection rule keys off the individual job's conclusion, so making `security-audit` required would block every PR the moment any dependency anywhere has a known CVE, which is the noisy failure mode `continue-on-error` exists to avoid.

**Required-check names are job names, not job IDs' cosmetic wrapper — they're the same string.** Renaming a job (the `<job_id>:` key, e.g. `backend-quality:`) silently un-requires it: GitHub's branch protection matches on the job's display name, so an old required-check entry just stops finding a match and is quietly ignored rather than erroring. Renaming a job in `ci.yml` must be paired with updating the branch protection rule in the same change.

## 8. Docker & Compose (dev / prod)

Dev and production run from different Dockerfiles and different compose files — dev optimizes for fast iteration (bind-mounted source, migrate-on-boot, hot reload), prod optimizes for reproducibility and security (baked image, non-root, no migrate-on-boot, explicit health-gated rollout). Sharing one Dockerfile between them tends to compromise both.

### 8.1 Dockerfiles

**`.dockerignore` first**, because without it every build ships a stale `.venv` and a 400MB `node_modules` into the context, which is both slow and a real source of "it works in the container because an old artifact is in there":

```gitignore
# backend/.dockerignore
.venv
__pycache__/
*.py[cod]
.pytest_cache
.ruff_cache
.mypy_cache
.env
.env.*
!.env.example
logs/
media/
staticfiles/
.git
```

```gitignore
# frontend/.dockerignore
node_modules
.next
.env.local
.git
coverage
```

**`backend/Dockerfile.prod`** — `uv`-based, multi-stage, non-root, with BuildKit cache mounts so a one-dependency change doesn't re-download the tree:

```dockerfile
# syntax=docker/dockerfile:1.7
FROM python:3.14-slim AS builder

# Pinned to the minor that matches backend/uv.lock's own revision — uv refuses a lockfile
# revision newer than it supports, so this pin must track the toolchain that maintains the
# lock, not float independently of it. See CLAUDE.md's pinned-versions table.
COPY --from=ghcr.io/astral-sh/uv:0.11 /uv /uvx /bin/

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=0
# UV_COMPILE_BYTECODE moves .pyc generation to build time — pure win for container cold starts.
# UV_LINK_MODE=copy is required with cache mounts: uv's default hardlinks point into the
# cache mount, which doesn't exist in the final stage, producing runtime ImportErrors.

WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential libpq-dev pkg-config git \
    && rm -rf /var/lib/apt/lists/*

# Layer 1: dependencies only. Cached until pyproject.toml/uv.lock actually change.
# --no-default-groups, NOT --no-dev: [tool.uv] default-groups (§4.2) is ["dev", "test"],
# and --no-dev is only an alias for --no-group dev — it leaves "test" (pytest and friends)
# installed. See §4.2.
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --locked --no-install-project --no-default-groups --no-editable

# Layer 2: the project itself. Invalidated by any code change, which is fine — it's fast.
COPY . /app
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-default-groups --no-editable

# ------------------------------------------------------------------ runtime
FROM python:3.14-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
        libpq5 postgresql-client curl \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --uid 10001 appuser

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:$PATH"

WORKDIR /app
COPY --from=builder --chown=appuser:appuser /app /app
RUN mkdir -p /app/logs /app/static /app/staticfiles /app/media \
    && chown -R appuser:appuser /app/logs /app/staticfiles /app/media

USER appuser
EXPOSE 8000
# No --workers flag: uvicorn's CLI reads it natively from $UVICORN_WORKERS (click
# auto_envvar_prefix="UVICORN"), so a compose-level `environment: UVICORN_WORKERS: 3`
# is enough — no shell, no entrypoint script needed. --forwarded-allow-ips is set the
# same way, via $UVICORN_FORWARDED_ALLOW_IPS — not hardcoded here as "*", which would
# make uvicorn trust the client-controlled LEFTMOST X-Forwarded-For entry rather than
# nginx's appended one (verified against uvicorn's own ProxyHeadersMiddleware — see §3's
# "three settings describe the same physical proxy-hop count" paragraph).
CMD ["uvicorn", "config.asgi:application", \
     "--host", "0.0.0.0", "--port", "8000", \
     "--proxy-headers"]
```

Notes on the deliberate choices:
- **`git` is installed in the builder only** — every app package publishes to a registry now, so `uv sync` normally never needs it, but the git+subdirectory form documented as the unreleased-commit fallback (`INTEGRATION-GUIDE.md` §2) still resolves through it, and it has no business being in the runtime image.
- **No migrate on boot.** See §9 for why that's a deploy-script step.
- **`--proxy-headers`** matters because prod binds to `127.0.0.1` behind nginx; without it every client IP in your logs is the proxy's. Its companion, `--forwarded-allow-ips`, is deliberately NOT baked into this image — see the CMD comment above and §3.
- **Base image digests are pinned automatically**, not as a manual step: `renovate.json` sets `pinDigests: true`, so Renovate opens a PR converting `python:3.14-slim` (and every other base image in the repo — both frontend Dockerfiles, `ghcr.io/astral-sh/uv:0.11`, the compose service images) to `python:3.14-slim@sha256:…` shortly after this workflow first runs, and keeps the digest current from then on. Reproducibility is the whole point of the prod image; a floating tag quietly undermines it. The trade-off — a base image only gets security patches via a Renovate PR, not silently on rebuild — is acceptable only because Renovate is actually running; a project that disables it should drop the digest pins too, or it sits on a frozen image indefinitely.
- **Worker count** comes from `$UVICORN_WORKERS`, uvicorn's own env var, set per-environment in compose rather than hardcoded — so the same image runs correctly on a 2-core VPS and a 16-core box.

**`backend/Dockerfile`** (dev) — same builder, but keeps dev/test groups and runs the autoreloading server:

```dockerfile
# syntax=docker/dockerfile:1.7
FROM python:3.14-slim
COPY --from=ghcr.io/astral-sh/uv:0.11 /uv /uvx /bin/
# UV_PROJECT_ENVIRONMENT puts the venv OUTSIDE the bind mount — see the .venv gotcha below.
ENV UV_COMPILE_BYTECODE=0 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=0 \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    PYTHONUNBUFFERED=1 PATH="/opt/venv/bin:$PATH"
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential libpq-dev pkg-config git postgresql-client curl \
    && rm -rf /var/lib/apt/lists/*
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --locked --no-install-project
COPY . /app
RUN mkdir -p /app/logs /app/static /app/staticfiles /app/media
EXPOSE 8000
CMD ["sh", "-c", "python manage.py migrate && exec python manage.py runserver 0.0.0.0:8000"]
```

Dev stays single-stage on purpose: with the source bind-mounted, a builder stage buys nothing and costs rebuild time. Dev runs as root deliberately too — bind-mounted files owned by your host user are otherwise unwritable by a container user, which breaks `makemigrations` in the most annoying possible way. That trade is acceptable in dev and unacceptable in prod, which is precisely why they're separate files. The `exec` before `runserver` matters too: without it, `sh` stays PID 1 and `docker compose down` waits out the full stop timeout on every service using this image instead of runserver receiving `SIGTERM` directly.

**One `.venv` gotcha with bind mounts:** if you bind-mount `./backend:/app` and the container's venv is at `/app/.venv`, your host's `.venv` shadows the container's. Either put the container venv outside the mount (`UV_PROJECT_ENVIRONMENT=/opt/venv`) or add an anonymous volume for `/app/.venv` in compose. The scaffold uses the first option, applied above — it's less surprising.

**`frontend/Dockerfile.prod`** — standard Next.js multi-stage, but using `output: "standalone"`:

```dockerfile
# syntax=docker/dockerfile:1.7
FROM node:24-alpine AS deps
WORKDIR /app
COPY package.json package-lock.json ./
RUN --mount=type=cache,target=/root/.npm npm ci

FROM node:24-alpine AS builder
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . .
ARG NEXT_PUBLIC_API_URL
ENV NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL
# NEXT_PUBLIC_* is inlined into the client bundle at BUILD time — it must be a build ARG,
# not a runtime env var. Changing it means rebuilding the image, not restarting it.
ENV NEXT_TELEMETRY_DISABLED=1
RUN npm run build

FROM node:24-alpine AS runner
WORKDIR /app
ENV NODE_ENV=production NEXT_TELEMETRY_DISABLED=1
RUN addgroup -g 10001 nodejs && adduser -S -u 10001 -G nodejs nextjs
COPY --from=builder /app/public ./public
COPY --from=builder --chown=nextjs:nodejs /app/.next/standalone ./
COPY --from=builder --chown=nextjs:nodejs /app/.next/static ./.next/static
USER nextjs
EXPOSE 3000
ENV PORT=3000 HOSTNAME=0.0.0.0
CMD ["node", "server.js"]
```

`output: "standalone"` in `next.config.ts` makes Next trace exactly which `node_modules` files the server actually needs and emit them into `.next/standalone`. Copying that instead of the whole `node_modules` typically takes the runner image from ~1.2GB to ~200MB, and it means a vulnerability in a build-only dependency isn't in your production image at all.

**`frontend/Dockerfile`** (dev) — single-stage, bind-mounted, for the same reason as the backend's dev image:

```dockerfile
# syntax=docker/dockerfile:1.7
FROM node:24-alpine
WORKDIR /app
ENV NEXT_TELEMETRY_DISABLED=1
COPY package.json package-lock.json ./
RUN --mount=type=cache,target=/root/.npm npm ci
COPY . .
EXPOSE 3000
CMD ["npm", "run", "dev", "--", "--hostname", "0.0.0.0", "--port", "3000"]
```

`node_modules` has the same bind-mount-shadowing problem as the backend's `.venv` — `docker-compose.yml` covers it with anonymous volumes over `/app/node_modules` and `/app/.next` rather than an env var, since there's no npm equivalent of `UV_PROJECT_ENVIRONMENT`.

### 8.2 Compose files

`docker-compose.yml` (dev) and `docker-compose.prod.yml` share the same service list — `db`, `redis`, `backend`, `frontend`, `celery`, `celery-beat`, and optionally `flower`/`mailpit`/`umami`/`umami-db` — but differ in what matters:

| | dev (`docker-compose.yml`) | prod (`docker-compose.prod.yml`) |
|---|---|---|
| Build | `Dockerfile` | `Dockerfile.prod` |
| Source | bind-mounted (`./backend:/app`) | baked into the image, no mount |
| Ports | exposed on all interfaces | bound to `127.0.0.1:<port>` — nginx fronts public traffic |
| `backend` command | image `CMD` (migrate + runserver) | image `CMD` (`uvicorn`, no migrate) |
| Dev extras | `debug-toolbar`, `flower`, mailpit | none |
| Optional profiles | `tooling` (`flower`, `mailpit`), `analytics` (`umami`, `umami-db`) | `analytics` only — activated via `COMPOSE_PROFILES=analytics` in `.env.prod`, see `README.md` |
| Resource limits | none | `deploy.resources.limits` per service |
| Log rotation | default | `max-size` / `max-file` per service |
| `restart` | `unless-stopped` | `unless-stopped` |

**Every service that another service depends on for correctness gets a real healthcheck**, and dependents use `condition: service_healthy`, so `celery` never starts racing a `backend` that hasn't booted. The original version of this scaffold only health-checked `backend`; that leaves a stuck Celery worker or a crashed Next.js server invisible, which is exactly the failure that wakes you up at 3am. All six:

```yaml
services:
  db:
    image: postgres:17-alpine
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U $${POSTGRES_USER} -d $${POSTGRES_DB}"]
      interval: 10s
      timeout: 5s
      retries: 5
      start_period: 30s

  redis:
    image: redis:7-alpine
    command: ["redis-server", "--appendonly", "yes"]
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 10s
      timeout: 3s
      retries: 5

  backend:
    container_name: ${PROJECT_NAME}_backend
    healthcheck:
      # 127.0.0.1, not localhost — see the frontend healthcheck note below; this doesn't
      # actually break on the backend image (Debian glibc resolves localhost to 127.0.0.1
      # first), but staying consistent is one fewer thing to remember.
      test: ["CMD", "curl", "-fsS", "http://127.0.0.1:8000/healthz/"]
      interval: 30s
      timeout: 10s
      retries: 5
      start_period: 40s
    depends_on:
      db: { condition: service_healthy }
      redis: { condition: service_healthy }

  celery:
    container_name: ${PROJECT_NAME}_celery
    command: ["celery", "-A", "config", "worker", "-l", "info", "--concurrency", "4"]
    healthcheck:
      test: ["CMD-SHELL", "celery -A config inspect ping -d celery@$$HOSTNAME || exit 1"]
      interval: 60s
      timeout: 20s
      retries: 3
      start_period: 60s
    depends_on:
      backend: { condition: service_healthy }

  celery-beat:
    container_name: ${PROJECT_NAME}_celery_beat
    # --pidfile is required, not decoration: celery beat's own default is no pidfile at
    # all, so the healthcheck below can never pass without it.
    command: ["celery", "-A", "config", "beat", "-l", "info",
              "--scheduler", "django_celery_beat.schedulers:DatabaseScheduler",
              "--pidfile=/tmp/celerybeat.pid"]
    healthcheck:
      test: ["CMD-SHELL", "test -f /tmp/celerybeat.pid && kill -0 $$(cat /tmp/celerybeat.pid)"]
      interval: 60s
      timeout: 10s
      retries: 3
    depends_on:
      backend: { condition: service_healthy }

  frontend:
    container_name: ${PROJECT_NAME}_frontend
    healthcheck:
      # 127.0.0.1, NOT localhost: on Alpine/musl (node:24-alpine), `localhost` resolves to
      # ::1 first and BusyBox wget does not fall back to IPv4, while the Next server binds
      # 0.0.0.0 (IPv4 only) — with `localhost` this service is permanently unhealthy.
      # Verified empirically.
      test: ["CMD", "wget", "--no-verbose", "--tries=1", "--spider",
             "http://127.0.0.1:3000/api/health"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 30s
```

`/healthz/` (in `config/views.py`) should check the things whose failure means "don't send traffic here" — a `SELECT 1` against the DB and a Redis `ping` — and return 503 if either fails. A healthcheck that only proves Python is running will happily report healthy while every request 500s. Keep it unauthenticated, excluded from throttling, and out of the Sentry transaction sample. On failure, log the real exception server-side but never put it in the response body — `db`/`redis` are unreachable-by-name errors that name the internal host (`"failed to resolve host 'db'"`), and an unauthenticated endpoint is exactly the wrong place for that; `_check_database`/`_check_cache` return the generic string `"unavailable"` once `DEBUG` is off, the same DEBUG-gated shape `appkit.exceptions.standard_exception_handler` already uses.

The prod healthcheck must also never trigger `SECURE_SSL_REDIRECT`'s 301 — `curl -f` doesn't fail on a 3xx, so an unhandled redirect would report the container healthy without the view's checks ever running. Rather than exempting `/healthz/` from the redirect at the settings level (which would make it reachable over plaintext from anywhere the path is proxied), the healthcheck itself sends `-H "X-Forwarded-Proto: https"`: `TRUST_PROXY_SSL_HEADER` already defaults `True` in prod, so this makes `request.is_secure()` true exactly the way nginx's real header will for actual traffic — no new bypass, just the same trust path every other request already uses. `backend/.env.prod.example`'s `ALLOWED_HOSTS` must include `127.0.0.1` for the same "never actually reaches the view" reason — `CommonMiddleware` enforces it on every request, healthchecks included. See §9 for why nginx itself must not proxy `/healthz/` to the public internet regardless.

Production-only hardening, per service:

```yaml
  backend:
    # The one healthcheck that differs from dev: the -H flag is what avoids the
    # SECURE_SSL_REDIRECT 301 described above, without a settings-level exemption.
    healthcheck:
      test: ["CMD", "curl", "-fsS", "-H", "X-Forwarded-Proto: https",
             "http://127.0.0.1:8000/healthz/"]
      interval: 30s
      timeout: 10s
      retries: 5
      start_period: 40s
    deploy:
      resources:
        limits: { cpus: "2.0", memory: 2G }
        reservations: { memory: 512M }
    logging:
      driver: json-file
      options: { max-size: "10m", max-file: "5" }
    security_opt: ["no-new-privileges:true"]
    read_only: false      # Django needs /tmp and staticfiles; use tmpfs if you want true RO
```

Without resource limits a runaway container starves everything else on a shared VPS; without log rotation a long-running prod container fills the disk, and a full disk takes Postgres down with it. Both are three lines and both are the kind of thing nobody adds until after it happens once.

**Volumes.** Every service that writes data it can't afford to lose gets a named volume, declared once at the bottom of each compose file:

```yaml
services:
  db:
    volumes: ["pgdata:/var/lib/postgresql/data"]

  redis:
    command: ["redis-server", "--appendonly", "yes"]
    volumes: ["redisdata:/data"]

  backend:            # prod only — see below
    volumes: ["media:/app/media"]

  celery:              # same volume as backend — tasks touching uploads need the same files
    volumes: ["media:/app/media"]

  umami-db:            # only when the analytics profile is active
    volumes: ["umamidata:/var/lib/postgresql/data"]

volumes:
  pgdata:
  redisdata:
  media:               # prod only
  umamidata:
```

Why each one exists:

- **`pgdata`** — the database itself. Without it, every `docker compose down` (dev) or container recreate (prod) wipes Postgres.
- **`redisdata`** — `redis` runs with `--appendonly yes`, which writes an append-only file for durability; without a volume that AOF has nowhere to persist and Redis starts empty on every recreate.
- **`media`** (**prod only**) — `Dockerfile.prod` does `mkdir -p /app/media` inside the image, and prod has no bind mount (source is baked in, §8.1). Without this volume, every `docker compose -f docker-compose.prod.yml up -d --build` — an ordinary deploy — would destroy every user upload: silently, and with nothing in the test suite positioned to catch it. Verified empirically: a file written to `/app/media` and a database row both survive a real `up -d --build` against a running prod-shaped stack; neither does without the corresponding volume. `celery` mounts the same volume — a task touching an upload needs to see the same files the request that queued it saw.
- **`umamidata`** — Umami's own Postgres instance (§3); loses analytics history without it.

Dev needs no `media` volume: `backend`'s bind mount (`./backend:/app`, §8.1) already puts `/app/media` on the host at `backend/media/` (gitignored) — the bind mount *is* the persistence mechanism there, the same way it is for the rest of the source tree. `staticfiles` is deliberately **not** a volume anywhere: a named volume is seeded once and then goes stale across rebuilds, while `collectstatic` (§9 step 6) regenerates it into the container's own layer on every deploy — a volume there would serve last release's CSS after this release's `collectstatic` ran.

**Media is not covered by any backup this scaffold takes.** `deploy-prod.sh`'s rsync excludes `media` (§9 step 2) — uploads live only on the server, are never rsynced from a developer machine, and never travel the other direction either. `pg_dump` (§9 step 5, and `make backup`) captures database rows, not files on disk, so a restored database has upload *records* pointing at files that were never part of the backup. If a project needs uploaded files backed up, that's a separate mechanism (rsync to another host, object storage) that this scaffold does not provide — see §9's restore section.

**Container names come from the root `.env`'s `PROJECT_NAME`** (`container_name: ${PROJECT_NAME}_backend`) rather than being hardcoded — that's what keeps this scaffold copy-paste-safe across projects, and it's what `deploy-prod.sh`'s health-check loop (§9) references directly.

Use compose **profiles** for optional services so `docker compose up` stays lean and `docker compose --profile <name> up` brings the extras. Two profiles exist: `tooling` (`flower`, `mailpit`, `debug-toolbar` sidecars — dev only) and `analytics` (`umami`, `umami-db` — dev *and* prod, §3). `mailpit` (not `mailhog` — MailHog has been unmaintained since 2020; mailpit is its drop-in successor, same 1025/8025 ports) is what `config/settings.py`'s `EMAIL_HOST` default resolves to by service name. `analytics` is the only profile defined in `docker-compose.prod.yml`; a production deploy activates it by setting `COMPOSE_PROFILES=analytics` in the root `.env.prod` rather than passing a `--profile` flag — `deploy-prod.sh` (§9) invokes compose with `--env-file`, and compose reads `COMPOSE_PROFILES` from that file the same way it reads every other key.

## 9. Deployment

Deployment is push-based, not a `git pull` on the server — `deploy-prod.sh` rsyncs the working tree to the target server, then runs the rebuild/rollout remotely over SSH. Configuration for *where* to deploy lives in `deploy/deploy.prod.env` (gitignored; `deploy.prod.env.example` is the tracked template), not in the script:

```bash
# deploy/deploy.prod.env
SERVER_HOST=
SERVER_USER=
SERVER_PATH=/opt/my-client-project
SSH_PORT=22
SSH_KEY_PATH=
```

`deploy-prod.sh`, run from the repo root, does — in order:

1. **Validate** `deploy.prod.env` exists with `SERVER_HOST`/`SERVER_USER`/`SERVER_PATH` set; confirm it's being run from the repo root (checks for `docker-compose.prod.yml`); confirm the working tree is clean, **with no override** — deploying a dirty tree is how "it works on my machine" reaches production literally, and since this script rsyncs the working tree rather than a git ref, a clean tree is the only thing that makes "what commit is production running" answerable afterwards (see the `DEPLOYED_VERSION` history, step 7). Untracked files count as dirty too — an untracked file rsyncs exactly like a tracked one.
   **CI gate**, replacing the original "ideally, that CI is green" (too vague to implement as written): with `gh` authenticated and an `origin` remote configured, look up the current commit's CI run by SHA and fail if it's missing, still running, or didn't conclude `success`/`skipped` — printing the run URL either way. If `gh` is absent, unauthenticated, or there's no `origin`, the check can't run and is skipped with a note (that's the machine's state, not the commit's). `--skip-ci-check` bypasses it entirely.
2. **Rsync** the working tree, excluding everything that shouldn't travel: `.git`, `.idea`/`.vscode`, `__pycache__`, `.venv`, `node_modules`, `.next`, `media`, `.env`/`.env.prod`/`.env.local` (those live only on the server), `deploy/deploy.prod.env`, `.mypy_cache`, `.ruff_cache`, `.pytest_cache`, `staticfiles`, `logs`, `backups` (step 5 writes here on the server; without this exclude, `rsync --delete` from a developer machine with no local `backups/` would wipe the server's own backup history).
3. **On the server, over SSH:** confirm every required `.env.prod` file exists — **root and `backend/` only** (not `frontend/`: `NEXT_PUBLIC_API_URL` is a frontend build **ARG** sourced from the root `.env.prod`, never a runtime env file frontend reads) — and fail loudly rather than deploying with a missing config; then `docker compose -f docker-compose.prod.yml --env-file .env.prod build --pull` and `up -d --remove-orphans`. `--env-file` is mandatory on every compose invocation from here on — without it, compose auto-loads a plain `.env` and `PROJECT_NAME:?` either aborts or silently collides with the dev stack's container names.
4. **Wait for the backend healthcheck** to report healthy (poll `docker inspect --format '{{.State.Health.Status}}'`, bounded retries — fail and dump the last 100 log lines rather than hanging forever).
5. **Back up the database** — unconditional, before migrating, `pg_dump` run inside the `backend` container (which is why `Dockerfile.prod` installs `postgresql-client` in its runtime stage) and gzipped to `$SERVER_PATH/backups/`. `--skip-backup-db` opts out. A destructive migration with no backup is the one failure mode in this list you cannot recover from.
6. **Only once healthy and backed up:** run `migrate --noinput` and `collectstatic --noinput` via `docker compose exec` — deliberately *not* in the container's boot command, so a migration runs once per deploy rather than once per replica or restart.
7. **Verify** every expected container — from `docker compose config --services` (which already accounts for compose profiles, so it never expects a profile-gated service) — is actually `running` (not just that `up -d` returned success) and, now that everything has a healthcheck (§8.2), that each is `healthy` or has no healthcheck at all — dump logs for anything that isn't. **Only once verification passes**, append a line to `$SERVER_PATH/DEPLOYED_VERSION` recording the commit SHA, `git describe`, timestamp, and deployer — the payoff for step 1's strict clean-tree check, and what makes rollback (below) possible. This is an append, not an overwrite: `DEPLOYED_VERSION` accumulates the last 20 deploys that actually passed verification, oldest first. A deploy that fails this step writes nothing — the file is a history of releases that worked, not of releases that were attempted.
8. **Reload nginx**, after `nginx -t` passes. nginx is a **host-level** reverse proxy here, not a compose service — both `backend`'s and `frontend`'s published ports bind `127.0.0.1` (§8.2), so this step runs over SSH with `sudo` (`nginx -t`, then `systemctl reload nginx`) rather than through compose. `SKIP_NGINX_RELOAD=1` skips it (e.g. nginx isn't installed on this host).
9. **`--follow`** optionally tails `docker compose logs -f` after a successful deploy.

Migration ordering: steps 3–6 mean the new code is serving traffic *before* migrations run, which is fine for additive migrations and dangerous for destructive ones. For a single-container deploy the practical rule is: make migrations backward-compatible (add columns nullable, deploy, backfill, then drop in a later release) so there's never a window where running code and the schema disagree. This is said out loud in the script's header comment, because it's the kind of thing that's obvious in principle and forgotten under deadline.

Failing loudly and early (missing env file, unhealthy container, failed nginx test, dirty tree) matters more here than anywhere else in this scaffold — a deploy script's whole job is to be the thing that stops a bad rollout, not the thing that quietly ships one.

**nginx must not expose `/healthz/` publicly.** It's unauthenticated by design (§8.2), reports real infrastructure state (DB/cache reachability), and — unlike every other path — the compose healthcheck reaches it with an `X-Forwarded-Proto: https` header that makes Django skip the HTTPS redirect for that one request. That combination is intentional for the healthcheck's loopback call inside the compose network; it is not something a project's nginx config should ever forward from the public internet. Keep the location block internal-only (`allow` the Docker network, `deny all`, or simply don't proxy the path at all) rather than relying on Django alone to gate it — `config/views.py`'s `healthz()` masks the specific DB/cache error string once `DEBUG` is off, but it still confirms whether the database or cache is reachable, which is more than an anonymous caller on the internet needs to know.

### Restoring a backup

A backup that's never been restored is a file, not a backup. Three places write one — `deploy-prod.sh` step 5 (pre-migrate, on the server), `make backup` (dev), and the `backups` rsync exclude that protects the server's own history from being deleted by a deploy — so restoring needs to be a real, tested path, not something improvised at 3am.

**Dev**: `make restore FILE=backups/<name>.sql.gz` (plain `.sql` also works). It refuses to run unless the dev stack's `db` service is actually up, and refuses outright if it detects `.env.prod` or `backend/.env.prod` anywhere in the checkout — those files live only on the server (§4.4), so their presence means this is a server checkout, not a dev clone, and `make restore` is the wrong tool. It then prints the database name it's about to drop and requires typing that name back before touching anything — not a `y/N`, because a `y/N` gets muscle-memoried through. Internally: `dropdb --if-exists --force`, `createdb`, then the dump streamed through `psql -v ON_ERROR_STOP=1 --single-transaction` — `pg_dump`'s plain output contains no `DROP` statements, so restoring onto a live schema without the drop/create first fails on every object that already exists, and without `ON_ERROR_STOP` + `--single-transaction` a restore that fails partway through leaves a half-populated database that still reports success.

**Server-side** — app containers stopped first, since a backend still writing during a restore produces a database that matches neither the backup nor the pre-restore state:

```bash
cd "$SERVER_PATH"
docker compose -f docker-compose.prod.yml --env-file .env.prod stop backend celery celery-beat

# db stays up — the restore runs inside it
docker compose -f docker-compose.prod.yml --env-file .env.prod exec -T db \
  dropdb --if-exists --force -U "$POSTGRES_USER" "$POSTGRES_DB"
docker compose -f docker-compose.prod.yml --env-file .env.prod exec -T db \
  createdb -U "$POSTGRES_USER" -O "$POSTGRES_USER" "$POSTGRES_DB"
gzip -dc backups/<name>.sql.gz | \
  docker compose -f docker-compose.prod.yml --env-file .env.prod exec -T db \
  psql -v ON_ERROR_STOP=1 --single-transaction -U "$POSTGRES_USER" -d "$POSTGRES_DB"

docker compose -f docker-compose.prod.yml --env-file .env.prod up -d
# wait for backend to report healthy (§9 step 4's own poll loop), then:
docker compose -f docker-compose.prod.yml --env-file .env.prod exec -T backend python manage.py migrate --noinput
```

`migrate` at the end matters even when restoring the most recent backup: it's a no-op if the schema already matches, and the thing that saves you if the backup predates a migration that's already shipped in the code now running.

**Media is not covered by this.** `pg_dump` captures database rows, not files on disk, and `media/` is excluded from the deploy rsync (§8.2, §9 step 2) — uploaded files exist only on the server and travel nowhere. Restoring the database from a backup taken before an upload will leave a row pointing at a file that no longer exists, and there is no scaffold-provided mechanism to prevent or repair that. If a project needs uploaded files backed up, that's a separate mechanism — rsync to another host, object storage with versioning — that **this scaffold does not provide; the operator owns it.**

### Rolling back

`deploy-prod.sh` writes `DEPLOYED_VERSION` (§9 step 7) but nothing reads it automatically — there is deliberately no `--rollback` flag. The script rsyncs the working tree, not a git ref, and refuses to run against a dirty tree with no override (step 1); an automated rollback would have to drive a local `git checkout` of the old commit before it could rsync anything, which makes it the manual procedure below with a wrapper around it — and it still couldn't undo a migration that already ran. Code that only executes during an incident, and can't fully do the one thing it promises, is worse than a written procedure. Roll back by hand:

1. On the server, read `$SERVER_PATH/DEPLOYED_VERSION` — the last line is the current release, the line before it is the rollback target. Cross-check with `docker compose -f docker-compose.prod.yml --env-file .env.prod ps` first: after a deploy that failed verification (§9 step 7), the tree on disk can be newer than the last line recorded, since a failed deploy appends nothing.
2. Locally, on a clean tree: `git checkout <previous-sha>` (detached `HEAD` is correct here — you're deploying a specific commit, not a branch). Stash first if the tree isn't clean; the deploy script's own clean-tree check still applies.
3. Run `deploy/deploy-prod.sh` as normal. `--skip-ci-check` is reasonable here specifically because that commit's CI run already passed once, when it originally shipped.
4. **The schema does not roll back.** Migrations the bad deploy applied stay applied — this is the same constraint the "Migration ordering" note above already describes, and it's why backward-compatible migrations are what actually makes a rollback survivable. If the bad deploy ran a destructive migration, checking out the old code is not enough on its own: restore the pre-migrate backup that step 5 took automatically (`backups/pre-migrate-<timestamp>.sql.gz`) using the procedure above.
5. Return to the tip of your branch (`git checkout -`) once the incident is resolved, so the next normal deploy isn't run from a detached `HEAD`.

## 10. Bootstrapping & Setup Walkthrough

```bash
# 1. Clone the scaffold — frontend/ and backend/ come together, already wired
git clone https://github.com/yourorg/base-scaffold.git my-client-project
cd my-client-project

# 2. Detach from the scaffold's history — from here on, this is just your code
rm -rf .git && git init

# 3. Name the project (drives container names, DB name, and CLAUDE.md's header)
./scripts/rename-project.sh my-client-project     # see §11

# 4. Environment
cp .env.example .env
cp backend/.env.example backend/.env
cp frontend/.env.example frontend/.env.local
python3 -c "import secrets; print(secrets.token_urlsafe(64))"                              # SECRET_KEY
python3 -c "import base64, os; print(base64.urlsafe_b64encode(os.urandom(32)).decode())"   # FERNET_KEY
# stdlib only — cryptography isn't installed until step 5, and its own Fernet.generate_key()
# output is byte-for-byte the same shape as this (32 random bytes, urlsafe-base64), so either
# is a valid key; this form just works before `uv sync` has run.
# paste both into backend/.env, then fill in the DB creds below them.
# (PROJECT_NAME lives in the root .env, not backend/.env — step 3 already set it there.)

# 5. Python + Node dependencies
cd backend && uv sync --locked && cd ..    # --locked proves pyproject.toml and uv.lock agree
cd frontend && npm ci && cd ..

# 6. Hooks
uv run --directory backend pre-commit install

# 7. Bring the stack up
docker compose up --build

# 8. First superuser
docker compose exec backend python manage.py createsuperuser

# 9. Sanity check — visit each in a browser (`open` is macOS-only; Linux: `xdg-open`)
http://localhost:8000/healthz/            # 200
http://localhost:8000/api/schema/swagger-ui/
http://localhost:3000

# 10. Commit — a fresh clone has no tags yet (step 2 deleted .git), so there's no real
# version to put in place of vX.Y.Z; either drop that part or fill in the scaffold
# version/commit you actually cloned from.
git add . && git commit -m "chore: initial commit from base-scaffold"
```

Steps 5–6 are `make install`; step 7 is `make up`; `make check` is the definition of done from
here on (§10.2) — the explicit steps above are what those targets actually run, spelled out
once for a first read.

At this point the project is fully independent. Installing a reusable app package (both halves) follows the protocol in `INTEGRATION-GUIDE.md` §2, and there's no further contact with the base-scaffold repo unless you're deliberately backporting an improvement by hand.

### 10.1 `CLAUDE.md` is generated, not copied blank

`base-scaffold`'s own root `CLAUDE.md` is this repo's authoring instructions — the working agreement and pinned-versions table used to *build* the scaffold. It is never copied into a cloned project and `rename-project.sh` never writes over it. Step 3's `rename-project.sh` instead renders the **host-project variant** out of `CLAUDE.md.template` (the file's other variant, at the bottom, is for an app-package repo — see `APP-DESIGN.md`), fills in `{{PROJECT_NAME}}` and the other placeholders it can know, and writes the result to the clone's `CLAUDE.md`. Keeping it generated rather than hand-written matters because a `CLAUDE.md` with the wrong project name and a stale installed-apps list is worse than none — an agent will trust it. The script guards this write: it only replaces a `CLAUDE.md` that still carries the scaffold's own marker heading, so a second run in an already-renamed project can't clobber edits a human has since made.

### 10.2 `Makefile`

`check` is defined as **parity with `.github/workflows/ci.yml`**: every job/step in CI maps to
a make target, or is named as a deliberate exclusion in the header comment. Any new CI step
must be mirrored here or explicitly documented as excluded — this rule is stated in the
Makefile itself, not just here, so it doesn't rot the next time CI gains a step.

```make
# A thin, memorable interface over the real commands — BASE-DESIGN.md §10.2. Built up phase
# by phase as its prerequisites landed (Phase 3: test: Phase 5: compose-stack targets; Phase 8:
# everything below).
#
# `check` is defined as PARITY WITH .github/workflows/ci.yml: every job/step in CI maps to a
# target below, or is named as a deliberate exclusion. Any new CI step must be mirrored here or
# documented as excluded — that's the rule, not just this phase's intent (docs/BASE-DESIGN.md
# §10.2).
#
#   ci.yml job         step                                   make target
#   -----------         ----                                   -----------
#   backend-quality      uv sync --locked                       install
#                        ruff check .                            lint
#                        ruff format --check .                   lint
#                        mypy .                                   typecheck
#   backend-tests        uv sync --locked                       install
#                        makemigrations --check --dry-run        django-checks
#                        check --deploy --fail-level WARNING     django-checks
#                        pytest -n auto                           test
#   frontend             npm ci                                  install
#                        tsc --noEmit                             typecheck
#                        npm run lint                             lint
#                        npm run format:check                     lint
#                        npm run test -- --run                    test
#                        npm run build                             build
#   docker-build         prod image build + boot smoke test       EXCLUDED — a minutes-long
#                                                                  BuildKit run; `make up` and
#                                                                  `make deploy` already
#                                                                  exercise the same Dockerfiles
#   security-audit       pip-audit / npm audit                    EXCLUDED — a network CVE
#                                                                  lookup, advisory only in CI
#                                                                  (continue-on-error: true,
#                                                                  never a required check)
#
# `uv sync --locked` / `npm ci` are deliberately NOT part of `check` — re-installing on every
# check is slow and, for npm, destructive to node_modules. `make install` is the lock-drift
# gate: run it after touching pyproject.toml/uv.lock or package.json/package-lock.json.
.DEFAULT_GOAL := help
.PHONY: help install up down stop ps logs shell migrate migrations superuser backup \
        lint fmt typecheck django-checks test test-fast build check deploy

help:  ## Show this help
	@grep -E '^[a-z-]+:.*?## ' $(MAKEFILE_LIST) | awk -F':.*?## ' '{printf "  %-14s %s\n", $$1, $$2}'

install:       ## uv sync --locked + npm ci + install pre-commit hooks
	cd backend && uv sync --locked
	cd frontend && npm ci
	uv run --directory backend pre-commit install
	test -f backend/.env || echo "NOTE: backend/.env doesn't exist yet — see README.md step 4."

up:            ## Start the dev stack
	docker compose up --build
down:          ## Stop AND remove the dev stack's containers/network (use `stop` to keep them)
	docker compose down
stop:          ## Stop the dev stack in place — containers/volumes survive, `make up` resumes them
	docker compose stop
ps:            ## Show dev stack container status, including the health column
	docker compose ps
logs:          ## Tail all logs
	docker compose logs -f
shell:         ## Django shell_plus in the backend container
	docker compose exec backend python manage.py shell_plus
migrate:       ## Apply migrations
	docker compose exec backend python manage.py migrate
migrations:    ## Create migrations
	docker compose exec backend python manage.py makemigrations
superuser:     ## Create a superuser
	docker compose exec backend python manage.py createsuperuser
backup:        ## pg_dump the dev database to backups/<PROJECT_NAME>-<timestamp>.sql.gz
	mkdir -p backups
	name=$$(grep -m1 '^PROJECT_NAME=' .env 2>/dev/null | cut -d= -f2); \
	f="backups/$${name:-myproject}-$$(date +%Y%m%d-%H%M%S).sql.gz"; \
	docker compose exec -T db sh -c 'pg_dump -U "$$POSTGRES_USER" "$$POSTGRES_DB"' | gzip -9 > "$$f"; \
	echo "Wrote $$f"

lint:          ## Ruff + ESLint + format checks (ruff format --check, prettier --check) — the CI gate
	cd backend && uv run ruff check . && uv run ruff format --check .
	cd frontend && npm run lint && npm run format:check
fmt:           ## Fix everything lint checks for — the companion fixer, not run by `check`
	cd backend && uv run ruff check --fix . && uv run ruff format .
	cd frontend && npm run format
typecheck:     ## mypy + tsc
	cd backend && uv run mypy .
	cd frontend && npx tsc --noEmit
django-checks: ## makemigrations --check + check --deploy, under a prod-shaped env — no setup needed
	cd backend && \
	SECRET_KEY=$$(python3 -c "import secrets; print(secrets.token_urlsafe(64))") \
	FERNET_KEY=$$(python3 -c "import base64, os; print(base64.urlsafe_b64encode(os.urandom(32)).decode())") \
	DEBUG=False ALLOWED_HOSTS=localhost SECURE_HSTS_SECONDS=31536000 \
	EMAIL_BACKEND=django.core.mail.backends.locmem.EmailBackend \
	sh -c 'uv run python manage.py makemigrations --check --dry-run && uv run python manage.py check --deploy --fail-level WARNING'
test:          ## Full suite (pytest + vitest) against an ephemeral Postgres + Redis — CI parity, what `check` runs
	docker compose -f docker-compose.test.yml up -d --wait
	trap 'docker compose -f docker-compose.test.yml down' EXIT; \
	(cd backend && POSTGRES_HOST=localhost POSTGRES_PORT=55432 \
	  POSTGRES_DB=test_db POSTGRES_USER=postgres POSTGRES_PASSWORD=postgres \
	  REDIS_URL=redis://localhost:56379/0 \
	  DEBUG=False SECURE_SSL_REDIRECT=False \
	  uv run pytest -n auto) && \
	(cd frontend && npm run test -- --run)
test-fast:     ## Backend only, skips slow tests — the inner-loop version of `test`, NOT what `check` runs
	docker compose -f docker-compose.test.yml up -d --wait
	trap 'docker compose -f docker-compose.test.yml down' EXIT; \
	(cd backend && POSTGRES_HOST=localhost POSTGRES_PORT=55432 \
	  POSTGRES_DB=test_db POSTGRES_USER=postgres POSTGRES_PASSWORD=postgres \
	  REDIS_URL=redis://localhost:56379/0 \
	  uv run pytest -n auto -m "not slow")
build:         ## Production frontend build — proves the Next.js build itself still succeeds
	cd frontend && NEXT_PUBLIC_API_URL=http://localhost:8000 npm run build
check: lint typecheck django-checks test build  ## Everything CI gates on, locally — the definition of done (see map above)
deploy:        ## Deploy to production (pass flags via ARGS, e.g. make deploy ARGS=--follow)
	./deploy/deploy-prod.sh $(ARGS)
```

The `check` target is the one that matters: it gives `CLAUDE.md` a single command to name as the definition of done, and it gives a human one command to run before pushing. Its earlier form only ran `lint typecheck test` and never set `DEBUG=False`, so it could pass locally and still fail in CI on the format checks or the deployment checks below; it now actually gates on everything CI does except the two jobs named above as excluded.

## 11. Ecosystem Tooling

Three small pieces of tooling that live *outside* any single project and make the whole ecosystem cheaper to operate. None is strictly necessary on day one; all three pay for themselves by the third project.

### 11.1 `scripts/rename-project.sh` (in the scaffold)

Replaces the placeholder project name (`myproject`) across every file that actually contains it
in one pass. The script derives that file list by grepping the tracked tree rather than
hardcoding it — the original hardcoded list here named `docker-compose*.yml` (which contains no
literal; those files interpolate `${PROJECT_NAME}` from `.env` at compose time) and omitted
`backend/uv.lock`, `frontend/package-lock.json`, `backend/.env.example`, `.env.prod.example`,
and `frontend/app/layout.tsx`'s `metadata.title` — a gap that broke `uv sync --locked`/`npm ci`
in a renamed clone until an empirical test of a fresh clone caught it. In practice this covers
`.env.example`, `.env.prod.example`, `backend/.env.example`, `backend/pyproject.toml`,
`backend/uv.lock`, `frontend/package.json`, `frontend/package-lock.json`, and
`frontend/app/layout.tsx`, plus rendering the host `CLAUDE.md` from `CLAUDE.md.template`
(§10.1). Lockfile edits are line-anchored to the root package's own `name` field, never a blind
substring replace, so a dependency that happens to contain the placeholder can't be corrupted.
Hand-editing this list is a five-minute job that gets done wrong roughly every other time, and
the failure mode (two projects sharing a `PROJECT_NAME`, so their containers collide) is
confusing to diagnose — deriving the list instead of hardcoding it is what keeps this section
from drifting out of sync with the repo again.

### 11.2 `create-app-package` (a separate template repo)

`BASE-DESIGN.md` solves "starting a new project" well. Starting a new *app package* still means hand-building the whole `APP-DESIGN.md` §2 skeleton — the dual-package layout, the README config-block stub, the CI caller workflow, the playground, the pytest settings module. That's exactly the repetitive setup this ecosystem exists to eliminate.

Use `copier` (preferred — it supports updating a generated project when the template improves, which matters as the standard evolves) or a plain `degit`-style template repo plus a script. It prompts for: package name, importable module name, whether it has a frontend half, and the initial `.env`/settings keys, then emits a repo that already passes CI with zero code in it. The first app you generate this way will feel like overkill; the fourth will not.

**`appkit` is app package #1, and it's built by hand — before this template exists.** It has to be: it's the reference the template gets derived from, and it's also the simplest possible instance of the `APP-DESIGN.md` §2 skeleton, since its own `pyproject.toml` declares no app-package dependencies at all (`APP-DESIGN.md` §1.1's exception exists *for* every app that comes after it, not for itself). Build it, ship v1.0.0, then generate the template from it.

App package #2 — the first real app built on top of `appkit` — is also the first genuine test of one app package depending on another: that `uv` actually resolves `appkit` transitively into a host that only declared app #2, that the §1.1 range rule holds up across that boundary rather than just within a single app's own direct dependencies, and that `APP-DESIGN.md` §10.1's `resolution-matrix` CI job exercises `appkit` at both `lowest-direct` and `highest` the same way it does every other dependency. Don't skip verifying this empirically the first time — see `INTEGRATION-GUIDE.md` §2's note on `[tool.uv.sources]` and transitive dependency names for the one part of this that isn't obviously going to work by construction.

### 11.3 An app registry

Once there are more than a handful of app packages, "what already exists that I could reuse here?" has no answer in the current design — and reuse across projects is the entire point of the architecture. A single `APPS.md` (or `apps.json`, if you want tooling to read it) in an org-level meta-repo, listing every app with its latest tag, a one-line description, and its required host settings:

```markdown
| App | Latest | Purpose | Notes |
|---|---|---|---|
| `appkit` | v2.0.1 | Shared cache/mixin/error-envelope helpers + the frontend HttpClient/provider | Every other app depends on this — not itself an installable feature |
| `auth-app` | v3.1.0 | JWT auth, registration, password reset | Every project needs this first |
| `notifications-app` | v1.4.2 | Email/SMS/push delivery + templates | Extras: `[sms]`, `[push]` |
| `payments-app` | v2.1.0 | Stripe charges, refunds, webhooks | Requires `notifications-app` wiring in `core/` |
| `ticketing-app` | v0.4.0 | Support tickets, categories, SLA timers | Uses `contenttypes` for optional links |
```

Keep it updated as the last step of each app's release workflow. It's also the single most useful file to paste into an agent's context when starting a new project, because it turns "build a notification system" into "install the one that already exists."
