# INTEGRATION-GUIDE.md — How the Ecosystem Fits Together

This document is the bridge between `BASE-DESIGN.md` (the monorepo scaffold) and `APP-DESIGN.md` (the versioned, read-only app packages). It's written for AI coding agents (Claude Code, Cursor, and similar) working inside a host project — **if you're an agent about to touch this project, read this fully before editing anything.**

## Table of contents

1. [System Overview & Architectural Hierarchy](#1-system-overview--architectural-hierarchy)
2. [App Installation & Wiring Standards](#2-app-installation--wiring-standards)
3. [URL Routing Architecture](#3-url-routing-architecture)
4. [Inter-App Communication (The Mediator Pattern)](#4-inter-app-communication-the-mediator-pattern)
5. [Handling Custom Views & Overrides](#5-handling-custom-views--overrides)
6. [Shared Utilities & Cross-Cutting Concerns](#6-shared-utilities--cross-cutting-concerns)
7. [Dependency Resolution & Troubleshooting](#7-dependency-resolution--troubleshooting)
8. [Keeping `CLAUDE.md` Current](#8-keeping-claudemd-current)
9. [Agent Execution Checklist](#9-agent-execution-checklist)

---

## 1. System Overview & Architectural Hierarchy

```
my-client-project/                     # single monorepo, one git history
├── frontend/                          # Next.js App Router — editable, project-owned
│   ├── lib/query-client.ts            # shared TanStack Query client every installed
│   │                                    frontend app-package's hooks plug into
│   ├── app/                           # pages/components — where cross-app UI
│   │                                    composition happens, see §4
│   └── node_modules/
│       ├── notifications-app/         # READ-ONLY — installed frontend SDK, pinned version
│       ├── payments-app/              # READ-ONLY — installed frontend SDK, pinned version
│       └── ...
├── backend/
│   ├── config/                        # editable, project-owned — settings.py, urls.py,
│   │                                    asgi.py, celery.py, logging.py
│   ├── core/                          # editable, project-owned — the ONLY place allowed
│   │   │                                to import more than one app package together
│   │   ├── signals.py
│   │   ├── services/
│   │   ├── views/                     # subclasses/overrides of app views, see §5
│   │   └── tests/
│   ├── tools/                         # editable, project-owned — shared utilities for
│   │                                    config/ and core/ specifically, see §6
│   ├── templates/                     # editable — override point for app templates, see §5
│   ├── pyproject.toml                 # editable — where `uv add` records app packages
│   ├── uv.lock                        # COMMITTED, machine-generated — never hand-edit
│   └── manage.py
└── backend/.venv/lib/python3.14/site-packages/
    ├── notifications_app/             # READ-ONLY — installed package, pinned version
    ├── payments_app/                  # READ-ONLY — installed package, pinned version
    └── ...
```

**The one rule that matters most: anything under `.venv`/`site-packages` *or* `frontend/node_modules` is read-only.** An agent must never open an installed app package — Python or TypeScript half — and edit its files. Not to fix a bug, not to tweak a default, not "just this once." If something about an installed app needs to change:

| The problem | Where the fix goes |
|---|---|
| Settings, URL mounting, throttle rates, env keys | `backend/config/` — §2 |
| A cross-app backend workflow | `backend/core/` — §4 |
| Cross-app UI composition | `frontend/app/` — §4 |
| Different behavior from one of the app's views/serializers | Subclass in `backend/core/views/` — §5 |
| A different admin experience for the app's model | Proxy model + `ModelAdmin` in `core/` — §5 |
| A different template or static asset | Mirror the namespaced path under `backend/templates/` — §5 |
| A genuine bug or missing feature in the app itself | A change to the app's **own repo**, released as a new version and re-pinned — `APP-DESIGN.md` §11 |

**A second rule, equally absolute: `uv.lock` is machine-generated.** Never hand-edit it, and never edit a dependency line in `pyproject.toml` without re-running `uv lock` (or using `uv add`, which does both). CI runs `uv sync --locked`, which fails when the two disagree — that failure is the guardrail working, not a CI problem to route around.

Everything under `backend/` and `frontend/` is fully editable, project-owned code — there's no scaffold/project ownership split to worry about, the way there might be in a template that gets re-pulled. This monorepo *is* the project from the moment it's cloned.

## 2. App Installation & Wiring Standards

When asked to add a new app package, follow this protocol exactly, in order. Most apps have both a backend and a frontend half (`APP-DESIGN.md` §12) — install both; don't stop after the backend just because that's the half that makes the server run.

1. **Read the app's `README.md` first**, before installing anything. It is the source of truth for every subsequent step — settings, env keys, throttle scopes, URL paths, signal payloads. Fetch it from the app's repo at the tag you're about to install, not from `main`, since `main` may document unreleased configuration.

2. **Install the backend half.** Every app package in this ecosystem publishes to PyPI
   (`APP-DESIGN.md` §10.2 — the standard shape, not an exception), so a normal install is a
   version range, same as any other dependency:
   ```bash
   cd backend
   uv add "notifications-app>=1.4,<2.0"
   ```
   If the app has extras you need: `uv add "notifications-app[sms]>=1.4,<2.0"`.
   Pinning an unreleased commit instead needs the git+subdirectory form (works because
   `uv`/`pip` correctly implement Git's `#subdirectory=` fragment):
   ```bash
   uv add "git+https://github.com/yourorg/notifications-app.git@v1.4.2#subdirectory=backend"
   ```
   Either way this updates `pyproject.toml` *and* `uv.lock`, and both are committed. Neither
   form needs authentication — every package in this ecosystem is public.

   Every app depends on `hjtdev-appkit` (`APP-DESIGN.md` §1.1), and `uv` resolves that
   transitively from PyPI — there's no separate `uv add hjtdev-appkit` step, and no
   `[tool.uv.sources]` entry to add either, since appkit's backend half is published to PyPI
   under that name (appkit's own `README.md`, "Installation — backend"). This only bites for a
   host still on a pre-2.0 pin: appkit's changelog entries before `[2.0.0]` used the plain
   `appkit` name and a git+subdirectory install, which still resolves for a tag already pinned
   but is no longer how a fresh install should be written.

3. **Install `@hjtdev/appkit`'s frontend half from the npm registry, if this is the first app
   being installed.** Every SDK declares `"@hjtdev/appkit": ">=2.0.0 <3.0.0"` as a
   `peerDependency` (`APP-DESIGN.md` §12) rather than bundling it, for the same reason `react`
   and `@tanstack/react-query` are peer deps: bundling it would give a host two separate
   copies — two React contexts — and `useApiClient` would silently return `null` in half the
   tree. So the host installs it once, explicitly, at the highest version any installed app's
   peer range requires:
   ```bash
   cd frontend
   npm install @hjtdev/appkit
   ```
   Already installed and satisfies every app's peer range? Skip this step. This is a
   **registry** install, unlike the app's own frontend half in step 4 below — appkit publishes
   to npm specifically because a git subdirectory install (`github:org/pkg#vX:frontend`)
   doesn't work in npm the way it works in `uv`: the tag and subdirectory are silently
   dropped, or (with the `::path:` form) the entire repository root installs instead of just
   `frontend/`. See appkit's own `README.md`, "Installation — frontend", for the full
   explanation.

4. **Install the app's own frontend half**, pinned to the same tag as its backend half. Every
   app package publishes its frontend half to npm too (same §10.2 standard, and the only
   reliable option — see the note above):
   ```bash
   npm install @yourorg/notifications-app@1.4.2
   ```
   If an app genuinely hasn't published yet and still ships via git, be aware
   `github:yourorg/notifications-app#v1.4.2:frontend` has the same tag/subdirectory-dropping
   failure mode `appkit` itself hit at v1.0.0 — verify the install actually resolved the
   tagged `frontend/` tree (`npm ls <package>` should show a version, not `main`'s) before
   trusting it. Either way, the versions must match. A mismatched pair is the single most
   likely cause of "the hook returns `undefined` for a field the API clearly sends."

5. **Copy the configuration block from the app's `README.md`** into `backend/config/settings.py` — `INSTALLED_APPS`, `MIDDLEWARE` (if any), its `REST_FRAMEWORK['DEFAULT_THROTTLE_RATES']` entries, and its settings dict (e.g. `NOTIFICATIONS = {...}`). Copy it verbatim; do not write these from memory or infer them from the package's source. Only adapt naming if there's a real collision, and if there is, note it in `CLAUDE.md` (§8) because it becomes a permanent local deviation.

   The very first app installed into a fresh scaffold also needs `appkit` itself wired in — this
   is a one-time step, not repeated per app: `REST_FRAMEWORK["EXCEPTION_HANDLER"] =
   "appkit.exceptions.standard_exception_handler"`, and `"appkit.request_id.RequestIDMiddleware"`
   added to `MIDDLEWARE` (before anything that logs, after security middleware, same position
   the scaffold's own `RequestIDMiddleware` used to occupy). Already done? Skip it.

6. **Add its `.env` keys** to `backend/.env.example` (tracked, with empty values and a comment saying whether each is required) and set real values in `backend/.env`. Required-and-missing keys should fail at startup, not at first use — see `BASE-DESIGN.md` §4.3.

7. **Mount its URLs explicitly** in `backend/config/urls.py` — see §3.

8. **Run migrations:** `docker compose exec backend python manage.py migrate` (or `uv run python manage.py migrate` outside Docker).

9. **Register any recommended periodic schedule.** If the README includes one, create the `django_celery_beat.models.PeriodicTask` entry — preferably as a data migration in `core/` so it's reproducible and reviewable, rather than clicked into the admin once. This does not happen automatically on install.

10. **Add the app's module to the `banned-api` ruff config** in `backend/pyproject.toml` (`BASE-DESIGN.md` §5.1), so the "only `core/` and `config/` may import app packages" rule is machine-enforced for this app too. One line:
    ```toml
    "notifications_app".msg = "Import app packages only from core/ or config/ — INTEGRATION-GUIDE.md §4"
    ```
    `appkit` never gets a `banned-api` line — it's a declared dependency every app is expected to import (`APP-DESIGN.md` §1.1), not a sibling app the rule exists to keep out.

11. **Mount `appkit`'s shared provider**, if it isn't mounted yet, in `frontend/app/providers.tsx` — once for the whole host, not once per app — and add this app's namespace to its `basePaths` map (the SDK-to-host client contract, `APP-DESIGN.md` §12):
    ```tsx
    // frontend/app/providers.tsx
    import { ApiClientProvider } from "@hjtdev/appkit";
    import { apiClient } from "@/lib/api-client";

    // ... inside the existing Providers component, nested under QueryClientProvider:
    <ApiClientProvider
      client={apiClient}
      basePaths={{
        // ... entries for already-installed apps stay here
        notifications: "/api/v1/notifications",   // this app's README-suggested prefix
      }}
    >
      {children}
    </ApiClientProvider>
    ```
    Installing a second, third, or fourth app adds a `basePaths` entry to this same provider — it
    does **not** nest a new provider. Get the key wrong (a typo, or reusing another app's
    namespace) and the app's hooks silently fall back to its own default prefix instead of
    failing to build; the key to use is whatever the app's own README documents.

    Skip this step entirely (no provider mounted at all) and every hook from the app throws
    immediately — `useApiClient` is written to fail loudly rather than silently pass `undefined`
    through to a `fetch` call.

12. **Import its hooks where needed**, from the package's single entrypoint (`import { useNotifications } from "notifications-app"`) — never reach past that into an internal path like `notifications-app/dist/api/manager`.

13. **Rebuild, don't just restart.** Installing or upgrading changes `uv.lock`/`package-lock.json`, which changes what's baked into the Docker image:
    ```bash
    docker compose up --build
    ```
    In production this is what `deploy-prod.sh`'s `build --pull` step exists for. **A restart without a rebuild is the single most common reason "I installed the package but it's not there."**

14. **Update `CLAUDE.md`'s installed-apps list** — §8. This is part of the task, not an optional courtesy.

15. **Verify before declaring done:** `make check` passes, `/api/schema/swagger-ui/` shows the new endpoints under their expected tags, and the app's own smoke path works (one request to a public endpoint, one to an admin endpoint expecting 403 as a non-admin).

Skipping steps or reordering them produces confusing failures — running `migrate` before `INSTALLED_APPS` is updated, mounting URLs for a throttle scope that was never registered, or a frontend hook 404ing because its backend counterpart was never installed.

### 2.1 Upgrading an installed app

```bash
cd backend  && uv add "git+https://github.com/yourorg/notifications-app.git@v1.5.0#subdirectory=backend" --upgrade
cd ../frontend && npm install "github:yourorg/notifications-app#v1.5.0::path:frontend"
```

Then, in order: read the app's `CHANGELOG.md` for the range you're crossing and act on **every "Host action:" line**; **check whether the new version raised its `appkit` peer/dependency range** (`APP-DESIGN.md` §1.1, §12) — if it did, upgrade `appkit` itself first, on both halves, before re-running `uv sync`/`npm install` for this app; re-copy any changed README config blocks; check whether any signal payload or service signature changed (a major bump means at least one did, and your `core/` receivers may need updating); `migrate`; `docker compose up --build`; run `make check`; update the version in `CLAUDE.md`.

`make check`'s `tsc --noEmit` is what actually catches a shape change the host's own code depends on — the app's `dist/index.d.ts` ships generated from its own schema (`APP-DESIGN.md` §12), so any type the host consumes that the new version changed fails to compile, same as any other breaking TS change. There's no separate host-side schema snapshot in this scaffold's own CI (`BASE-DESIGN.md` §7) — deliberately: it would only add a second gate for changes the host doesn't consume, which by definition aren't breaking it, at the cost of an artifact that churns on every unrelated endpoint change across every installed app and stops being read. If you want to see everything an upgrade changed, not just what broke the build, `diff` the running `/api/schema/` before and after — optional, human-run, not part of `make check`.

**Never upgrade across a major bump without reading the changelog.** The whole point of the version-pinning discipline in this architecture is that upgrades are deliberate; a blind `--upgrade` throws that away.

### 2.2 Removing an app

Reverse the install, and don't skip the middle steps — a half-removed app leaves a broken migration state and an unresolvable import:

```bash
cd backend && uv remove notifications-app
cd ../frontend && npm uninstall notifications-app
```

Before removing the package: `python manage.py migrate notifications_app zero` to unwind its tables (irreversible — back up first). Then delete its `INSTALLED_APPS` entry, settings dict, throttle scopes, `.env` keys, URL mounts, `banned-api` line, any `core/signals.py` receivers or `core/services/` calls referencing it, any frontend imports, its entry in `CLAUDE.md`, and **its `basePaths` entry** in `frontend/app/providers.tsx` (§2 step 11) — not the `ApiClientProvider` mount itself, which every remaining app still needs. Grep for both the module name (`notifications_app`) and the package name (`notifications-app`) to catch leftovers.

Don't `npm uninstall @hjtdev/appkit` or remove `hjtdev-appkit`'s backend dependency as part of removing a single app — it's a shared dependency every remaining installed app still relies on. Only remove it if this was the last app installed in the project.

## 3. URL Routing Architecture

`backend/config/urls.py` is a normal, explicit Django URLconf — no discovery loop, no filesystem scan. Every app's public and admin routes are written out by hand, following the app's README:

```python
urlpatterns = [
    path("admin/", admin.site.urls),
    path("healthz/", views.healthz),
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path("api/schema/swagger-ui/", SpectacularSwaggerView.as_view(url_name="schema")),

    # ---- Public App APIs
    path("api/v1/payments/", include("payments_app.urls")),
    path("api/v1/notifications/", include("notifications_app.urls")),

    # ---- Custom Admin Dashboard APIs
    path("api/v1/admin/payments/", include("payments_app.urls_admin")),
    path("api/v1/admin/notifications/", include("notifications_app.urls_admin")),
]
```

Keep public and admin routes visually grouped like this — it makes the permission boundary obvious at a glance, and it matches how `drf-spectacular` groups them: every view in a public `urls.py` carries `tags=["<app-name>"]`, every view in an `urls_admin.py` carries `tags=["<app-name>-admin"]`, so Swagger shows two clearly separated sections per app rather than one flat list.

The prefix is the host's choice, not the app's — an app's README *suggests* `api/v1/notifications/`, and a project that already has a different convention is free to mount it elsewhere. What must not change is the public/admin split, since the app's permission classes assume it.

## 4. Inter-App Communication (The Mediator Pattern)

Reusable apps never import each other. Every cross-app connection is mediated by `backend/core/`, using the signals and services each app exposes as its public surface (`APP-DESIGN.md` §6).

### Signal handlers — `backend/core/signals.py`

```python
# backend/core/signals.py
from django.db import transaction
from django.dispatch import receiver

from notifications_app.services import NotificationService
from payments_app.signals import payment_completed


@receiver(payment_completed)
def notify_on_payment_completed(sender, payment_id, user_id, amount, **kwargs):
    # on_commit: never notify about a payment whose transaction later rolls back
    transaction.on_commit(
        lambda: NotificationService.send(
            user_id=user_id,
            template="payment_success",
            context={"amount": amount},
        )
    )
```

```python
# backend/core/apps.py
from django.apps import AppConfig


class CoreConfig(AppConfig):
    name = "core"

    def ready(self):
        import core.signals  # noqa: F401 — registers every receiver above
```

`core` must be in `INSTALLED_APPS` with this `AppConfig` for the receivers to connect. **This is the single most common thing to forget, and the most common reason a signal handler "silently doesn't fire."** It's the first item in §9's checklist.

Three more rules for receivers, each learned the hard way:

- **Always accept `**kwargs`.** An app adding a kwarg to a signal payload is a minor bump, and a receiver without `**kwargs` breaks on it.
- **Never let a receiver raise into the sender.** A receiver that throws propagates into the app's own `services.py` call, so a failed notification rolls back a successful payment. Wrap the body in a `try/except` that logs, or — better — do nothing but enqueue a task, so the retry story belongs to Celery.
- **Slow work goes in a task, not the receiver.** Signals are synchronous. `NotificationService.send` calling an SMS provider inline adds its latency to the payment request.

### Service orchestration — `backend/core/services/`

Some workflows are a request/response composition rather than fire-and-forget — checkout needing to read the cart, create a payment, reserve inventory. That composition lives here, calling each app's own `services.py`:

```python
# backend/core/services/checkout.py
from django.db import transaction

from cart_app.services import CartService
from inventory_app.services import InventoryService
from payments_app.services import PaymentService


@transaction.atomic
def complete_checkout(user_id: int):
    cart = CartService.get_active_cart(user_id)
    InventoryService.reserve(cart.items)
    payment = PaymentService.charge(user_id, cart.total)
    return payment
```

This function — not any single app — is what a project-level view or Celery task calls. No app in the chain knows about any other app in the chain.

**The `@transaction.atomic` is doing real work here, and so is what it can't do.** It guarantees the *database* effects roll back together, but it cannot roll back a charge already made at Stripe. Any orchestrator that mixes DB writes with external side effects needs an explicit compensation path (a `try/except` that refunds, or an idempotency key so a retry is safe) — the atomic block is necessary and not sufficient. Note this in the orchestrator's docstring so the next reader doesn't assume more safety than exists.

### Frontend composition — `frontend/app/`

Same rule, mirrored: an installed SDK's hooks never import another installed SDK. When a page needs both, that composition happens in the page or component:

```tsx
// frontend/app/checkout/page.tsx
// Assumes appkit's ApiClientProvider is already mounted in frontend/app/providers.tsx
// with "cart" and "payments" entries in its basePaths map (§2 step 11) — this page only
// consumes each SDK's hooks, it never mounts a provider itself.
"use client";

import { useCart, cartKeys } from "cart-app";
import { useCreatePayment } from "payments-app";
import { useQueryClient } from "@tanstack/react-query";

export default function CheckoutPage() {
  const queryClient = useQueryClient();
  const { data: cart } = useCart();
  const { mutate: createPayment, isPending } = useCreatePayment();

  const handleCheckout = () => {
    if (!cart) return;
    createPayment(
      { amount: cart.total, items: cart.items },
      // cross-app cache invalidation belongs HERE, using the key factory the cart
      // SDK exports (APP-DESIGN.md §12) — never by hardcoding the key string
      { onSuccess: () => queryClient.invalidateQueries({ queryKey: cartKeys.all }) }
    );
  };

  return (
    <button onClick={handleCheckout} disabled={isPending || !cart}>
      Pay {cart?.total}
    </button>
  );
}
```

`CheckoutPage` is the mediator here, exactly like `core/services/checkout.py` is on the backend — it's allowed to know both packages exist because it lives in the host project, not inside either SDK.

### Testing `core/`

Everything in `core/` is custom, project-owned code — no app's test suite covers it, since no app knows `core/` exists. It gets real tests in `backend/core/tests/`:

```python
# backend/core/tests/test_signals.py
from unittest.mock import patch

import pytest
from payments_app.factories import PaymentFactory
from payments_app.signals import payment_completed


@pytest.mark.django_db
def test_payment_completed_triggers_notification(user):
    payment = PaymentFactory(user=user, amount=100)
    with patch("core.signals.NotificationService.send") as mock_send:
        payment_completed.send(
            sender=None, payment_id=payment.id, user_id=user.id, amount=100
        )
    mock_send.assert_called_once_with(
        user_id=user.id, template="payment_success", context={"amount": 100},
    )
```

Note `PaymentFactory` coming from the installed app's own `factories.py` (`APP-DESIGN.md` §7.3) — that's the sanctioned way to build another app's objects in a test, and it's why `factory-boy` is in the host's `test` dependency group. Importing factories from *production* `core/` code is a bug.

If the receiver uses `transaction.on_commit` (as it should), the test needs `django_capture_on_commit_callbacks` or `pytest.mark.django_db(transaction=True)` — otherwise the callback never runs inside the test transaction and the assertion fails for a reason that has nothing to do with your code.

Also test:
- **`core/services/` orchestrators** — as plain functions against a test DB; assert the return value *and* the side effects (was inventory actually reserved, was the payment created).
- **`core/views/` overrides** — with `APIClient`, same as any DRF view.
- **The wiring itself** — one test asserting `/api/schema/` is 200 and contains every mounted app's tag; one asserting every `throttle_scope` string in the codebase exists in `DEFAULT_THROTTLE_RATES`. Fifteen lines that catch the two most common integration mistakes in this architecture.

This is a normal `pytest` suite (`make test`). CI runs it (`BASE-DESIGN.md` §7); `deploy-prod.sh` deliberately does not — the deploy script stays focused on build/health/rollout.

## 5. Handling Custom Views & Overrides

- **Subclassing app views.** If the project needs modified behavior on top of an app's view (extra validation, a different response shape), subclass it in `backend/core/views/` and point `config/urls.py` at the subclass instead of the app's own view — never edit the installed package. Same for serializers. Keep the app's `throttle_scope` on the subclass unless you deliberately want a different rate, and if you do, register the new scope.
- **Admin overrides.** Jazzmin-wide config (icons, ordering, branding) lives in `config/settings.py`'s `JAZZMIN_SETTINGS` — the host's to control regardless of which apps are installed. If a project needs a different Django admin experience for a specific app's model, use a proxy model + a new `ModelAdmin` registered from `core/`, rather than editing the installed app. (`admin.site.unregister(...)` then re-registering also works and is sometimes cleaner; either way the change lives in `core/`.)
- **Template & static overrides.** Django's template loader checks project-level directories before app-provided ones when `DIRS` in `TEMPLATES` lists `backend/templates/` first. To override an app's template, mirror its namespaced path: `templates/notifications_app/email/payment_success.html` in the app is overridden by a file at the same relative path under `backend/templates/`. Same idea for static files via `STATICFILES_DIRS` ordering.
- **When an override starts to sprawl, stop and reconsider.** Three subclasses and two template overrides against the same app is a signal, not a solution — either the app needs a real configuration hook (a change in its own repo, released properly), or this project's needs have diverged enough that it wants its own app. Piling up overrides means every future upgrade of that app is a guessing game about which of your subclasses still line up.

## 6. Shared Utilities & Cross-Cutting Concerns

`backend/tools/` is project-owned and exists for **`config/` and `core/` code** — not for installed app packages, which can't assume a specific host's internals exist. What used to live here and be duplicated by every app (`APP-DESIGN.md` §4) now has a real home: `appkit`, a declared, versioned dependency every app depends on explicitly (`APP-DESIGN.md` §1.1). appkit's own `ApiClientProvider`/`useApiClient`/`makeQueryClient` are what an installed SDK is allowed to assume exist (`APP-DESIGN.md` §12) — `frontend/lib/query-client.ts` no longer exists as a separate host convention; the scaffold's own `frontend/app/providers.tsx` calls `makeQueryClient()` straight from `appkit`. `frontend/lib/api-client.ts` (the host's concrete `HttpClient` implementation, injected into `ApiClientProvider`) is the one thing left in `frontend/lib/` for the host's own pages and components to share.

- `tools/crypto.py` — wraps the project's `FERNET_KEY` for field-level encryption in project-owned models: `from tools.crypto import encrypt, decrypt`. Internally a thin wrapper over `appkit.crypto.Cipher` (requires the `crypto` extra — `hjtdev-appkit[crypto]`) built from `FERNET_KEY`; appkit's `Cipher` itself reads no setting or env var of its own, by design. If an *app* needs encryption internally, that's the app's own concern with its own documented `.env` key and its own `Cipher` — never the host's `tools.crypto`.
- `appkit.cache` / `appkit.mixins` — the caching helpers and `CachedListMixin`, shared with every installed app rather than duplicated per app or reimplemented in `tools/`.
- `appkit.exceptions` — the error-envelope handler, wired as `REST_FRAMEWORK["EXCEPTION_HANDLER"]`.
- `appkit.request_id` — the request-ID `ContextVar`, middleware, and logging filter; `config/logging.py`'s `build_logging_config()` imports the filter from here.

`BASE-DESIGN.md` §3's "The `tools/` vs `appkit` boundary" has the test for which new host code belongs where: **does an app package need it to behave correctly in any host?** If yes, it's an `appkit` candidate, not a `tools/` addition.

**If something genuinely project-specific in `tools/` (i.e. not a candidate for `appkit`) would be useful in the next project too, that's a signal** — copy it by hand into the next scaffold clone (fine for a 20-line helper), since it depends on this project's own configuration and isn't something a shared dependency can express. What's *not* fine, on either side of this boundary, is an app package importing `tools.*` directly — that silently couples a supposedly-standalone package to one host's layout, and it will fail in the next project that installs it. `appkit` exists specifically so that instinct has a legitimate outlet instead.

## 7. Dependency Resolution & Troubleshooting

The failure modes specific to this architecture, and what each actually means.

### `uv add` fails with a resolution conflict

```
× No solution found when resolving dependencies:
╰─▶ Because notifications-app depends on djangorestframework==3.14.2 and
    payments-app depends on djangorestframework==3.15.0, we can conclude…
```

All installed apps share **one** environment (`APP-DESIGN.md` §1.1). Two apps with incompatible pins can't coexist. In order of preference:

1. **Fix the app.** Whichever app pinned exactly is the one violating the standard — change it to a range, release a patch version, re-pin. This is the correct fix and it's usually a two-line diff.
2. **`uv tree`** to see who actually requires what, and `uv add --upgrade-package <name>` if one side just needs a nudge within its range.
3. **A last-resort `[tool.uv] override-dependencies`** in the host, forcing one version. This says "I know better than the app's declared constraint" — legitimate occasionally, dangerous always. If you do it, comment *why* and open an issue on the app repo, because it's a landmine for the next person.

`appkit` is the most likely subject of this conflict once an ecosystem has more than a couple of apps — it's the one dependency every app shares (`APP-DESIGN.md` §1.1). Two apps pinning different `appkit` majors is the same unresolvable shape as the `djangorestframework` example above, and the fix is the same: whichever app pinned too tightly needs a range, not the host working around it.

### The app installed but Django can't find it

Check in this order — it's almost always the first or the last:
1. Is it in `INSTALLED_APPS`? (Installing a package does not register it.)
2. Did you rebuild the Docker image, or just restart? (`docker compose up --build`.)
3. Is the *module* name right in `INSTALLED_APPS`? The package is `notifications-app` (hyphens), the module is `notifications_app` (underscores). They're different strings and both appear in this workflow.

### Templates or translations are missing from an installed app

The app's build didn't ship its package data (`APP-DESIGN.md` §2). That's a bug in the app's own `MANIFEST.in`/build config, fixable only in the app's repo — and it's exactly what the `wheel-smoke-test` CI job (`APP-DESIGN.md` §10) exists to prevent. Don't work around it by copying files into `backend/templates/`; that hides the bug and breaks on the next upgrade.

### A signal receiver isn't firing

1. Is `core` in `INSTALLED_APPS` with the `AppConfig` whose `ready()` imports `core.signals`?
2. Is the receiver importing the signal object from the app, or accidentally creating a new one? `from payments_app.signals import payment_completed` — a re-declared `Signal()` in `core/` connects to nothing.
3. Did the sender's transaction commit? If the receiver uses `on_commit` and the caller rolled back, silence is correct behavior.
4. Did the app's major version bump change the signal's payload or name? Read the changelog.

### The frontend hook 404s or returns the wrong shape

Almost always a version mismatch between halves (§2 step 4) or a missing URL mount (§3). Confirm the pinned tags match in `package.json` and `pyproject.toml`, then hit the endpoint directly with `curl` — if `curl` works and the hook doesn't, check the `basePaths` key in `frontend/app/providers.tsx` (§2 step 11) before the base URL in `frontend/lib/api-client.ts` — a wrong or missing key falls back to the app's own default prefix silently.

### After any of these

Re-run `make check`. If `uv sync --locked` fails, someone hand-edited `pyproject.toml` without re-locking — run `uv lock` and commit the result.

## 8. Keeping `CLAUDE.md` Current

`CLAUDE.md` is read on every agent turn, which makes it the highest-leverage file in the repo and also the most dangerous when stale — an agent will trust a wrong installed-apps list over the actual `pyproject.toml`, because that's what a `CLAUDE.md` is *for*.

Update it as part of the task, not afterward, whenever:

- An app package is **installed, upgraded, or removed** → its line in the installed-apps table, with the new version.
- A **project-specific convention** is established (a naming pattern, a deliberate deviation from an app's suggested URL prefix, a decision not to use some app's feature) → one line under conventions, because it will otherwise be re-litigated every session.
- A **command changes** (a new `make` target, a changed test invocation) → the commands block.
- **Something surprising is discovered** — a footgun, a non-obvious constraint, an override that exists for a reason nobody would guess → the gotchas section. This is the highest-value content in the file. A single line saying "`payments_app`'s webhook view must stay unauthenticated; don't add a permission class to the subclass" saves an hour and a production incident.

Keep it short. It competes for context on every single turn, so anything long-form belongs in `docs/` with a pointer from `CLAUDE.md`. If it grows past roughly 150 lines, that's a sign content should move into `docs/`.

## 9. Agent Execution Checklist

Before considering any integration task complete, verify every one of these — don't assume, and don't mark them off by reading the code you just wrote. Where a command exists, run it.

**Wiring**
- [ ] `core` is in `INSTALLED_APPS`, and its `AppConfig.ready()` imports `core/signals.py`.
- [ ] Every new signal receiver actually fires — proven by a test, not by reading the code.
- [ ] Every receiver accepts `**kwargs`, can't raise into the sender, and defers slow work to a task.
- [ ] `migrate` has been run for every newly installed or updated app.
- [ ] Every new/changed setting came from the app's `README.md` block, not guessed.
- [ ] Every new `.env` key is in `.env.example` too, marked required or optional.
- [ ] Every view (app or override) has a `throttle_scope`, and that scope exists in `DEFAULT_THROTTLE_RATES`.
- [ ] Both halves of every app are installed **at the same tag**.
- [ ] The newly installed app has a `banned-api` line in `backend/pyproject.toml` (§2 step 10) — except `appkit`, which never gets one (`APP-DESIGN.md` §1.1).

**Boundaries**
- [ ] Zero imports between two app packages anywhere outside `backend/core/` — `uv run ruff check .` proves this now that §2 step 10 is done; don't rely on grep alone. `appkit` is a declared dependency, not a sibling app, so every app importing it is expected and not a violation.
- [ ] Zero imports between two installed frontend SDKs; cross-app UI composition lives only in `frontend/app/`. Same `appkit` carve-out as above — every SDK importing `appkit` is the declared-peer-dependency case, not the banned inter-SDK case.
- [ ] Every installed frontend hook is imported from its package root, not a deeper internal path.
- [ ] No app package imports `tools.*` or anything else host-specific. `appkit` is explicitly not `tools.*` — it's the shared dependency `tools.*` helpers moved into, precisely so an app *can* import it (`BASE-DESIGN.md` §3).
- [ ] No `factories` import in production code — test files only.
- [ ] **No file under `.venv`/`site-packages` or `frontend/node_modules` was edited.**

**Quality gates**
- [ ] `make check` passes end to end (ruff, mypy, tsc, eslint, pytest, vitest).
- [ ] `uv sync --locked` succeeds — `pyproject.toml` and `uv.lock` agree, and both are committed.
- [ ] `python manage.py makemigrations --check --dry-run` reports nothing missing.
- [ ] `docker compose up --build` succeeds, and every container reports `healthy` — not just `running`.
- [ ] `/api/schema/swagger-ui/` renders with the new endpoints grouped under their public/admin tags.
- [ ] Any new or changed `core/` signal, service, or view override has a test in `backend/core/tests/`.
- [ ] `CLAUDE.md` reflects the new state — installed versions, new conventions, any gotcha discovered along the way (§8).

If any item can't be satisfied, **say so explicitly rather than silently skipping it.** A reported gap is a small problem; a checklist marked complete on an assumption is how this architecture's guarantees quietly stop being true.
