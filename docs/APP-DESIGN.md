# APP-DESIGN.md — Reusable App Package Architecture

> **Companion documents:** `BASE-DESIGN.md` (the host scaffold), `INTEGRATION-GUIDE.md` (how a host wires apps in), `CLAUDE-CODE-GUIDE-APP.md` (how to actually build one of these with an AI agent).

## Table of contents

1. [Purpose & Package Contract](#1-purpose--package-contract)
2. [Package Folder Structure](#2-package-folder-structure)
3. [Toolchain, Dependencies & Project Configuration](#3-toolchain-dependencies--project-configuration)
4. [Views, Rate Limiting & API Documentation Standards](#4-views-rate-limiting--api-documentation-standards)
5. [Two Admin Surfaces & Permissions](#5-two-admin-surfaces--permissions)
6. [Inter-App Communication (Signals & Services)](#6-inter-app-communication-signals--services)
7. [Testing Standards](#7-testing-standards)
8. [Documentation Standard (`README.md` Contract)](#8-documentation-standard-readmemd-contract)
9. [Security Checklist](#9-security-checklist)
10. [Continuous Integration](#10-continuous-integration)
11. [Release Workflow](#11-release-workflow)
12. [Frontend SDK Contract](#12-frontend-sdk-contract)

---

## 1. Purpose & Package Contract

A reusable app is a **standalone, versioned Python package** — its own GitHub repo, its own release history, installable into any host project via `uv`. Once installed, it lives in `.venv/lib/.../site-packages` as read-only, third-party code: nothing inside it is ever hand-edited from within a host project. If a host project needs different behavior, that's a new version of the package, or a project-level override/subclass in the host's `core/` layer (see `INTEGRATION-GUIDE.md`) — never a local edit to the installed files.

**Versioning:** every release is tagged `vX.Y.Z` (semantic versioning — breaking changes bump major, additive/back-compatible features bump minor, fixes bump patch). A host project pins the exact tag it depends on:

```bash
uv add "git+https://github.com/yourorg/notifications-app.git@v1.4.2#subdirectory=backend"
```

`uv` records that in the host's `pyproject.toml` and resolves the exact commit hash into the host's `uv.lock`, so `uv sync` reproduces the identical tree on any machine and in CI. Upgrading is changing that one pinned ref and re-syncing — never assume a host project is on the latest version, and never publish a breaking change under a minor/patch bump.

**Full-stack packages.** Every reusable app is a **dual-package monorepo**: a Python/Django half installed into the backend, and a TypeScript/React half installed into the frontend (see §12). Both halves live in the same repo and release under the *same* version tag, so a host is never stuck pairing an old hook against a new API shape or vice versa — see §11 for how a release keeps both in lockstep, and §10 for the CI job that makes a version mismatch fail the build rather than ship.

### 1.1 Dependency declaration rules — permissive ranges, never exact pins

This is the single most important rule in this document that has nothing to do with code structure, because getting it wrong makes apps *un-combinable*.

When a host installs three app packages, `uv` resolves **one shared environment** across the host's own dependencies and every installed app's dependencies. There is no per-app isolation — they all share one `site-packages`. So if `payments-app` declares `djangorestframework==3.15.0` and `notifications-app` declares `djangorestframework==3.14.2`, that combination is *unresolvable*, and it surfaces as an opaque resolver error at `uv add` time in some unlucky host project six months from now.

Therefore:

- **Shared platform dependencies get wide ranges.** `django`, `djangorestframework`, `celery`, `redis`, `drf-spectacular`, `python-decouple`, `django-celery-beat` — anything the host also depends on directly — are declared as compatible ranges with an upper bound at the next known-breaking major:
  ```toml
  dependencies = [
      "django>=5.2,<7.0",
      "djangorestframework>=3.15,<4.0",
      "drf-spectacular>=0.27,<1.0",
  ]
  ```
- **App-private dependencies can be tighter**, but still prefer a range. A niche library only this app uses (`stripe`, `twilio`, `qrcode`) is less likely to collide, so `"stripe>=11,<13"` is fine — but `==` is still discouraged, because the moment a second app also needs `stripe`, an exact pin on both sides is a coin flip.
- **The host pins the exact versions everyone runs against.** The host's `pyproject.toml` + `uv.lock` is where `django==6.0.4` actually gets decided. Apps declare what they *tolerate*; the host decides what *runs*.
- **Never declare a dependency on another app package.** Not even a loose range. See §6 — with one named exception:
  - **`appkit` is the exception.** Every app declares `"hjtdev-appkit>=2.0,<3.0"` in `[project.dependencies]` and imports the shared helpers it bundles from it (§4, §12) rather than reimplementing them. (The distribution is `hjtdev-appkit` — the bare `appkit` name is an unrelated package already on PyPI — but the *importable* module stays `appkit` everywhere: `import appkit`, `appkit.mixins`, `appkit.exceptions`, and so on.) The range rule above applies with full force here — `appkit` is the most widely shared dependency in the entire ecosystem, so an exact pin on it is the worst possible place for one: two apps pinning different exact versions of `appkit` is unresolvable in any host that installs both.

    Make the distinction crisp, because this is the rule most likely to be misapplied later: §6 bans an app **reaching sideways into another app's models and services** — an ambient assumption that some other app just happens to be installed in the same host. A declared shared dependency is a different category entirely: it's explicit, versioned, resolved by `uv`, and sitting right there in `pyproject.toml` for anyone to see — the same category as the `jwt-core` dependency an OTP app would declare, not the category §6 exists to prevent. The test is mechanical: *is it in `[project.dependencies]`?* If yes, it's a declared dependency. If no, and you're importing it anyway, that's the §6 violation.
- **Test/lint tooling never appears in `dependencies`.** It goes in `[dependency-groups]`, which is never installed by a consumer — see §3.

### 1.2 Namespacing convention

A handful of things from every installed app end up merged into one shared, flat namespace — one `settings.py`, one `.env`, one React Query cache. Two apps picking the same short name silently collide there, so every one of these is prefixed with the app's own name, no exceptions:

- **Throttle scopes** — `notifications_list`, not `list` (§4).
- **Settings dict keys** — `NOTIFICATIONS = {...}`, not `SETTINGS = {...}` (§3, §8).
- **`.env` keys** — `NOTIFICATIONS_PROVIDER_API_KEY`, not `PROVIDER_API_KEY` (§8).
- **Frontend query keys** — `["notifications", ...]`, not `["list", ...]` (§12).
- **Celery task names** — `notifications_app.tasks.cleanup`, which comes free if tasks live in the app's own module (don't override `name=` with something short).
- **Cache keys** — any `cache.set()` key is prefixed too; the host runs one Redis instance.

None of this is enforced by tooling — it's a convention every app package is expected to follow, and it's the first thing to check if a throttle rate or a cache invalidation is behaving strangely across two apps that were each written correctly in isolation.

## 2. Package Folder Structure

```
notifications-app/                       # the repo
├── README.md                            # ONE doc covering both halves — Python config AND
│                                          npm/hook integration, see §8
├── CHANGELOG.md                          # Keep a Changelog format, ONE changelog for the
│                                          whole package — both halves release together, §11
├── CLAUDE.md                             # agent instructions for working IN this repo,
│                                          see CLAUDE-CODE-GUIDE-APP.md
├── .python-version                       # e.g. "3.14" — matches CI and the playground image
├── .pre-commit-config.yaml               # ruff, mypy, prettier/eslint — see §3
├── .github/
│   └── workflows/
│       └── ci.yml                        # thin caller of the org reusable workflow, see §10
├── backend/
│   ├── pyproject.toml                    # build config, dependencies, dependency-groups,
│   │                                       ruff/mypy/pytest config — see §3
│   ├── uv.lock                            # committed; used by CI and the playground only —
│   │                                       NEVER travels to a consuming host, see §3.4
│   ├── MANIFEST.in                        # ships locale/, templates/, static/ in the wheel
│   └── src/
│       └── notifications_app/             # the importable package — this name is what
│           │                                goes in INSTALLED_APPS and every import
│           ├── __init__.py
│           ├── apps.py                    # AppConfig — name, verbose_name (translatable)
│           ├── conf.py                    # typed accessor over the host's NOTIFICATIONS
│           │                                settings dict, with defaults — see §3.5
│           ├── models.py                  # indexed and query-optimized, see note below
│           ├── admin.py                   # Jazzmin ModelAdmin registrations, see §5
│           ├── admin_views.py             # custom admin-dashboard API views, see §5
│           ├── views.py                   # user-facing API views
│           ├── serializers.py
│           ├── permissions.py             # user-facing + IsAppAdmin, see §5
│           ├── signals.py                 # emits this app's own events, see §6
│           ├── services.py                # its public callable interface, see §6
│           ├── urls.py                    # user-facing endpoints
│           ├── urls_admin.py              # admin-dashboard endpoints
│           ├── tasks.py                   # celery / django.tasks — autodiscovered by host
│           ├── utils.py                   # app-private helpers only, if any — shared cache/
│           │                                mixin/error-envelope helpers come from the
│           │                                appkit dependency instead, see §4
│           ├── factories.py               # factory_boy factories — PUBLIC test surface, §7.3
│           ├── migrations/
│           ├── locale/                    # translations, bundled via package data, see §8
│           └── templates/notifications_app/   # namespaced so a host can override
│                                                cleanly, see INTEGRATION-GUIDE.md §5
├── frontend/
│   ├── package.json                       # name, peer deps, build config, see §12
│   ├── tsconfig.json                      # "strict": true, no exceptions
│   ├── vitest.config.ts
│   └── src/
│       ├── index.ts                       # the ONLY entrypoint a host imports from, §12
│       ├── hooks/
│       │   ├── useNotifications.ts
│       │   └── useSendNotification.ts
│       ├── api/
│       │   ├── config.ts                  # one-line binding of this app's namespace/basePath
│       │   │                                to appkit's shared useApiClient hook, see §12
│       │   └── manager.ts                 # typed NotificationsManager — the ONLY place
│       │                                    raw requests happen, see §12
│       └── types.ts
├── playground/                            # local dev host — a minimal Django+Next pair with
│   │                                        both halves linked by path, see §11.2
│   ├── backend/
│   ├── frontend/
│   └── docker-compose.yml
└── tests/
    ├── backend/                           # pytest — authoritative gate for the Python half
    │   ├── conftest.py
    │   └── test_*.py
    └── frontend/                          # Vitest + MSW — authoritative gate for the TS half
```

Two structural notes that cause the most first-time breakage:

**Package data must be declared, or it silently doesn't ship.** `locale/`, `templates/`, and any `static/` are not `.py` files, so no build backend includes them by default. With `setuptools` that means `include-package-data = true` in `pyproject.toml` plus a matching `MANIFEST.in`; with `hatchling` it means an explicit `[tool.hatch.build.targets.wheel]` include list. Skipping this is the most common reason a freshly-installed app "loses" its translations or templates — and §10's wheel-smoke-test CI job exists specifically to catch it before a release.

**Indexes and query optimization are baseline, not per-app.** Every model in `models.py` declares `Meta.indexes` for fields used in frequent filters, ordering, or foreign key lookups, and every queryset in `views.py`/`services.py` uses `select_related`/`prefetch_related` to avoid N+1 queries.

### Referencing the host's user model

Nearly every app needs a `user` field, but auth is its own separate installed package — an app can't `import` it without violating the no-inter-app-imports rule (§6). Django already has the sanctioned indirection for exactly this: reference `settings.AUTH_USER_MODEL`, never a specific User model:

```python
# notifications_app/models.py
from django.conf import settings
from django.db import models


class Notification(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="notifications",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [models.Index(fields=["user", "-created_at"])]
```

```python
# notifications_app/migrations/0001_initial.py (excerpt)
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]
    operations = [...]
```

This isn't an import of the auth package — it's a string reference Django resolves at runtime, and `swappable_dependency` is what makes the migration graph run the auth app's migrations first automatically, regardless of which specific auth package a host has installed. This is the *only* app-to-app reference every app is expected to need; see §6 for what to do on the rarer occasions an app needs to reference something else entirely.

## 3. Toolchain, Dependencies & Project Configuration

`uv` is the only Python package manager in this ecosystem. There is no `requirements.txt` anywhere, in an app or in a host — one dependency declaration format, one lockfile format, one install command.

### 3.1 `backend/pyproject.toml` — the canonical file

```toml
[build-system]
requires = ["setuptools>=77", "setuptools-scm>=8"]
build-backend = "setuptools.build_meta"

[project]
name = "notifications-app"
version = "1.4.2"                    # kept in lockstep with CHANGELOG.md + package.json, §11
description = "Multi-channel notification delivery for Django, as an installable app package."
requires-python = ">=3.13"           # a RANGE, not a pin — a host may be on 3.13 or 3.14
license = "MIT"
# "README.md", not "../README.md" — a build backend reads `readme` relative to THIS file, and a
# monorepo's sdist build has no reliable access to a file outside its own project root (build
# isolation may operate on a copy of just backend/). backend/README.md is a committed, generated
# COPY of the repo-root README (§8's README-sync note), never hand-written prose of its own —
# pointing this at "../README.md" instead is what silently shipped three real releases with an
# empty PyPI description before anyone noticed (`docs/CONTRACT.md` §22).
readme = "README.md"

# Wide ranges on anything the host also depends on — see §1.1
dependencies = [
    "django>=5.2,<7.0",
    "djangorestframework>=3.15,<4.0",
    "drf-spectacular>=0.27,<1.0",
    "python-decouple>=3.8,<4.0",
]

# A TOML subtable, not a plain key — MUST come after every bare `[project]` key above
# (`dependencies` included). A subtable header implicitly closes the parent table to further bare
# keys, so placing this any earlier silently nests `dependencies`/`optional-dependencies` under
# `[project.urls]` instead of `[project]` — caught live: setuptools rejects the build with
# `project.urls.dependencies must be string` once that happens.
[project.urls]
Homepage = "https://github.com/yourorg/notifications-app"
Repository = "https://github.com/yourorg/notifications-app"
Changelog = "https://github.com/yourorg/notifications-app/blob/main/CHANGELOG.md"

[project.optional-dependencies]
# Extras = features a CONSUMER opts into. Installed with notifications-app[sms].
sms = ["twilio>=9,<10"]
push = ["pyfcm>=2,<3"]

[dependency-groups]
# PEP 735 groups = tooling for developing THIS package. Never installed by a consumer,
# never published, not visible to a host at all. This is the correct home for all of it.
dev = [
    "ruff>=0.12",
    "mypy>=1.14",
    "django-stubs[compatible-mypy]>=5.1",
    "djangorestframework-stubs>=3.15",
    "pre-commit>=4.0",
]
test = [
    "pytest>=8.3",
    "pytest-django>=4.9",
    "pytest-cov>=6.0",
    "pytest-xdist>=3.6",
    "factory-boy>=3.3",
    "psycopg[binary]>=3.2",          # tests run on Postgres, see §7.5
]

[tool.uv]
default-groups = ["dev", "test"]     # `uv sync` gives a contributor everything

[tool.setuptools]
include-package-data = true

[tool.setuptools.packages.find]
where = ["src"]

# ---------------------------------------------------------------- ruff
[tool.ruff]
line-length = 100
target-version = "py313"
src = ["src", "../tests"]
# backend/README.md (§8's README-sync copy) sits inside this directory — `ruff format` reformats
# Python code fences inside Markdown files by default, and without this exclude it rewrites the
# README's own example config blocks to satisfy a formatter meant for src/ and tests/, not
# narrative documentation. Found live the moment a package's backend/README.md first existed.
extend-exclude = ["README.md"]

[tool.ruff.lint]
select = [
    "E", "W",     # pycodestyle
    "F",          # pyflakes
    "I",          # isort
    "UP",         # pyupgrade
    "B",          # bugbear
    "DJ",         # flake8-django
    "S",          # bandit — security
    "TID",        # tidy-imports (used to enforce §6, see below)
    "RUF",
]
ignore = ["S101"]  # assert is fine in tests

[tool.ruff.lint.per-file-ignores]
"../tests/**" = ["S", "TID251"]
"*/migrations/*" = ["E501", "RUF012"]

[tool.ruff.lint.flake8-tidy-imports]
ban-relative-imports = "parents"

# Machine-enforced version of the §6 rule: this package may not import a sibling app.
# Add a line per app that exists in the ecosystem; the CI job in §10 also greps as a backstop.
[tool.ruff.lint.flake8-tidy-imports.banned-api]
"payments_app".msg = "App packages must never import each other — see APP-DESIGN.md §6."
"cart_app".msg = "App packages must never import each other — see APP-DESIGN.md §6."
"auth_app".msg = "Use settings.AUTH_USER_MODEL instead — see APP-DESIGN.md §2."

# Factories are a test-only surface (§7.3). This works in an app repo because the test
# tree lives outside src/ and is cleanly exempted below — a host project can't do the
# same, see BASE-DESIGN.md §5.2.
"notifications_app.factories".msg = "factories.py is test-only — see APP-DESIGN.md §7.3."

# ---------------------------------------------------------------- mypy
[tool.mypy]
python_version = "3.13"
strict = true
plugins = ["mypy_django_plugin.main", "mypy_drf_plugin.main"]
warn_unreachable = true
exclude = ["migrations/"]

[[tool.mypy.overrides]]
module = "*.migrations.*"
ignore_errors = true

[tool.django-stubs]
django_settings_module = "tests.backend.settings"

# ---------------------------------------------------------------- pytest (see §7)
[tool.pytest.ini_options]
DJANGO_SETTINGS_MODULE = "tests.backend.settings"
pythonpath = ["src", ".."]
testpaths = ["../tests/backend"]
python_files = ["test_*.py"]
addopts = """
  -ra --strict-markers --strict-config
  --cov=notifications_app --cov-report=term-missing --cov-fail-under=85
"""
markers = [
    "slow: excluded from the default run, opt in with -m slow",
    "integration: crosses a real DB/broker boundary rather than mocking it",
]
filterwarnings = ["error::DeprecationWarning"]

[tool.coverage.run]
omit = ["*/migrations/*", "*/tests/*"]
```

### 3.2 Everyday commands

```bash
uv sync                       # create .venv, install deps + dev + test groups
uv run pytest                 # run the suite in that env, no manual activation
uv run ruff check --fix .
uv run ruff format .
uv run mypy src
uv add "stripe>=11,<13"       # adds to [project.dependencies] and re-locks
uv add --group test "freezegun>=1.5"
uv lock --upgrade-package django   # move one dep within its declared range
uv build                      # produce the wheel + sdist CI smoke-tests in §10
```

### 3.3 `.python-version` and interpreter policy

Commit a `.python-version` containing the version CI and the playground use (e.g. `3.14`). It pins what `uv` provisions locally; `requires-python` in `pyproject.toml` stays a *range*, because that's a compatibility claim to consumers, not a local preference. Keeping these two conceptually separate avoids the trap of accidentally telling every host "you must be on exactly 3.14."

### 3.4 The lockfile boundary — the most common `uv` misconception

**An app package's `uv.lock` never travels downstream.** When a host runs `uv add "git+...#subdirectory=backend"`, `uv` reads only that package's `pyproject.toml` `[project.dependencies]`. The app's own lockfile is used for exactly two things: reproducing a contributor's dev environment, and pinning CI. This is why §1.1's range rule matters so much — the ranges *are* the published contract, and a green CI run against your locked versions proves nothing about what a host will resolve. §10 includes a `resolution-matrix` job that resolves against the *lowest* and *highest* ends of your declared ranges precisely to close that gap.

### 3.5 Settings access — `conf.py`, not scattered `getattr` calls

An app reads host configuration from one place, with defaults, so a host that omits an optional key gets a sane value instead of an `AttributeError` deep in a view:

```python
# notifications_app/conf.py
from typing import Any

from django.conf import settings

DEFAULTS: dict[str, Any] = {
    "DEFAULT_CHANNEL": "email",
    "RETENTION_DAYS": 90,
    "MAX_BATCH_SIZE": 500,
}


def get_setting(key: str) -> Any:
    """Read a NOTIFICATIONS setting, falling back to this app's documented default."""
    return getattr(settings, "NOTIFICATIONS", {}).get(key, DEFAULTS[key])
```

Required-and-secret values (API keys) are the exception: those come from the environment via `decouple.config("NOTIFICATIONS_PROVIDER_API_KEY")` and should fail loudly at import or first use if missing, rather than defaulting. Every key in `DEFAULTS` and every `.env` key is listed in the README block (§8) — that file and this one must agree, and §11 makes updating them a release step.

### 3.6 Pre-commit

```yaml
# .pre-commit-config.yaml
repos:
  # Tool versions come from uv.lock / package-lock.json, never a pinned `rev` —
  # so pre-commit and CI can never disagree about which formatter is authoritative.
  - repo: local
    hooks:
      - id: ruff
        name: ruff
        entry: bash -c 'cd backend && uv run ruff check --fix .'
        language: system
        types_or: [python, pyi]
        files: ^backend/
        pass_filenames: false
      - id: ruff-format
        name: ruff-format
        entry: bash -c 'cd backend && uv run ruff format .'
        language: system
        types_or: [python, pyi]
        files: ^backend/
        pass_filenames: false
      - id: mypy
        name: mypy
        entry: bash -c 'cd backend && uv run mypy src'
        language: system
        files: ^backend/src/
        pass_filenames: false
        require_serial: true
      - id: eslint
        name: eslint
        entry: bash -c 'cd frontend && npx eslint --fix src'
        language: system
        files: ^frontend/
        pass_filenames: false
      - id: prettier
        name: prettier
        entry: bash -c 'cd frontend && npx prettier --write src'
        language: system
        files: ^frontend/
        pass_filenames: false
  # Only environment-independent hooks stay as pinned mirrors.
  - repo: https://github.com/pre-commit/pre-commit-hooks
    rev: v5.0.0
    hooks:
      - id: check-merge-conflict
      - id: end-of-file-fixer
      - id: trailing-whitespace
      - id: check-added-large-files
      - id: detect-private-key
      - id: check-yaml
      - id: check-toml
```

`uv run pre-commit install` once per clone. This matters more in this ecosystem than in a normal project: you have one base repo plus N app repos that all need to stay stylistically consistent without a human re-checking each one, and pre-commit is what makes that automatic instead of aspirational.

The `cd` in each entry is load-bearing. `uv run --project backend mypy` sets environment resolution but not the working directory, so mypy would look for config in the repo root, find none, and run *without* `strict`, the Django plugin, or `django_settings_module` — passing while checking almost nothing. Any tool that discovers its config from the current directory needs the explicit `cd`.

## 4. Views, Rate Limiting & API Documentation Standards

- **Caching & error handling.** Every GET/list/retrieve view uses a caching mixin, and every view uses consistent error-handling/response conventions. Because this package must work standalone in *any* host project, it cannot import a host's `backend/tools/` — that folder is project-owned and isn't guaranteed to exist, or to exist at a stable import path, in every host. Instead, every app declares `hjtdev-appkit>=2.0,<3.0` (§1.1) and imports `CachedListMixin` from `appkit.mixins` and `standard_exception_handler` from `appkit.exceptions` — see `BASE-DESIGN.md` §3 for the exact envelope (`{"error": {"code", "message", "details", "request_id"}}` and the fixed `code` list) those helpers produce. This is a declared, versioned dependency, not an assumption about the host's internals — see §1.1 for why `appkit` is the one named exception to "never depend on another app package."
- **Rate limiting.** Every view declares a `throttle_scope`, prefixed per §1.2, and every scope is listed in the app's `README.md` (§8) so a host knows what to add to `REST_FRAMEWORK['DEFAULT_THROTTLE_RATES']`. No view ships without one.
- **API documentation.** Every view/viewset carries a complete `drf-spectacular` `@extend_schema` (or `extend_schema_view`) — summary, description, request/response serializers, and `tags=["notifications"]` for public views or `tags=["notifications-admin"]` for admin-dashboard views, so Swagger stays grouped per app and per surface.
- **Pagination.** List views that can return unbounded data set an explicit `pagination_class` rather than relying on the host's `DEFAULT_PAGINATION_CLASS`, which the app can't know. The page-size default is documented in the README block.

```python
# notifications_app/views.py — every view in every app should structurally match this
# shape: appkit's caching mixin, throttle_scope, full schema, a real permission class,
# and an optimized queryset.
from appkit.mixins import CachedListMixin   # shared helper, declared as a dependency, per above
from drf_spectacular.utils import extend_schema
from rest_framework import generics

from .models import Notification
from .permissions import IsNotificationOwner
from .serializers import NotificationSerializer


@extend_schema(
    summary="List the current user's notifications",
    description="Returns notifications belonging to the authenticated user, newest first.",
    responses={200: NotificationSerializer(many=True)},
    tags=["notifications"],
)
class NotificationListView(CachedListMixin, generics.ListAPIView):
    serializer_class = NotificationSerializer
    permission_classes = [IsNotificationOwner]
    throttle_scope = "notifications_list"
    cache_timeout = 30  # seconds — CachedListMixin's own convention

    def get_queryset(self):
        return (
            Notification.objects
            .filter(user=self.request.user)
            .select_related("user")
        )
```

## 5. Two Admin Surfaces & Permissions

Every app supports two separate admin surfaces, and its own `permissions.py` gates both:

1. **Django Admin / Jazzmin** — standard `ModelAdmin` registrations in `admin.py`. Jazzmin's per-app icon/menu ordering is configured in the *host's* `JAZZMIN_SETTINGS` — an app can suggest an icon in its `README.md`, but can't register into that dict itself.
2. **Custom Admin Dashboard API** — `admin_views.py` + `urls_admin.py`, gated by `IsAppAdmin`. These are real DRF endpoints meant for a custom admin frontend, throttled and documented exactly like public views.

`permissions.py` exposes, at minimum, one user-facing permission class (app-specific business logic) and `IsAppAdmin`. Both rely only on what Django's user model already guarantees everywhere — `is_authenticated`, `is_staff`, `is_superuser`, `user.has_perm(...)` — never on models or logic from another reusable app, which is the whole point of §6.

## 6. Inter-App Communication (Signals & Services)

An app package **must never import another app package** — with the one named exception at §1.1: `appkit`, which every app declares as an explicit, versioned dependency rather than reaching for sideways. Everything below is about the case §1.1's exception doesn't cover — one app reaching into another app's own models, services, or signals without either app declaring the other. The only two things an app exposes for that kind of production use are `signals.py` (things that happened) and `services.py` (things you can ask it to do) — plus `factories.py` as a *test-only* third surface, see §7.3. Wiring two apps together is the host project's job, done in `backend/core/` — never inside either app. See `INTEGRATION-GUIDE.md` §4 for the full host-side pattern; here's the app side of the same example:

```python
# notifications_app/signals.py
import django.dispatch

# fired whenever a notification is actually sent — sends: user_id, channel, template
notification_sent = django.dispatch.Signal()
```

```python
# notifications_app/services.py
from .models import Notification
from .signals import notification_sent


class NotificationService:
    @staticmethod
    def send(user_id: int, template: str, context: dict, channel: str = "email") -> Notification:
        notification = Notification.objects.create(
            user_id=user_id, template=template, context=context, channel=channel
        )
        # ... actually dispatch the email/SMS/push ...
        notification_sent.send(
            sender=Notification, user_id=user_id, channel=channel, template=template
        )
        return notification
```

```python
# payments_app/signals.py
import django.dispatch

# sends: payment_id, user_id, amount
payment_completed = django.dispatch.Signal()
```

Neither package above knows the other exists. `NotificationService.send(...)` is a plain, agnostic callable — it doesn't know or care who calls it. `payment_completed` is a plain event — it doesn't know or care who's listening. The connection between them lives entirely in the host's `core/signals.py`.

**Signal payloads are a versioned contract.** Removing or renaming a kwarg from a signal, or changing a `services.py` method signature, is a **major** version bump — a host's `core/signals.py` receiver breaks silently otherwise (a missing kwarg raises at dispatch time, in production, in a background task). Document every signal's payload in the README (§8) and treat that documentation as the contract.

The same discipline applies to each app's frontend half: a package's `frontend/src/hooks/` must never import from another package's frontend SDK. Combining two apps' hooks in one UI (e.g. a checkout page using both `useCart` from one package and `useCreatePayment` from another) happens in the host's own `frontend/` code, at the page or component level — never inside either SDK. See `INTEGRATION-GUIDE.md` §4 for the worked example.

### Cross-app data references

Beyond the user relation (§2), two apps needing to relate to each other's data is common — it still doesn't mean two apps get to import each other. Two more patterns, from more common to less:

1. **An optional, dynamic reference to *any* other app's object — `contenttypes`.** When an app occasionally needs to point at an object that could live in one of several other apps (or in none, depending on the project), use Django's built-in `contenttypes` framework instead of a real foreign key:
   ```python
   # ticketing_app/models.py
   from django.contrib.contenttypes.fields import GenericForeignKey
   from django.contrib.contenttypes.models import ContentType
   from django.db import models


   class Ticket(models.Model):
       category = models.CharField(max_length=100)
       related_content_type = models.ForeignKey(
           ContentType, null=True, blank=True, on_delete=models.SET_NULL
       )
       related_object_id = models.PositiveIntegerField(null=True, blank=True)
       related_object = GenericForeignKey("related_content_type", "related_object_id")
   ```
   `contenttypes` ships with Django — it's already a dependency of `django.contrib.admin`, so it's always available — and it lets `Ticket` point at a `Payment`, an `Order`, or nothing at all, without ever importing `payments_app`. Resolving `related_object` into something meaningful is `core/`'s job, same as every other cross-app connection in this document. In practice this should be the exception, not the default — most apps, like a ticketing system that's really just a category and a status, don't need to reference anything outside themselves at all.

2. **Two concepts that are really one thing — don't force a split.** If two concepts are coupled tightly enough that they'd always need a direct reference to each other and would always release together — a cart and the order it becomes — that's a sign they're one package, not two decoupled ones with a manufactured exception carved into the import rule. Shipping them as a single package (with real foreign keys between their models, since they're in the same app) is more honest than inventing a special case for one pair of apps.

### Realtime (optional fourth surface)

Channels is not part of the base scaffold (`BASE-DESIGN.md` §3 "WebSockets") — most projects
never open a socket, and a project that does opts in explicitly. An app package that needs
realtime delivery exposes a **fourth public surface**, alongside `urls.py`/`urls_admin.py`,
`signals.py`/`services.py`, and `factories.py`:

```python
# notifications_app/routing.py
from django.urls import re_path

from . import consumers

websocket_urlpatterns = [
    re_path(r"ws/notifications/$", consumers.NotificationConsumer.as_asgi()),
]
```

```python
# notifications_app/consumers.py
from channels.generic.websocket import AsyncJsonWebsocketConsumer


class NotificationConsumer(AsyncJsonWebsocketConsumer):
    async def connect(self) -> None:
        if not self.scope["user"].is_authenticated:
            await self.close()
            return
        await self.channel_layer.group_add(f"user-{self.scope['user'].id}", self.channel_name)
        await self.accept()

    async def notification_message(self, event: dict) -> None:
        await self.send_json(event["payload"])
```

**The host mounts `websocket_urlpatterns` explicitly in `config/asgi.py`** — nothing
auto-discovers it, same as every other wiring point in this ecosystem. See `BASE-DESIGN.md`
§3 "WebSockets" for the `ProtocolTypeRouter` composition on the host side.

**`channels` is a wide-range *optional* dependency** — an extra, e.g. `notifications-app[realtime]`
— so the package still installs cleanly into a host that isn't running Channels at all. A host
that never imports `routing.py`/`consumers.py` never needs the extra; only `config/asgi.py`
pulling them in requires it.

**The §6 boundary rules apply here unchanged: a consumer must never import another app
package.** The mediator for realtime is the same one for everything else — a receiver in
`core/signals.py`, calling `channel_layer.group_send(...)` — not a direct import between two
apps' consumers. App A's `services.py` fires a signal; `core/signals.py` decides that event
should be pushed over app B's socket and calls `group_send` itself. Neither app knows the
other's channel-group naming scheme, let alone that a socket is involved.

**Auth is the one thing every realtime app needs and none should reimplement.**
`channels.auth.AuthMiddlewareStack` is session-based, but auth in this ecosystem is a
standalone JWT app package (`BASE-DESIGN.md` §3), and a browser cannot set an `Authorization`
header on a WebSocket handshake — the socket has to authenticate via a token in the query
string or a subprotocol instead. That middleware belongs in the **auth app package**, exposed
as something like `JWTAuthMiddlewareStack`, so the first app that ships a consumer doesn't
have to invent (and every app after it doesn't have to re-invent) how a socket proves who's
connecting.

`routing.py` and `consumers.py` are a public surface like any other — changing a consumer's
message shape or removing a route is a **major** version bump, same rule as `signals.py`
payloads in §6.

## 7. Testing Standards

`pytest` is the authoritative gate for the Python half; Vitest + MSW for the TypeScript half. Configuration lives in `backend/pyproject.toml` (§3.1) — there is no separate `pytest.ini`, `setup.cfg`, or `tox.ini`.

### 7.1 Test settings module

Tests need a real Django settings module. It lives in the test tree, not the package (the package must never contain a settings file — that's a host concern):

```python
# tests/backend/settings.py
SECRET_KEY = "test-only-not-a-secret"
DEBUG = False
USE_TZ = True

INSTALLED_APPS = [
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.admin",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "drf_spectacular",
    "notifications_app",
]

# Schema generation (§12, "Generated types") walks the URLconf, so this module needs one —
# it isn't only a test-runner requirement.
ROOT_URLCONF = "tests.backend.urls"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": "test_notifications",
        "USER": "postgres",
        "PASSWORD": "postgres",
        "HOST": "localhost",   # overridden to "postgres" by CI env, see §10
        "PORT": "5432",
    }
}

REST_FRAMEWORK = {
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "DEFAULT_THROTTLE_RATES": {
        "notifications_list": "60/min",
        "notifications_send": "20/min",
    },
}

# COMPONENT_SPLIT_REQUEST is required, not optional — see §12, "Generated types", for why.
SPECTACULAR_SETTINGS = {
    "TITLE": "notifications-app",
    "VERSION": "0.0.0",  # irrelevant here — the app's real version lives in pyproject.toml
    "COMPONENT_SPLIT_REQUEST": True,
}

NOTIFICATIONS = {"DEFAULT_CHANNEL": "email"}
```

```python
# tests/backend/urls.py — exists so the app's schema can be generated standalone, without a
# host. Mounts the same URLconfs a host's own backend/config/urls.py would mount per the
# app's README (§8) — nothing host-specific, since this file ships in the test tree, not a
# real host's tree.
from django.urls import include, path

urlpatterns = [
    path("api/v1/notifications/", include("notifications_app.urls")),
    path("api/v1/notifications/admin/", include("notifications_app.urls_admin")),
]
```

Keeping `tests/backend/settings.py` minimal is deliberate: if your tests only pass with fifteen extra apps installed, the package has an undeclared dependency on a host's configuration, and a real host will hit that.

### 7.2 `conftest.py` hierarchy

```
tests/backend/conftest.py          # app-wide fixtures: api_client, user, admin_user
tests/backend/api/conftest.py      # fixtures only the view tests need
```

```python
# tests/backend/conftest.py
import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from notifications_app.factories import NotificationFactory


@pytest.fixture
def api_client() -> APIClient:
    return APIClient()


@pytest.fixture
def user(db):
    return get_user_model().objects.create_user(username="alice", password="pw")


@pytest.fixture
def auth_client(api_client, user) -> APIClient:
    api_client.force_authenticate(user=user)
    return api_client


@pytest.fixture
def notification(user):
    return NotificationFactory(user=user)
```

In a **host** project the same hierarchy applies, one level up: `backend/conftest.py` for project-wide fixtures, `backend/core/tests/conftest.py` for anything spanning apps. See `INTEGRATION-GUIDE.md` §4.

### 7.3 `factories.py` — the third public surface

This is a deliberate addition to the two-surface rule in §6, and it solves a real problem: a host's `core/tests/test_signals.py` needs to construct a realistic `Payment` in order to fire `payment_completed` at it. Without a sanctioned way to do that, every host either duplicates the app's creation logic or reaches directly into its models — both worse than the alternative.

So: **every app ships `factories.py` inside the package** (not in `tests/`, so it's importable from a host), and it is an explicitly public, importable surface for **test code only**:

```python
# notifications_app/factories.py
import factory
from django.contrib.auth import get_user_model

from .models import Notification


class UserFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = get_user_model()
        django_get_or_create = ("username",)

    username = factory.Sequence(lambda n: f"user{n}")


class NotificationFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Notification

    user = factory.SubFactory(UserFactory)
    template = "welcome"
    channel = "email"
    context = factory.Dict({})
```

Rules for it:
- `factory-boy` is declared in the `test` **dependency group**, not `[project.dependencies]` — so a host that imports factories in its tests must add `factory-boy` to its own test group. Document that in the README block. (An app must not force `factory-boy` into every production install.)
- Importing `notifications_app.factories` from another app's *tests* or from `core/tests/` is allowed and expected. Importing it from anywhere in production code is a bug, and `ruff`'s `TID251` config in §3.1 bans it outside test paths. A host project can't enforce this with ruff for structural reasons — see `BASE-DESIGN.md` §5.2 for the grep-based equivalent.
- Factories are covered by semver like anything else public: renaming `NotificationFactory` is a breaking change.

### 7.4 What gets tested, at minimum

An app's suite isn't complete until it covers:

| Area | Minimum bar |
|---|---|
| Every `services.py` method | Happy path + at least one failure path |
| Every view | 200 for the permitted user, 403 for another user's object (the IDOR case from §9), 401 unauthenticated |
| Every signal it emits | Fired with the exact documented payload — connect a receiver in the test and assert kwargs |
| Every serializer | Write-path validation rejects bad input; read-path omits sensitive fields |
| Every `tasks.py` task | Called synchronously as a plain function (`CELERY_TASK_ALWAYS_EAGER` is not needed if you call `task_fn(...)` directly) |
| Throttling | One test asserting the scope name exists and is applied — a typo'd `throttle_scope` fails open, silently |
| Migrations | `pytest --create-db` proves they apply cleanly from zero; a `makemigrations --check --dry-run` step in CI proves none are missing |

### 7.5 Postgres, not SQLite

Tests run against real Postgres, locally and in CI. SQLite papers over behavioral differences that only surface in production — `JSONField` lookups, `select_for_update`, `ArrayField`, case-sensitivity in `iexact`, constraint deferral, and transaction semantics. `playground/docker-compose.yml` provides a Postgres for local runs; §10's CI job provides one as a service container. The connection host comes from an env var so the same config works in both.

### 7.6 Markers, coverage, parallelism

- `-m "not slow"` is the default developer loop; CI runs everything.
- `integration` marks anything touching a real DB/broker rather than a mock — useful for running the fast half first in a pre-push hook.
- `--cov-fail-under=85` is enforced in CI, not eyeballed. Pick a number you'll actually hold; a threshold you routinely lower is worse than none.
- `-n auto` (`pytest-xdist`) once the suite passes a few seconds. Note it requires tests to be independent — a shared-state test that only passes serially is a bug worth finding early.

### 7.7 Frontend testing

Vitest + MSW (Mock Service Worker) is the standard — mock the HTTP layer, never a live backend, so the test suite runs the same in CI as it does locally. **Vitest 4.x** is the version pinned by the scaffold's own frontend baseline (`frontend/package.json`, see `BASE-DESIGN.md` §3) — an app package's `devDependencies` should track the same major, not an older one, so a host's `make check` and an installed app's own `npm test` run the same engine. Landing on Vitest 2 or 3 here is a version-drift bug, not a style choice:

```tsx
// tests/frontend/useSendNotification.test.tsx
import { renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { setupServer } from "msw/node";
import { http, HttpResponse } from "msw";
import { useSendNotification } from "../../frontend/src/hooks/useSendNotification";

const server = setupServer(
  http.post("/api/v1/notifications/send/", () =>
    HttpResponse.json({ id: "1", status: "sent" })
  )
);

beforeAll(() => server.listen({ onUnhandledRequest: "error" }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

function wrapper({ children }: { children: React.ReactNode }) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
}

test("sends a notification and returns the created record", async () => {
  const { result } = renderHook(() => useSendNotification(), { wrapper });
  result.current.mutate({ userId: "42", template: "welcome" });
  await waitFor(() => expect(result.current.isSuccess).toBe(true));
  expect(result.current.data).toEqual({ id: "1", status: "sent" });
});
```

Two details that matter: `onUnhandledRequest: "error"` turns a hook accidentally calling an undeclared endpoint into a test failure instead of a silent hang, and `retry: false` stops react-query's default retry from making a failure-path test take three seconds. Every hook gets at least one success-path test and one error-path test (mock a 4xx/5xx and assert `isError`) — a hook without an error-path test is the frontend equivalent of a backend view no one checked against a failed permission.

## 8. Documentation Standard (`README.md` Contract)

Every app's `README.md` must include a **copy-paste-ready configuration block** so wiring the app into a host project is mechanical, not exploratory. At minimum:

````markdown
## Installation — backend

Published to PyPI — every app package in this ecosystem is (§10.2):

```bash
uv add "notifications-app>=1.4,<2.0"
```

Pinning an unreleased commit instead of a tagged release still works via the git+subdirectory
form, since `uv`/`pip` correctly implement Git's `#subdirectory=` fragment:

```bash
uv add "git+https://github.com/yourorg/notifications-app.git@v1.4.2#subdirectory=backend"
```

Optional extras: `notifications-app[sms]` adds Twilio support, `[push]` adds FCM.

## Compatibility

- Python 3.13+ · Django 5.2–6.x · DRF 3.15+
- Requires `django.contrib.contenttypes` (present by default with the admin).

## Settings — add to `backend/config/settings.py`

```python
INSTALLED_APPS += ["notifications_app"]

MIDDLEWARE += []  # none required

REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"].update({
    "notifications_list": "60/min",
    "notifications_send": "20/min",
})

NOTIFICATIONS = {
    "DEFAULT_CHANNEL": "email",   # "email" | "sms" | "push"
    "RETENTION_DAYS": 90,
    "MAX_BATCH_SIZE": 500,
}
```

## Required `.env` keys

```
NOTIFICATIONS_PROVIDER_API_KEY=      # required — the app fails at startup without it
NOTIFICATIONS_FROM_ADDRESS=          # optional, defaults to DEFAULT_FROM_EMAIL
```

## URL mounting — add to `backend/config/urls.py`

```python
path("api/v1/notifications/", include("notifications_app.urls")),
path("api/v1/admin/notifications/", include("notifications_app.urls_admin")),
```

## Migrations

```bash
uv run python manage.py migrate notifications_app
```

## Signals emitted (contract — payload changes are a MAJOR bump)

| Signal | Payload kwargs |
|---|---|
| `notification_sent` | `user_id: int`, `channel: str`, `template: str` |
| `notification_failed` | `user_id: int`, `channel: str`, `error: str` |

## Services (public callables)

| Method | Signature |
|---|---|
| `NotificationService.send` | `(user_id: int, template: str, context: dict, channel: str = "email") -> Notification` |

## Test helpers

`notifications_app.factories` exports `NotificationFactory` and `UserFactory` for host
tests. Add `factory-boy` to your own test dependency group to use them.
````

**README sync — a structural requirement, not a suggestion.** The repo root's `README.md` above
is the single hand-maintained source. PyPI and npm each read a published package's readme
relative to *its own* project root (`backend/`, `frontend/`), never a monorepo's repo root two
directories up — so `backend/README.md` and `frontend/README.md` must exist as real,
byte-identical **copies** of the root file, or the registry page shows no description at all
(appkit's own v1.0.0 through v2.0.0 all shipped this way, undetected, until a human noticed both
registry pages showed no description at all — see `docs/CONTRACT.md` §22; CI now catches it for
every release after that one). Practically:

- `backend/pyproject.toml` declares `readme = "README.md"` (relative to `backend/`, i.e.
  `backend/README.md` — never `"../README.md"`, see §3.1's own note on why that path silently
  fails).
- A single Make target regenerates both copies: `cp README.md backend/README.md && cp README.md
  frontend/README.md`. Run it — and commit both files — every time the root `README.md` changes.
- CI's `readme-contract` job (§10.1) fails the build if either copy has drifted from the root,
  the same "committed artifact must match a fresh generation" pattern §12 uses for
  `schema.yml`/`schema.d.ts`.
- Add `[project.urls]` (Homepage/Repository/Changelog, §3.1) and `package.json`'s
  `homepage`/`bugs` fields alongside the readme fix — free, and otherwise both registry pages
  show no way back to the repo at all.
- **Both formatters reformat Markdown by default and will fight the sync requirement.** The
  moment `backend/README.md`/`frontend/README.md` exist, `ruff format` (Python code fences) and
  Prettier (the Markdown prose itself — italic-marker style, table-column padding) both want to
  rewrite them — differently from each other and from the root file, which breaks the
  byte-identical copy the `readme-contract` check requires. Exclude both copies from both tools:
  `[tool.ruff] extend-exclude = ["README.md"]` in `backend/pyproject.toml` (§3.1), and
  `frontend/README.md` added to `.prettierignore`. Found live wiring this up for appkit's own
  v2.0.1 — do this before the first `make check`/`npm run lint` after adding either copy, not
  after CI reports it.

## Recommended periodic schedule (optional)

```
notifications_cleanup — daily at 03:00 — notifications_app.tasks.cleanup_old_notifications
```

This is a recommendation, not something that auto-registers — the host creates the actual
`django_celery_beat` schedule entry, see `BASE-DESIGN.md` §6.

## Suggested Jazzmin icon

`fas fa-bell` — add under `JAZZMIN_SETTINGS["icons"]["notifications_app.Notification"]`.

## Installation — frontend

```bash
npm install @hjtdev/appkit                                    # if not already installed
npm install "github:yourorg/notifications-app#v1.4.2:frontend"
```

`@hjtdev/appkit` is a registry install — one package, one name, regardless of which org is
building the app package that depends on it. This app's own frontend half, by contrast, is
whatever this template's own author chooses to publish (a git subdirectory install, shown here,
or its own registry package) — appkit does not prescribe it.

## Usage — add this app's basePath to the shared provider, then import hooks from the package root

**basePath key: `notifications`** — add it to the `basePaths` map on the `ApiClientProvider`
every installed app shares (one provider for the whole host, mounted once — see
`INTEGRATION-GUIDE.md` §2 step 11):

```tsx
// frontend/app/providers.tsx — one-time wiring per host, one basePaths entry per app
import { ApiClientProvider } from "@hjtdev/appkit";
import { apiClient } from "@/lib/api-client";

<ApiClientProvider
  client={apiClient}
  basePaths={{
    // ...entries for already-installed apps stay here
    notifications: "/api/v1/notifications",
  }}
>
  {children}
</ApiClientProvider>;
```

```tsx
import { useNotifications, useSendNotification } from "notifications-app";

function NotificationBell() {
  const { data: notifications } = useNotifications();
  const { mutate: send } = useSendNotification();
  // ...
}
```

Requires the host's `@tanstack/react-query` `QueryClientProvider` to already be mounted
(it is, by default, in the scaffold's `frontend/lib/query-client.ts` — see
`BASE-DESIGN.md` §3) and `appkit`'s `ApiClientProvider` mounted above wherever these hooks
are used, with the `notifications` key above present in its `basePaths` map (see
`APP-DESIGN.md` §12's "SDK-to-host client contract"). No further frontend configuration
needed.
````

An app that ships without every one of these sections isn't done — see §11's release checklist, and §10's CI job that fails when the README's declared throttle scopes don't match the scopes actually present in the code.

## 9. Security Checklist

An app — or a change to one — isn't complete until each of these has been explicitly checked, not assumed:

**Application layer**
- No unauthenticated access to write endpoints unless explicitly intended.
- Object-level permission checks on top of class-level ones, to prevent one user reaching another user's object by ID (IDOR) — with a test per §7.4.
- Serializers used for writes list fields explicitly — never a blanket `fields = "__all__"` on anything user-writable.
- Sensitive fields (tokens, internal IDs, password hashes) are never exposed in a serializer's read output.
- No raw SQL without parameterization; no string-built queries. (`ruff`'s `S` rules catch most of this automatically now — see §3.1.)
- File uploads (if any) validate type and size server-side, not just client-side.
- No secrets or keys hardcoded — everything sensitive comes through `decouple.config(...)`, documented in the README `.env` block.
- Rate limiting (§4) and admin-vs-user permission separation (§5) are both in place, not deferred to "later."

**Supply chain**
- `pip-audit` (backend) and `npm audit --audit-level=high` (frontend) pass — both are CI jobs, see §10.
- No new dependency added without a look at what it pulls in transitively; `uv tree` shows the answer.
- Dependency ranges follow §1.1 — CI's `resolution-matrix` job proves the low end actually works.

The frontend-specific checklist lives in §12.

## 10. Continuous Integration

Every checklist in this document is worthless if a human has to remember to run it. CI is what turns them into gates. The design goal is that **an app repo's own workflow file is ~10 lines** — all real logic lives in one org-level reusable workflow, so improving CI once improves it for every app.

### 10.1 The org-level reusable workflow

Lives in a dedicated repo: `yourorg/.github`, at `.github/workflows/app-package-ci.yml`.

```yaml
name: app-package-ci

on:
  workflow_call:
    inputs:
      package-name:        # importable module name, e.g. notifications_app
        required: true
        type: string
      python-version:
        type: string
        default: "3.14"
      node-version:
        type: string
        default: "22"
      has-frontend:
        type: boolean
        default: true
      coverage-threshold:
        type: number
        default: 85
      publish-npm:
        # Publishes frontend/ to the npm registry on a v* tag push, via OIDC trusted publishing
        # — no stored token, no `secrets:` entry needed for this. false by default: an app
        # package that ships its frontend half by git tag (INTEGRATION-GUIDE.md §2 step 4) never
        # sets this. See §11.1's one-time bootstrap before flipping it on for the first time.
        type: boolean
        default: false
    secrets:
      ORG_READ_TOKEN:
        required: false   # only needed if this app depends on a private shared toolkit

jobs:
  # ---------------------------------------------------------------- backend
  backend-quality:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v5
        with:
          enable-cache: true
          cache-dependency-glob: backend/uv.lock
      - run: uv sync --locked
        working-directory: backend
      - run: uv run ruff check --output-format=github .
        working-directory: backend
      - run: uv run ruff format --check .
        working-directory: backend
      - run: uv run mypy src
        working-directory: backend

  backend-tests:
    runs-on: ubuntu-latest
    services:
      postgres:
        image: postgres:17-alpine
        env:
          POSTGRES_PASSWORD: postgres
          POSTGRES_DB: test_db
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
      REDIS_URL: redis://localhost:6379/0
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v5
        with:
          enable-cache: true
          cache-dependency-glob: backend/uv.lock
      - run: uv sync --locked
        working-directory: backend
      - name: Missing migrations check
        run: uv run python -m django makemigrations --check --dry-run
        working-directory: backend
        env:
          DJANGO_SETTINGS_MODULE: tests.backend.settings
      # Same pattern as the migrations check above, one line up: the committed artifact must
      # match what the code generates. Catches "serializer changed, schema.yml wasn't
      # regenerated" — see §12, "Generated types". No DB, no frontend toolchain needed here.
      - name: Committed schema.yml must match a fresh generation
        run: |
          uv run python manage.py spectacular --file /tmp/schema.yml --fail-on-warn
          diff -u schema.yml /tmp/schema.yml \
            || { echo "::error::schema.yml is stale — run 'manage.py spectacular --file schema.yml' and commit it. See APP-DESIGN.md §12."; exit 1; }
        working-directory: backend
        env:
          DJANGO_SETTINGS_MODULE: tests.backend.settings
      - name: pytest
        run: uv run pytest -n auto --cov-fail-under=${{ inputs.coverage-threshold }}
        working-directory: backend

  # Proves the DECLARED ranges work, not just the locked versions — see §3.4
  resolution-matrix:
    runs-on: ubuntu-latest
    strategy:
      fail-fast: false
      matrix:
        resolution: [lowest-direct, highest]
    services:
      postgres:
        image: postgres:17-alpine
        env: { POSTGRES_PASSWORD: postgres, POSTGRES_DB: test_db }
        options: >-
          --health-cmd pg_isready --health-interval 10s
          --health-timeout 5s --health-retries 5
        ports: ["5432:5432"]
    env:
      POSTGRES_HOST: localhost
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v5
      - run: uv sync --resolution ${{ matrix.resolution }} --upgrade
        working-directory: backend
      - run: uv run pytest -n auto --no-cov
        working-directory: backend

  # Proves the built wheel actually contains templates/locale/static — §2
  wheel-smoke-test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v5
      - run: uv build
        working-directory: backend
      - name: Install the wheel into a clean env and import it
        working-directory: backend
        run: |
          uv venv /tmp/smoke
          uv pip install --python /tmp/smoke/bin/python dist/*.whl
          /tmp/smoke/bin/python -c "import ${{ inputs.package-name }}; print('import ok')"
      - name: Assert package data shipped
        working-directory: backend
        run: |
          python - <<'PY'
          import glob, sys, zipfile
          whl = glob.glob("dist/*.whl")[0]
          names = zipfile.ZipFile(whl).namelist()
          missing = [
              kind for kind, pat in (("templates", "/templates/"), ("locale", ".mo"))
              if not any(pat in n for n in names)
          ]
          if missing:
              sys.exit(f"wheel is missing package data: {missing} — check MANIFEST.in")
          print("package data ok")
          PY

  security-audit:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v5
      # --no-default-groups, NOT --no-dev: --no-dev is only an alias for --no-group dev and
      # leaves the "test" group (pytest and friends) in the audited set — the same defect
      # as the prod Docker builder, see BASE-DESIGN.md §4.2.
      # --no-hashes: with hashes present, pip-audit's internal pip install switches into
      # hash-checking mode, which is fragile against uv.lock/PyPI hash drift and is
      # redundant anyway — hash integrity is already uv's job via `uv sync --locked`.
      # Confirmed empirically on a real CI runner: a wheel's hash in uv.lock disagreed with
      # what PyPI currently serves for that exact file, failing pip-audit's hash check even
      # though `uv sync --locked` installed correctly from the same lockfile elsewhere in
      # the same run.
      - run: uvx pip-audit --strict --no-deps -r <(uv export --locked --no-default-groups --no-hashes --format requirements-txt)
        shell: bash
        working-directory: backend

  # ---------------------------------------------------------------- frontend
  frontend:
    if: ${{ inputs.has-frontend }}
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: ${{ inputs.node-version }}
          cache: npm
          cache-dependency-path: frontend/package-lock.json
      - run: npm ci
        working-directory: frontend
      # Same "committed artifact must match a fresh generation" pattern as backend-tests'
      # schema.yml check above — this half needs only Node, so it lives here rather than
      # growing a Python dependency into the frontend job. Catches "schema.yml changed,
      # schema.d.ts wasn't regenerated" — see §12, "Generated types".
      - name: Committed schema.d.ts must match a fresh generation
        run: |
          npm run generate:types
          git diff --exit-code src/schema.d.ts \
            || { echo "::error::schema.d.ts is stale — run 'npm run generate:types' and commit it. See APP-DESIGN.md §12."; exit 1; }
        working-directory: frontend
      - run: npx tsc --noEmit
        working-directory: frontend
      - run: npm run lint
        working-directory: frontend
      - run: npm run test -- --run --coverage
        working-directory: frontend
      - run: npm audit --audit-level=high
        working-directory: frontend
      - run: npm run build
        working-directory: frontend

  # ---------------------------------------------------------------- contract gates
  version-lockstep:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: pyproject, package.json and CHANGELOG must agree
        run: |
          PY=$(grep -m1 '^version' backend/pyproject.toml | sed 's/.*"\(.*\)"/\1/')
          JS=$(node -p "require('./frontend/package.json').version")
          # Anchored to the CHANGELOG's own version heading, NOT a bare numeric grep — an
          # unanchored `grep -oE '[0-9]+\.[0-9]+\.[0-9]+'` matches the first x.y.z-shaped string
          # in the file, which for a Keep a Changelog document is the changelog format's own
          # "keepachangelog.com/en/1.1.0/" preamble link, producing a false mismatch on every
          # release.
          CL=$(grep -m1 -oE '^## \[[0-9]+\.[0-9]+\.[0-9]+\]' CHANGELOG.md | grep -oE '[0-9]+\.[0-9]+\.[0-9]+')
          echo "pyproject=$PY package.json=$JS changelog=$CL"
          test "$PY" = "$JS" && test "$PY" = "$CL" \
            || { echo "::error::version mismatch — see APP-DESIGN.md §11"; exit 1; }
      - name: On a tag, the tag must match too
        if: startsWith(github.ref, 'refs/tags/v')
        run: |
          PY=$(grep -m1 '^version' backend/pyproject.toml | sed 's/.*"\(.*\)"/\1/')
          test "v$PY" = "${GITHUB_REF_NAME}" \
            || { echo "::error::tag ${GITHUB_REF_NAME} != version v$PY"; exit 1; }

  no-inter-app-imports:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Backstop grep for sibling app imports
        run: |
          if grep -rnE '^\s*(from|import)\s+[a-z_]+_app' backend/src \
               --include='*.py' \
               | grep -v '${{ inputs.package-name }}'; then
            echo "::error::app package imports another app package — see APP-DESIGN.md §6"
            exit 1
          fi
      - name: Factories must not be imported by production code
        run: |
          if grep -rn 'factories' backend/src --include='*.py' \
               | grep -v 'factories.py'; then
            echo "::error::factories.py is a test-only surface — see APP-DESIGN.md §7.3"
            exit 1
          fi

  readme-contract:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Every throttle_scope in code appears in README
        run: |
          fail=0
          for scope in $(grep -rhoE 'throttle_scope\s*=\s*"[^"]+"' backend/src \
                          | sed 's/.*"\(.*\)"/\1/' | sort -u); do
            grep -q "$scope" README.md || { echo "::error::scope $scope missing from README"; fail=1; }
          done
          exit $fail

  # ---------------------------------------------------------------- publish
  # Only runs when the calling workflow opts in with publish-npm: true, and only on a v* tag —
  # never on a plain push to main or a PR. id-token: write is what makes OIDC trusted publishing
  # possible; there is no NPM_TOKEN anywhere in this job. Requires npm >=11.5.1 (bundled with a
  # sufficiently recent Node 22/24 actions/setup-node release) and a one-time manual bootstrap
  # publish + Trusted Publisher link on npmjs.com before the first tag — see §11.1.
  publish-npm:
    if: inputs.publish-npm && startsWith(github.ref, 'refs/tags/v')
    needs: [frontend]
    runs-on: ubuntu-latest
    permissions:
      id-token: write
      contents: read
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: ${{ inputs.node-version }}
          registry-url: https://registry.npmjs.org
      - run: npm ci
        working-directory: frontend
      # Skips cleanly, rather than failing, if this exact name@version is already on the
      # registry. The release that bootstraps trusted publishing always hits this: the very
      # first publish has to happen by hand, before trusted publishing can even be configured,
      # for the SAME version this tag is about to push — without this check, that one release's
      # tag would always fail this job with npm's "cannot publish over previously published
      # version," the opposite of the "tag only after CI is green" workflow this supports.
      - name: Skip if this version is already published
        id: check
        working-directory: frontend
        run: |
          NAME=$(node -p "require('./package.json').name")
          VERSION=$(node -p "require('./package.json').version")
          if npm view "$NAME@$VERSION" version >/dev/null 2>&1; then
            echo "already-published=true" >> "$GITHUB_OUTPUT"
          else
            echo "already-published=false" >> "$GITHUB_OUTPUT"
          fi
      - run: npm publish --access public --provenance
        if: steps.check.outputs.already-published == 'false'
        working-directory: frontend
```

### 10.2 What an app repo actually commits

**Every app package repo in this ecosystem is public and publishes both halves to a public
registry, automatically, on tag push.** That is the default shape, not an opt-in extra a package
adds later — a new app repo is public from creation, registers a PyPI project and an npm package
before its first real tag, and its `ci.yml` looks like this from day one:

```yaml
# .github/workflows/ci.yml
name: CI
on:
  push:
    branches: [main]
    tags: ["v*"]
  pull_request:

# id-token: write is required the moment publish-npm/publish-pypi exist at all — see the
# permissions block below.
permissions:
  contents: read
  id-token: write

jobs:
  ci:
    uses: yourorg/.github/.github/workflows/app-package-ci.yml@main
    with:
      package-name: notifications_app
      coverage-threshold: 85
      publish-npm: true
    secrets: inherit

  # PyPI publish CANNOT live in app-package-ci.yml — see the note below this template. Every
  # package that publishes to PyPI commits this exact job, verbatim except for
  # `packages-dir`/`environment` if the package's own layout differs from backend/.
  publish-pypi:
    if: startsWith(github.ref, 'refs/tags/v')
    needs: [ci]
    runs-on: ubuntu-latest
    environment: publish-pypi
    permissions:
      id-token: write
      contents: read
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v5
        with:
          python-version: "3.14"
      - run: uv build
        working-directory: backend
      - uses: pypa/gh-action-pypi-publish@release/v1
        with:
          packages-dir: backend/dist
          skip-existing: true
```

**Before the first tag, register the name on both registries and wire the trusted publishers —
this is not optional bootstrap-later work, it's part of creating the repo:**

1. Check the desired name is free on **both** PyPI and npm before committing to it anywhere in
   the code (`pyproject.toml`, `package.json`, docs, CI). A collision on either registry (as
   happened to appkit on both — `docs/CONTRACT.md` §22) forces a prefixed name after the fact,
   which is a breaking rename once anything has shipped. Cheap to check up front, expensive to
   fix later.
2. On PyPI: register a **pending** trusted publisher (Publishing → Add a new pending publisher)
   naming this repo, `ci.yml`, and a chosen environment name (e.g. `publish-pypi`) — this can be
   done before the project exists at all; the first successful tag run creates it.
3. On npm: the package must exist first (trusted publishing can't bootstrap a brand-new npm
   package the way PyPI's pending publishers can) — `cd frontend && npm publish --access public`
   once, by hand, then on npmjs.com open the package's Settings → Trusted Publisher and link this
   repo + `ci.yml`. If that config names a specific GitHub environment, add
   `environment: <that name>` to `publish-npm`'s call via the reusable workflow's
   `npm-environment` input (default: `"publish-npm"`) — an environment named in npm's config that
   doesn't also exist as a real GitHub environment on this repo, and isn't set on the job, fails
   every publish with a claim mismatch.
4. Create both GitHub environments named above (Settings → Environments, no protection rules
   needed) — PyPI and npm both reject a token whose `environment` claim doesn't match one that
   actually exists on the repo.
5. Add the package's real README (§8) at `README.md`, `backend/README.md`, and
   `frontend/README.md` before the first publish — see §8's README-sync note. A first release
   with a real README costs nothing; fixing it later needs a whole new version, since neither
   registry lets a published release's description be edited after the fact.

**Why the template above has a top-level `permissions:` block.** A reusable workflow's job can
only *downscope* the permissions the calling workflow grants, never escalate past them — the
`publish-npm` job (§10.1) requests `id-token: write` for OIDC, so if the repo's default
`GITHUB_TOKEN` permissions are the (increasingly common) restrictive `read` default, the whole
`workflow_call` fails **validation before any job runs at all** — a zero-job `startup_failure`,
not a red `publish-npm` job specifically, discovered live wiring this up for appkit v1.0.1. A
package that sets neither `publish-npm: true` nor commits its own `publish-pypi` job doesn't need
this block.

**Publishing the backend half to PyPI cannot use `publish-npm`'s pattern — the job has to live in
the CALLER's `ci.yml`, not in `app-package-ci.yml`.** This is not a style choice; it's forced by
how each registry's trusted publisher validates a `workflow_call` job:

- **npm** validates the *calling* workflow's filename — so `publish-npm` living inside
  `app-package-ci.yml` is exactly right; every app registers `ci.yml` as its trusted publisher
  and it works no matter which app's `ci.yml` triggered the run.
- **PyPI** validates the *callee's* `job_workflow_ref` OIDC claim — for a `workflow_call` job that
  resolves to `app-package-ci.yml` itself, never the caller. A `publish-pypi` job placed in the
  shared workflow would make every app package share one PyPI trusted-publisher identity, which
  isn't how PyPI's model works at all (a trusted publisher is registered per PyPI *project*,
  naming one specific repo + workflow file). PyPI's own docs state the limitation outright:
  reusable workflows cannot be the workflow named in a Trusted Publisher.

So a `publish-pypi` job is a per-repo addition to `ci.yml` itself — see appkit's own
`.github/workflows/ci.yml` for the concrete job (`environment: publish-pypi`,
`pypa/gh-action-pypi-publish@release/v1`, gated on `needs: [ci]` so it only runs after the shared
workflow is green). Register the trusted publisher on pypi.org against that exact repo + workflow
filename + environment before the first tag that should publish.

### 10.3 Branch protection & automation

- Require `backend-quality`, `backend-tests`, `frontend`, `version-lockstep`, and `no-inter-app-imports` to pass before merge to `main`. The rest (`resolution-matrix`, `security-audit`) can be advisory at first and promoted once they're stable. The two generated-types diff checks (§12) are steps inside `backend-tests` and `frontend` respectively, not separate jobs — requiring those two jobs already requires them.
- **Renovate** (preferred over Dependabot here, because it handles the `git+...@vX.Y.Z` tag pattern and `uv.lock` better) opens PRs for: `uv.lock` updates within declared ranges, `package-lock.json`, the pinned Docker base image digests in `playground/`, and pre-commit hook `rev`s. Group patch updates into one weekly PR; keep majors separate so they get read.
- **Conventional Commits** (`feat:`, `fix:`, `feat!:`) make the semver decision in §11 mechanical instead of a judgement call, and let `git-cliff` generate the `CHANGELOG.md` section from history. Enforce with a `commitlint` job or a `commit-msg` pre-commit hook.

## 11. Release Workflow

### 11.1 Order of operations

1. **Green CI on `main`.** Not "tests passed locally" — the full workflow from §10, including `resolution-matrix` and `wheel-smoke-test`. These two are the ones that catch the failures a host would otherwise discover for you.
2. **Playground verification** (§11.2) — prove the two halves work together against a real host before tagging.
3. **Decide the bump** from the Conventional Commit history: any `!`/`BREAKING CHANGE` → major; any `feat:` → minor; otherwise patch. Remember from §6 that a changed signal payload, a changed `services.py` signature, or a renamed factory is a **major**, even if the diff looks tiny.
4. **Bump the version in three places together:** `backend/pyproject.toml`, `frontend/package.json`, and a new `CHANGELOG.md` section. CI's `version-lockstep` job fails the build if they disagree, so this cannot be forgotten silently. Generated types (§12) make this rule enforceable rather than aspirational: a serializer change now mechanically produces a `schema.yml` diff and, from that, a `schema.d.ts` diff — and `backend-tests`/`frontend` (§10.1) refuse to pass until both are committed. There is no longer a way to ship a backend shape change in a commit whose frontend types weren't regenerated alongside it, which is exactly the class of "tiny diff, actually a major" mistake step 3 above warns about.
5. **Update `README.md`'s config block** (§8) if settings, `.env` keys, throttle scopes, URLs, signal payloads, service signatures, factories, or exported hooks changed.
6. **Commit, tag `vX.Y.Z`** (one tag covers both halves), push the tag. The tag push re-runs CI with the tag-match assertion active — and, for an app publishing its frontend half to npm (`publish-npm: true`, §10.1) and/or its backend half to PyPI (a `publish-pypi` job in `ci.yml`, §10.2), publishes both automatically via their respective OIDC trusted-publish steps. Nothing to run by hand once bootstrapped.
7. **In a consuming project**, follow `INTEGRATION-GUIDE.md` §2's upgrade path.

**One-time bootstrap, before the first tag that should publish to npm:** trusted publishing can
only be configured on a package that already exists, so the very first publish has to happen by
hand: `cd frontend && npm run build && npm publish --access public`. Then, on npmjs.com, open
the package's Settings → Trusted Publisher and link this repo and the workflow filename that
calls `app-package-ci.yml` with `publish-npm: true`. Every tag pushed after that publishes from
CI with no stored credential at all.

**PyPI needs no equivalent bootstrap.** A PyPI *pending* trusted publisher can be registered
against a project name that doesn't exist yet — the first tag whose `publish-pypi` job succeeds
creates the project directly from CI, no manual `twine upload`/`uv publish` first. Only the
GitHub environment the job declares (e.g. `publish-pypi`) has to exist ahead of time
(`gh api repos/OWNER/REPO/environments -X PUT` or the repo's Settings → Environments UI, no
protection rules required) — PyPI rejects the OIDC token with `invalid-pending-publisher` if the
environment name in the pending publisher's config doesn't match one that actually exists on the
repo.

### 11.2 The `playground/`

`playground/` is a minimal Django + Next.js host living in the app's own repo, with both halves linked by **path**, not by tag. Use `[tool.uv.sources]` for this rather than an editable install flag — it redirects where a dependency resolves from without changing the dependency declaration, so the same `pyproject.toml` line works for both dev and release:

```toml
# playground/backend/pyproject.toml
[project]
dependencies = ["notifications-app"]

[tool.uv.sources]
notifications-app = { path = "../../backend", editable = true }
```

```bash
cd playground/backend && uv sync         # picks up your working tree, live
cd playground/frontend && npm install    # package.json uses "file:../../frontend"
docker compose -f playground/docker-compose.yml up
```

This is what catches "the hook's shape drifted from the API's actual response" before a host project does — the single highest-value pre-release check, because it's the one thing no unit test on either half can prove.

**`playground/frontend`, `playground/demo-sdk` (or an app's own SDK-under-test), and `appkit`'s
own `frontend/` need an npm workspace, not three independent `npm install`s.** Without one, any
package the SDK and the host app both depend on (`@tanstack/react-query` is the concrete case
that bit this — see the peer-dependency note above) can install as two separate physical copies,
breaking React Context identity at runtime with no build-time signal. `playground/package.json`
declaring `"workspaces": ["frontend", "demo-sdk"]` (or the app's own SDK directory) is what
hoists and dedupes them; `appkit`'s own `frontend/` stays outside that workspace and reached by
`file:../../frontend`, same as before — a workspace member can still depend on a path outside
the workspace root by `file:` path.

**If the playground's frontend uses Next.js with Turbopack (the default since Next 15), two
things need explicit configuration that nothing about this setup makes obvious, both found live
building this package's own `playground/` (full detail: `playground/FINDINGS.md`):**

1. **`turbopack.root` in `next.config.ts` must be pinned to the true common ancestor of the npm
   workspace root *and* `appkit`'s own `frontend/`** — Turbopack's `root` is a hard compilation
   boundary ("files outside of the workspace root are not compiled"), and its own nearest-
   lockfile auto-inference has no correct single answer once there's more than one
   `package-lock.json` in the tree (which there always will be — one for `appkit`'s own
   `frontend/`, one for the playground's npm workspace). Get `root` wrong and Turbopack reports
   `"Module not found: Can't resolve 'appkit'"` even though plain Node resolves the exact same
   specifier from the exact same directory without error.
2. **A page that calls a hook needing `<Providers>` context must export `dynamic =
   "force-dynamic"` from a *server*-component file** (`page.tsx`, not a `"use client"` file it
   renders) — otherwise `next build`'s static-generation pass prerenders the client component in
   a worker with no provider mounted, failing with `"No QueryClient set, use QueryClientProvider
   to set one"`. The directive is silently ignored when placed directly in a `"use client"` file;
   split the page into a thin server wrapper exporting `dynamic` and a separate client component
   it renders.

### 11.3 `CHANGELOG.md` format

Keep a Changelog, so "did v1.5.0 change my throttle scopes?" is answerable at a glance:

```markdown
# Changelog

## [1.5.0] — 2026-08-14

### Added
- `useNotificationPreferences` hook and matching `/preferences/` endpoint.

### Changed
- `notifications_list` throttle default raised from 30/min to 60/min.
  **Host action:** update `DEFAULT_THROTTLE_RATES` if you copied the old value.

### Fixed
- N+1 query on the list endpoint when `channel` was prefetched.
```

Any entry that requires the host to change something says so explicitly, under a **Host action:** line. That line is the difference between a smooth upgrade and a mystery.

## 12. Frontend SDK Contract

The `frontend/` half of a package is a small SDK — typed hooks and a fetcher, nothing more. It follows the same decoupling discipline as the backend half, adapted to React:

- **One entrypoint.** Everything a host can use is exported from `frontend/src/index.ts`. Nothing under `hooks/`, `api/`, or `types.ts` is imported directly by a host — only through `index.ts`. This keeps the internal file layout free to change without it being a breaking change.
- **Peer dependencies, not bundled ones.** `react`, `@tanstack/react-query` (or `axios`, whichever the app actually uses), and **`appkit`** are declared as `peerDependencies`, never as regular `dependencies`. Bundling any of them would mean a host ends up with two copies — two copies of React, two `QueryClient` instances, or two `appkit`s each holding their own React context, so a host-mounted `ApiClientProvider` and an SDK's `useApiClient` resolve against different instances and the hook sees `null`. Same failure shape as the React/react-query case, for the same reason. The host's own copy, already provided via the scaffold's `frontend/lib/query-client.ts` (see `BASE-DESIGN.md` §3) and `appkit`'s `ApiClientProvider` (`INTEGRATION-GUIDE.md` §2), is what every hook plugs into.
  **The same failure reproduces from a `devDependency`, not just a bundled one — found building `appkit`'s own `playground/` (`playground/FINDINGS.md`, Phase 6).** An SDK's package.json needs `react`/`@tanstack/react-query` as real installed packages for its own local `tsc` type-checking, and it's tempting to list them under `devDependencies` for that. Without a shared npm **workspace** linking the SDK and the host app that consumes it, this installs a second, real, physically separate copy — `useQuery()` inside the SDK's *compiled* code resolves it from the SDK's own `node_modules`, not the host's, so it reads a different `React.Context` than the host's mounted `QueryClientProvider` created. Symptom: `"No QueryClient set, use QueryClientProvider to set one"` despite a provider correctly mounted — reproduced live with `demo-sdk`'s own `@tanstack/react-query` devDependency, fixed only once `playground/` became an npm workspace so the dependency hoisted and deduped. If a host and an SDK aren't in the same workspace, keep any package like this out of the SDK's `devDependencies` entirely (typecheck against the peer range via `@types/*` alone, or accept untyped `tsc` gaps) rather than risk this.
- **No inter-app frontend dependencies — with the same named exception as §1.1.** Exactly like the backend half (§6, §1.1), a package's `frontend/` must never depend on or import another reusable app's frontend package. If two apps' UIs need to be combined, that composition happens in the host's own `frontend/` code — see `INTEGRATION-GUIDE.md` §4. `appkit` is the one declared exception, on both halves, for the same reason: it's an explicit, versioned `peerDependency`, not an ambient assumption about a sibling app.
- **Typed end to end, strictly.** `tsconfig.json` sets `"strict": true`; `types.ts` exports the request/response shapes the hooks use, so a host gets full type safety with no separate `@types` package and no `any`. Those shapes are **generated** from the app's own OpenAPI schema, not hand-written — see "Generated types" below.
- **The concrete HTTP client is injected, never imported.** An app's `frontend/` can't `import` the host's `frontend/lib/api-client.ts` — that file lives in the host project, not in the publishable package, and the SDK has to build and ship standalone (§1). See "SDK-to-host client contract" below for the mechanism.

```json
// frontend/package.json (excerpt)
{
  "name": "notifications-app",
  "version": "1.4.2",
  "type": "module",
  "main": "./dist/index.js",
  "types": "./dist/index.d.ts",
  "exports": { ".": { "types": "./dist/index.d.ts", "import": "./dist/index.js" } },
  "files": ["dist"],
  "peerDependencies": {
    "react": ">=18",
    "@tanstack/react-query": ">=5",
    "@hjtdev/appkit": ">=1.0.0 <2.0.0"
  },
  "devDependencies": {
    "openapi-typescript": "^7.13.0"
  },
  "scripts": {
    "generate:types": "openapi-typescript ../backend/schema.yml -o src/schema.d.ts",
    "build": "tsc -p tsconfig.build.json",
    "test": "vitest",
    "lint": "eslint src"
  }
}
```

The `exports` map matters: it's what stops a host from importing `notifications-app/dist/api/manager` and coupling itself to internals, which the "one entrypoint" rule exists to prevent. Declaring only `"."` makes the rule enforced by Node's resolver rather than by convention.

### Generated types

`types.ts` matching the backend's serializers exactly (the rule stated above) used to depend on a human keeping two files in sync by hand — the only thing that ever caught drift was clicking through the playground (§11.2, `CLAUDE-CODE-GUIDE-APP.md` Phase 6). Since every view already carries a complete `@extend_schema` (§4), `drf-spectacular` already has everything it needs to emit that shape mechanically. Doing so converts "hook returns `undefined` for a field the API sends" (`CLAUDE-CODE-GUIDE-APP.md` §5) from a bug a human usually catches into a diff CI refuses to let through (§10.1).

**The generator is `openapi-typescript` (currently 7.13.0), types only — deliberately not a client generator.** `openapi-fetch` and `orval` both generate a runtime HTTP client (`orval` goes further and generates the react-query hooks themselves); either would replace exactly the hand-written manager-and-hooks layer this section exists to specify, and `orval`'s generated hooks are a different shape than "Manager & hook conventions" below mandates. `openapi-typescript-codegen` is unmaintained in favor of `@hey-api/openapi-ts`, and both are full client generators too — same problem. `openapi-typescript` emits runtime-free `.d.ts` output and nothing else, which is the one degree of automation this architecture actually wants.

**The file split — this is the load-bearing decision:**

- **`src/schema.d.ts` — generated, never hand-edited.** Carries a header comment saying so (openapi-typescript writes one automatically: *"This file was auto-generated... Do not make direct changes to the file."*). Every type lives under `components["schemas"][...]` and `operations[...]` — indexed-access types, not top-level names, because that's what a spec with many operations needs to stay collision-free.
- **`src/types.ts` — hand-written, and stays the SDK's public type surface.** Re-exports narrowed, ergonomic aliases from `schema.d.ts` (`export type Notification = components["schemas"]["Notification"];`), plus everything the schema cannot express — see "What stays hand-written" below. `index.ts`'s "one entrypoint" rule and every existing example in this section are unaffected: hooks and the manager still import from `../types`, never from `../schema.d.ts` directly.

Regeneration has to be safe to run at any time with no review of its own output — that's only true if it writes to a file nobody hand-edits. That's the entire reason for the split.

**The exact command:** `npm run generate:types`, defined in `frontend/package.json` above as `openapi-typescript ../backend/schema.yml -o src/schema.d.ts`. `openapi-typescript` is a `devDependency`, never a `dependency` or `peerDependency` — it's build-time tooling that generates a committed file; a host installing the package must never need it.

**Committed, not generated at install time.** Both `backend/schema.yml` and `frontend/src/schema.d.ts` are committed to the repo. A host installs the published package and gets `dist/index.d.ts`, already built from these committed sources — no Python, no `uv`, no Django, no `openapi-typescript`, nothing beyond what `npm install` already pulls. Generating at install time (a `postinstall` hook, say) would put the entire backend toolchain in every host's install path, which is a hard violation of §1's "builds and ships standalone" rule — a host has no `backend/schema.yml` to generate from in the first place, since the app's backend source isn't part of what it installed.

**Where the schema comes from: `manage.py spectacular` against `tests/backend/settings.py` (§7.1), not the playground (§11.2).** Three reasons, in ascending order of importance:

1. It's the same settings module §10.1's `makemigrations --check --dry-run` step already runs under — the CI job below (§10.1) is the same pattern in the same place, not a new mechanism to maintain.
2. Schema generation walks the URLconf and serializer declarations; it never queries the database. It runs in a bare `uv sync`'d checkout in seconds, needing no Postgres, no Redis, no Docker — the playground needs a full `docker compose up`.
3. **The decisive reason:** the playground is a *host*, and a host's schema carries that host's own mount prefix. §12's "SDK-to-host client contract" injects `basePath` at runtime specifically because the mount point is the host's choice, not the app's (`DEFAULT_BASE_PATH` above is a suggestion, not a guarantee). Generating from the playground would bake one arbitrary host's prefix into the shipped types — generating from `tests/backend/settings.py`, whose URLconf exists solely to make the app's own schema generatable standalone, keeps the types mount-agnostic, matching how the manager itself is written.

```bash
# backend/ — regenerate the committed schema
DJANGO_SETTINGS_MODULE=tests.backend.settings uv run python manage.py spectacular \
  --file schema.yml --fail-on-warn

# frontend/ — regenerate the committed types from that schema
npm run generate:types
```

`--fail-on-warn` matters on its own: drf-spectacular warns when it can't cleanly resolve something (an enum name collision, a missing `@extend_schema`), and a schema generated with warnings produces types that are wrong in exactly the way this whole mechanism exists to prevent. A warning-clean run is the bar, not merely a file being produced.

**`COMPONENT_SPLIT_REQUEST = True` is required**, set in `tests/backend/settings.py`'s `SPECTACULAR_SETTINGS` (§7.1) — this is what makes readOnly/writeOnly fields translate correctly. Without it, a single `Notification` component would need every write-only field marked optional-and-ignorable and every read-only field marked as if the client could send it back; a POST body typed from that component would happily let a caller set `id`. With it on, `drf-spectacular` emits two components — `Notification` (response) and `NotificationRequest` (request) — and `openapi-typescript` renders the read-only field as TypeScript's own `readonly` modifier on the response type, entirely absent from the request type; a write-only field appears only on the request type, entirely absent from the response type. No wrapper types, no runtime cost — verified directly: a `ChoiceField`, an `allow_null` field, a `read_only` `id`, a `write_only` field, a nested serializer, and a paginated list view all round-tripped through `manage.py spectacular --fail-on-warn` (zero warnings) and `openapi-typescript` cleanly, producing exactly the shapes described here.

openapi-typescript's own `--read-write-markers` flag was considered and **rejected**: it wraps properties as `id?: $Read<number>` and requires consumers to apply `Readable<T>`/`Writable<T>` helper types to unwrap them. Those marker types would leak into the published SDK's `dist/index.d.ts` and become part of the host-facing API surface — exactly the kind of internal-mechanism leakage §1's decoupling discipline exists to prevent elsewhere in this package. `COMPONENT_SPLIT_REQUEST` solves the same problem at the schema level and produces plain, named types instead.

**Enum stability.** `drf-spectacular` names each `choices` field's value set into its own component (`StatusEnum`, following `ENUM_SUFFIX`'s default) and renders a JSDoc comment listing each choice's label — verified above: a three-value `ChoiceField` produced `type StatusEnum = "active" | "inactive" | "archived";` with the human-readable labels preserved as a comment. Two fields sharing the same choice values under different names, or the same field name with different choice sets across serializers, make the naming unstable (`drf-spectacular` appends disambiguating suffixes and warns). An unstable component name is an unstable *type* name in `schema.d.ts`, which would make `schema.d.ts` churn on every regeneration for no functional reason — noisy enough that a team stops trusting the CI diff gate below. Set `ENUM_NAME_OVERRIDES` in `SPECTACULAR_SETTINGS` the moment `--fail-on-warn` flags a collision; don't wait for it to become a habit of ignoring warnings.

**What stays hand-written**, in `types.ts`, because nothing in an OpenAPI schema can express it — and it's shorter than it used to be, because two of the three things that used to live here now come from `appkit` instead:

- ~~`HttpClient`~~ — moved to `appkit`. Re-exported from this app's own `types.ts` for convenience (`export type { HttpClient } from "@hjtdev/appkit"`), never redeclared.
- ~~The error envelope~~ — moved to `appkit` as `ApiErrorEnvelope` / `ApiErrorCode`. Same reasoning as before (produced by the exception handler at request-handling time, not declared on any serializer, so `drf-spectacular` has no field to introspect) — it just now has one definition instead of one per app.
- Whatever's left is genuinely app-specific: request/response shapes the schema can't express, if any. Most apps have nothing left to hand-write here at all.

### SDK-to-host client contract

Every app's SDK has to make HTTP calls, but its `manager.ts` can't `import { apiClient } from "frontend/lib/api-client"` — that file is project-owned code living in the host's repo (`BASE-DESIGN.md` §3), and an app package builds and ships as a standalone `dist/` with no dependency on any particular host's file layout (§1). The mechanism is runtime dependency injection through a React context, not a shared import: the host constructs its own client — the `apiClient` instance from `frontend/lib/api-client.ts` — and hands it to every installed SDK via **one shared provider that every app depends on**, rather than a bespoke provider each app ships for itself.

That shared provider is `appkit`'s `ApiClientProvider` / `useApiClient`, not something this app defines. `appkit` owns the `HttpClient` *interface* and the provider/hook pair — it never owns a client *implementation*. The host still constructs the real `ApiClient` (reads `NEXT_PUBLIC_API_URL`, decides the credentials mode, handles CSRF — all host configuration, `BASE-DESIGN.md` §3) and hands that instance to `ApiClientProvider`. If `appkit` shipped its own client implementation instead of just the interface, that implementation would have to read the host's env and configuration itself — reintroducing exactly the host-coupling this whole mechanism exists to prevent. **Don't "helpfully" move a client implementation into `appkit`** — the interface-only boundary is deliberate, not an oversight to fix later.

This needs no shared package for the *typing* to work — TypeScript is structurally typed, so the host's concrete `ApiClient` satisfies `HttpClient` by having the right methods, not by declaring that it implements anything — but a shared package is exactly what's needed for the *provider* to work, so a host mounts one `ApiClientProvider` instead of one differently-named provider per installed app:

```ts
// appkit/src/index.ts (excerpt) — for reference; this ships in appkit, not in this app.
// Authoritative signatures: docs/CONTRACT.md §14-§15, frontend/src/client.ts + provider.tsx.
export interface HttpClient {
  get<T>(path: string, init?: RequestInit): Promise<T>;
  post<T>(path: string, body?: unknown, init?: RequestInit): Promise<T>;
  put<T>(path: string, body?: unknown, init?: RequestInit): Promise<T>;
  patch<T>(path: string, body?: unknown, init?: RequestInit): Promise<T>;
  delete<T>(path: string, init?: RequestInit): Promise<T>;
}

export interface ApiClientProviderProps {
  /** Any client satisfying HttpClient — normally the host's frontend/lib/api-client.ts
   *  apiClient, passed in as-is. */
  client: HttpClient;
  /** basePath per installed app, keyed by the app's own namespace (§1.2) — see
   *  "Where basePath comes from now" below. */
  basePaths?: Readonly<Record<string, string>>;
  /** Composable per-request header sources, docs/CONTRACT.md §16 — must be a stable
   *  reference (module scope or useMemo). */
  headerSources?: ReadonlyArray<() => HeadersInit | Promise<HeadersInit>>;
  children: React.ReactNode;
}

export function ApiClientProvider(props: ApiClientProviderProps): React.ReactElement;

/** Called from an app's own api/config.ts, never directly by a host. `key` is this app's
 *  namespace; `defaultBasePath` is what the app's own README suggests if the host's
 *  basePaths map has no entry for `key`. Both arguments required — throws on an empty
 *  defaultBasePath, since there is no host-wide-safe default. */
export function useApiClient(key: string, defaultBasePath: string): { client: HttpClient; basePath: string };
```

Each app's own `frontend/src/api/config.ts` does nothing more than bind its namespace and default to that shared hook:

```ts
// frontend/src/api/config.ts — internal, never exported from index.ts
import { useApiClient } from "@hjtdev/appkit";

export const useNotificationsConfig = () => useApiClient("notifications", "/api/v1/notifications");
```

`useApiClient` throws if called outside an `ApiClientProvider` rather than silently returning `undefined` — deliberate, same reasoning as before: a hook that got `client: undefined` would fail three layers away from the actual mistake, inside a `fetch` call, with an error that says nothing about a missing provider. `ApiClientProvider` and `HttpClient` are exported from `appkit`'s own entrypoint; `useApiClient` is exported too (unlike a per-app config hook, it's meant to be called — indirectly, through each app's `api/config.ts` — by every installed app), but this app's own `useNotificationsConfig` wrapper is not exported from `index.ts` — a host mounts the provider and imports hooks, but never calls a config hook directly.

**Where `basePath` comes from now.** Each app still owns its own default basePath — the mount prefix is the host's choice (`INTEGRATION-GUIDE.md` §3), not the app's. Of the shapes considered, the recommendation is **one root provider carrying a `basePaths` map keyed by namespace**, resolved at the host level once instead of per app:

```tsx
// host frontend/app/providers.tsx — mounted once, not once per installed app
import { ApiClientProvider } from "@hjtdev/appkit";
import { apiClient } from "@/lib/api-client";

<ApiClientProvider
  client={apiClient}
  basePaths={{ notifications: "/api/v1/notifications", payments: "/billing/api" }}
>
  {children}
</ApiClientProvider>;
```

Namespaces are already collision-free per §1.2, so keys can't collide between apps. The trade-off, stated plainly: the key is stringly typed and unenforced by the compiler — a typo in the host's `basePaths` map silently falls back to the app's own default rather than failing to build, and the requests 404 at runtime instead. That's the price of collapsing N providers into one; it's mitigated by documenting the exact key in the app's README (§8) and by INTEGRATION-GUIDE.md §2 making it an explicit wiring step.

Two alternatives were considered and rejected: a `basePath` argument baked into `useApiClient` at each app's own call site removes the host's ability to choose a different mount point at all; a per-app provider prop (each app back to shipping `<NotificationsProvider basePath="...">`) keeps compile-time checking but reinstates the exact provider-nesting problem this design exists to remove. The escape hatch, for the rare app needing a differently-configured client (an auth app on `credentials: "include"`, say): a second `ApiClientProvider` nested deeper in the tree wins for that subtree, same as any React context.

### Manager & hook conventions

Every app's frontend has two layers, mirroring the backend's `views.py` + `services.py` split:

- **The manager** (`api/manager.ts`) is a plain class, instance-based — its constructor takes the `HttpClient` and `basePath` a hook read from context, never a static class reaching for a module-level client, since there is no module-level client to reach for (see "SDK-to-host client contract" above). It's the *only* place a raw HTTP call happens — no `fetch`/`axios` call exists anywhere outside this file. It's typed against `types.ts`, and it's never exported from `index.ts` — a host only ever reaches it indirectly, through a hook.
- **Hooks** (`hooks/*.ts`) are thin `@tanstack/react-query` wrappers around manager methods — never anything more. Each hook calls the app's `useXConfig()` to read the injected `client`/`basePath`, builds the manager with `useMemo` (keyed on `[client, basePath]`, so it isn't reconstructed every render), then wraps `useQuery`/`useMutation` around its methods. A query hook wraps `useQuery` with a stable, namespaced `queryKey` (`["notifications", ...]`, per §1.2); a mutation hook wraps `useMutation` and invalidates the relevant query keys on success. Neither swallows loading/error state — every hook returns the standard react-query result object as-is, so the host UI decides how to render `isLoading`/`isError`, rather than the SDK imposing a spinner or toast opinion. If two hooks share logic (e.g. an error-shape normalizer), factor it into an internal, unexported helper.

```ts
// frontend/src/api/manager.ts
import type { HttpClient, Notification, SendNotificationPayload } from "../types";

export class NotificationsManager {
  constructor(
    private readonly client: HttpClient,
    private readonly basePath: string,
  ) {}

  list(): Promise<Notification[]> {
    return this.client.get<Notification[]>(`${this.basePath}/`);
  }

  send(payload: SendNotificationPayload): Promise<Notification> {
    return this.client.post<Notification>(`${this.basePath}/send/`, payload);
  }
}
```

```ts
// frontend/src/hooks/useNotifications.ts
import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { NotificationsManager } from "../api/manager";
import { useNotificationsConfig } from "../api/config";

export const notificationKeys = {
  all: ["notifications"] as const,
  list: () => [...notificationKeys.all, "list"] as const,
};

export function useNotifications() {
  const { client, basePath } = useNotificationsConfig();
  const manager = useMemo(() => new NotificationsManager(client, basePath), [client, basePath]);

  return useQuery({
    queryKey: notificationKeys.list(),
    queryFn: () => manager.list(),
  });
}
```

```ts
// frontend/src/hooks/useSendNotification.ts
import { useMemo } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { NotificationsManager } from "../api/manager";
import { useNotificationsConfig } from "../api/config";
import { notificationKeys } from "./useNotifications";
import type { SendNotificationPayload } from "../types";

export function useSendNotification() {
  const { client, basePath } = useNotificationsConfig();
  const manager = useMemo(() => new NotificationsManager(client, basePath), [client, basePath]);
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (payload: SendNotificationPayload) => manager.send(payload),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: notificationKeys.all });
    },
  });
}
```

```ts
// frontend/src/index.ts — the only file a host ever imports from; note the
// manager and useNotificationsConfig are never exported here, only the hooks,
// key factories, and types. There is no provider to export — the host mounts
// appkit's ApiClientProvider once, per "SDK-to-host client contract" above.
export { useNotifications, notificationKeys } from "./hooks/useNotifications";
export { useSendNotification } from "./hooks/useSendNotification";
export type { Notification, SendNotificationPayload } from "./types";
export type { HttpClient } from "@hjtdev/appkit";
```

Exporting the `notificationKeys` factory is deliberate: a host sometimes needs to invalidate this app's cache from its own code (after a cross-app action composed in `frontend/app/`, per `INTEGRATION-GUIDE.md` §4). Without the factory, the host hardcodes the key string and silently breaks when the SDK changes it.

### Frontend security checklist

Parallel to the backend checklist in §9 — a frontend half isn't done until each of these is checked, not assumed:

- No sensitive tokens (auth tokens, API keys) stored in `localStorage`/`sessionStorage` from within the package's own code — rely on the host's existing auth/cookie handling rather than the app inventing its own storage. See `BASE-DESIGN.md` §3, "Auth integration" for exactly what the host's own handling consists of (CORS credentials, CSRF trusted origins, the shared `ApiClient`'s credentials default).
- Manager methods never build a URL by concatenating unescaped user input — values always go through the client's param/body encoding, never string-interpolated into a path.
- No `dangerouslySetInnerHTML` with unsanitized data, if the package ships any UI components beyond hooks.
- No hardcoded base URLs, API keys, or secrets anywhere in the package — the base URL always comes from the host's shared client configuration.
- A mutation hook for a destructive or sensitive action (`useDeletePaymentMethod`, `useCreatePayment`) never fires on mount or on a passive render — it only fires from an explicit user action, so a stray re-render can't trigger a real charge or deletion.
- Every manager method and hook is typed against `types.ts` — no `any` on a request/response shape, since a silently wrong type is exactly how a backend contract drifting out from under a hook turns into a runtime bug nobody notices until it's in production.
- `react`, `@tanstack/react-query`, and `appkit` stay `peerDependencies`, never bundled.
- `npm audit --audit-level=high` passes (CI job, §10).
