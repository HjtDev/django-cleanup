# CLAUDE-CODE-GUIDE-APP.md — Building an App Package with Claude Code

How to build a reusable, versioned, dual-package app (Django + React SDK) with Claude Code, and
release it so any host project can install it with two commands.

Unlike the base scaffold, you'll do this **many times** — so the goal isn't just a working app,
it's a repeatable process. Build the second one with the same phases as the first, then
templatize (§6).

> Companion: `CLAUDE-CODE-GUIDE-BASE.md` (building the host scaffold).

---

## 0. The operating principle

The base scaffold's difficulty was breadth — lots of infrastructure, each piece
straightforward. An app package's difficulty is **discipline under a constraint the agent's
training pulls against**: a normal Django app freely imports whatever's in the project, and
this one cannot. Every session, the pull is toward `from payments_app.models import Payment`
because that's what a million Django apps do.

**`appkit` is app package #1 in this ecosystem, and it's the one named exception to that
constraint** (`APP-DESIGN.md` §1.1) — every app declares it as a real, versioned dependency in
`pyproject.toml`/`package.json` and imports the cache mixin, error-envelope handler, and
`HttpClient`/provider from it rather than reimplementing them. If you're building `appkit`
itself, most of this guide still applies, but there's nothing to declare a dependency *on* —
it's the simplest possible instance of the shape below. If you're building any app *after* it,
`appkit` is always in scope for Phase 0 and Phase 1: it's the one import that isn't the
`payments_app.models`-style mistake this section warns about.

So the process below front-loads two things:

1. **A contract defined before any code exists** (§2, Phase 0). What this app's models,
   signals, services, endpoints, and settings *are* — written down, reviewed, frozen. Half the
   coupling mistakes in an app package come from discovering a need mid-implementation and
   satisfying it the easy way.
2. **Machine enforcement of the boundary**, from phase 1 (ruff `banned-api`, the CI grep job).
   Rules a human has to remember are rules that get broken at 11pm; rules that fail the build
   are rules that hold.

Same session hygiene as the base guide: one phase per session, `/clear` between, every phase
ends in a command with an exit code, review every diff.

---

## 1. Before you open Claude Code

### 1.1 Scaffold the repo and drop in the spec

```bash
mkdir notifications-app && cd notifications-app
git init
mkdir -p docs
cp /path/to/APP-DESIGN.md        docs/
cp /path/to/INTEGRATION-GUIDE.md docs/    # so the agent can see the host's side of the contract
cp /path/to/BASE-DESIGN.md       docs/    # for what a host provides (query-client, tools/, etc.)
```

All three, not just `APP-DESIGN.md`. An app package's whole job is to be installable into the
host described by the other two — an agent that can't see the host side will invent
assumptions about it, and those assumptions are exactly what breaks in project number three.

### 1.2 Write this repo's `CLAUDE.md` first

Start from the **app-package variant** at the bottom of `CLAUDE.md.template`, then add the
build-time working agreement:

```markdown
## Working agreement (delete after v1.0.0 ships)
- One phase at a time; don't create files outside the current phase's scope.
- Re-read the relevant docs/APP-DESIGN.md section before writing files it specifies.
- After each phase, run its verification command and paste the real output. Never report
  success you haven't observed.
- If the spec is ambiguous or looks wrong, ask. Don't guess and proceed.
- This package must work in ANY host project. Whenever you're about to rely on something
  existing outside this package, stop — that's the constraint this whole design exists for.
```

The last bullet is the one that matters. Keep it phrased as a *trigger to stop*, not a
prohibition to remember — "whenever you're about to rely on X" is actionable in the moment in a
way that "never couple to the host" isn't.

### 1.3 Answer these before Phase 0

| Question | Why it has to be decided up front |
|---|---|
| Module name (`notifications_app`) vs package name (`notifications-app`) | Both appear everywhere; changing later touches every file |
| Does it need a frontend half? | Some apps (a webhook receiver, an audit logger) genuinely don't |
| What does it need from the user model beyond `AUTH_USER_MODEL`? | If the answer is "more," reconsider the boundary — see §5 |
| Does it need to reference another app's data? | If yes, `contenttypes` or one-package-not-two (`APP-DESIGN.md` §6) — decide now, not mid-build |
| Which settings are configurable vs. fixed? | Becomes `conf.py`'s `DEFAULTS` and the README block |
| Which `.env` keys are required vs. optional? | Required-and-missing must fail at startup |
| Celery, `django.tasks`, or neither? | Changes whether the host must run a worker for this app to function |
| Which shared helpers does this app need from `appkit`, and does `appkit` already have all of them? | `appkit` (`APP-DESIGN.md` §1.1) is the one named exception to "an app never depends on an app" — but if the answer to the second half is "no," that gap is an `appkit` minor release, not a local reimplementation in this app's own `utils.py` |

---

## 2. The build, phase by phase

Fresh session per phase. Preamble each one:

> Read `CLAUDE.md`, then `docs/APP-DESIGN.md` §{{N}}. Phase {{N}} only — nothing outside its
> scope. Give me your plan before writing anything.

### Phase 0 — The contract (no code)

The most valuable phase, and the one most likely to be skipped.

```
Phase 0: design the public contract. Write it to docs/CONTRACT.md. No implementation code.

Read docs/APP-DESIGN.md fully first — especially §1 (package contract), §6 (inter-app
communication), and §8 (the README contract, which is what this document will become).

I want a {{notification delivery}} app that {{one-paragraph description of what it does}}.

Produce:
1. Models — fields, types, indexes, and every FK. Flag any FK that would point outside this
   package, and propose how to avoid it per §2 and §6.
2. Signals emitted — name + exact payload kwargs + when it fires. This is a versioned
   contract, so argue for the minimum viable payload: every kwarg is something we can never
   remove without a major bump.
3. services.py — the public callables, with full signatures and return types. Same reasoning:
   this is the surface hosts couple to.
4. Endpoints — public and admin, method, path, permission class, throttle scope (namespaced
   per `APP-DESIGN.md` §1.2), request/response shape.
5. Settings dict keys with defaults (→ conf.py) and .env keys marked required or optional.
6. Frontend hooks — name, what it wraps, query keys, invalidation behavior.
7. Celery/django.tasks tasks, and any recommended periodic schedule.
8. Dependencies, with the range rule from §1.1 applied — call out anything a host is also
   likely to depend on directly.

For each of 1–7, note explicitly whether anything requires knowledge of another app package.
If something does, propose the decoupled alternative rather than accepting it.
```

**Review this yourself, carefully, before Phase 1.** Specifically:

- **Is every signal payload minimal?** A kwarg added later is a minor bump; one removed later
  is major. Err toward too few.
- **Would a host actually be able to use this without reading the source?** If a service
  method's semantics can't be captured in a signature plus one sentence, it's the wrong shape.
- **Does anything smell like it belongs in a different app** — or like this app is really two?
  Phase 0 is the last cheap moment to split.
- **Is anything reaching outside?** An FK to another app's model, a settings key naming another
  app, a service that takes another app's object as a parameter. All three are the same
  mistake, and all three are trivial to fix now and painful to fix at v1.3.

### Phase 1 — Package skeleton, `pyproject.toml`, boundary enforcement

```
Phase 1: the package skeleton. docs/APP-DESIGN.md §2 and §3.

Create the repo structure from §2 exactly, then:
1. backend/pyproject.toml complete per §3.1 — build config with include-package-data, the
   dependencies from docs/CONTRACT.md item 8 with WIDE RANGES per §1.1, PLUS
   "hjtdev-appkit>=2.0,<3.0" (unless this repo IS appkit — see §0), [dependency-groups] dev + test,
   [tool.uv] default-groups, and the ruff / mypy / pytest / coverage config.
2. The flake8-tidy-imports banned-api block, listing every OTHER app package in our
   ecosystem plus this package's own factories module (test paths exempted). Do NOT add a
   line for appkit — it's a declared dependency every app is expected to import, not a
   sibling app the rule exists to keep out (§1.1).
3. backend/MANIFEST.in so locale/, templates/, and static/ ship in the wheel.
4. .python-version, .gitignore, .pre-commit-config.yaml.
5. src/notifications_app/__init__.py, apps.py (AppConfig with a translatable verbose_name),
   and conf.py per §3.5 with the DEFAULTS from CONTRACT.md item 5.
6. Empty-but-present: models.py, views.py, serializers.py, permissions.py, signals.py,
   services.py, urls.py, urls_admin.py, admin.py, admin_views.py, tasks.py, factories.py
   — each with a docstring stating its role per the spec. utils.py is NOT on this list
   anymore — create it only if the app has genuinely private helpers with nowhere else to
   go; the shared cache mixin and error handler come from appkit, not from a bundled
   utils.py (§4).

Run `uv sync`, then `uv build`, and paste both outputs.
```

**appkit's pytest fixtures are opt-in, not automatic.** appkit ships `api_client`, `user`,
`admin_user`, `auth_client`, `admin_client`, `frozen_request_id`, `clear_cache`, and
`assert_error_envelope` via a pytest plugin (`appkit.testing`) with no `pytest11` entry point —
loading it automatically for every host the moment appkit is installed (which is always,
transitively) was considered and rejected (`appkit/docs/CONTRACT.md` §2.17). Wire it up in this
app's own `pyproject.toml`:

```toml
[tool.pytest.ini_options]
addopts = "-p appkit.testing ..."
```

Do this instead of hand-rolling a slightly different `api_client`/`auth_client`/`user` in this
app's own `tests/backend/conftest.py` — the shared fixtures exist precisely so nine installed
apps don't each reinvent them slightly differently.

**Verify:** `uv sync` and `uv build` both succeed; `dependencies` uses ranges, not `==`, including
on `appkit`.

**Review for:** exact pins on `django`/`djangorestframework`/`appkit` (the most consequential
mistake in this whole document — see §5); `include-package-data` present; `banned-api` populated
and NOT listing `appkit`.

### Phase 2 — Models, migrations, admin

```
Phase 2: data layer. docs/APP-DESIGN.md §2 and docs/CONTRACT.md item 1.

Implement models.py exactly as CONTRACT.md specifies:
- settings.AUTH_USER_MODEL for any user FK — never a concrete model, never an import
- Meta.indexes for every field used in filters, ordering, or FK lookups
- No FK to any other app package's model, ever

Then makemigrations, and verify 0001_initial uses
migrations.swappable_dependency(settings.AUTH_USER_MODEL) — add it if it's missing.

Then admin.py: ModelAdmin registrations with list_display, list_filter, search_fields,
readonly_fields for anything computed, and select_related/prefetch_related on
get_queryset so the changelist isn't N+1. Do NOT touch JAZZMIN_SETTINGS — that's the
host's (§5); instead note the suggested icon for the README.

Create tests/backend/settings.py per §7.1 (minimal INSTALLED_APPS, Postgres), then run
`uv run pytest --create-db` to prove migrations apply from zero. Paste the output.
```

**Verify:** migrations apply against real Postgres from zero; `swappable_dependency` present.

**Review for:** any concrete `User` import; missing indexes; a `ForeignKey` to something
outside the package.

### Phase 3 — Services, signals, tasks

The phase where coupling gets in if it's getting in.

```
Phase 3: business logic. docs/APP-DESIGN.md §6 and docs/CONTRACT.md items 2, 3, 7.

Implement:
- services.py — exactly the signatures in CONTRACT.md, fully type-annotated. Each method is
  agnostic about its caller: no assumption about who calls it or why.
- signals.py — the declared signals with a comment documenting the exact payload above each.
- tasks.py — tasks per CONTRACT.md item 7. Idempotent where they might be retried; no
  reliance on host-specific Celery config beyond what an autodiscovered task can assume.
- utils.py — the bundled cache/mixin helpers from §4, since we cannot import a host's tools/.

Hard constraints, re-stated because this is the phase they matter most:
- No import of any other app package, in any form.
- No import from a host (core, tools, config) — those don't exist from this package's view.
- Every service method that emits a signal emits it with EXACTLY the documented payload.
- Anything configurable comes from conf.get_setting(), not a hardcoded literal.

Then write tests/backend tests: happy path + at least one failure path per service method,
and one test per signal asserting the exact payload by connecting a receiver. Run pytest.
```

**Verify:** `uv run pytest` green; `uv run ruff check .` clean (the `banned-api` config is what
catches a stray cross-app import here).

**Review for:** signal payloads matching `CONTRACT.md` character for character (a host's
receiver is written against the documented payload, so a drift here breaks hosts silently);
hardcoded values that should be settings; a service method that quietly needs an object from
another app.

### Phase 4 — API layer

```
Phase 4: the API. docs/APP-DESIGN.md §4 and §5, plus docs/CONTRACT.md item 4.

Implement serializers.py, permissions.py, views.py, admin_views.py, urls.py, urls_admin.py.

Every view, without exception:
- a namespaced throttle_scope (`APP-DESIGN.md` §1.2)
- a complete @extend_schema: summary, description, request/response serializers, and
  tags=["notifications"] or tags=["notifications-admin"]
- a real permission class — object-level, not just class-level, so one user can't reach
  another's object by ID
- an optimized queryset (select_related/prefetch_related)
- an explicit pagination_class on any list endpoint that can grow unbounded
- the bundled CachedListMixin from utils.py on GET/list/retrieve

permissions.py exposes at least one user-facing class plus IsAppAdmin, relying only on
is_authenticated / is_staff / is_superuser / has_perm — never another app's models.

Write serializers used for writes with explicit field lists — never fields = "__all__".
Never expose tokens, internal IDs, or password hashes in read output.

Then tests: per §7.4, every view gets 200 for the permitted user, 403 for someone else's
object, 401 unauthenticated. Plus one test asserting each throttle scope is actually applied.
Run pytest and paste coverage.

Then generate the schema: DJANGO_SETTINGS_MODULE=tests.backend.settings uv run python
manage.py spectacular --file schema.yml --fail-on-warn, and commit schema.yml. This is what
Phase 5 generates types.ts from — a complete @extend_schema on every view (above) is what
makes that possible, so a warning here means Phase 5 will generate something wrong.
```

**Verify:** coverage over threshold; the 403 IDOR test exists and genuinely fails when you
temporarily remove the object-level check (worth actually trying — a permission test that
passes against broken code is common and worthless); `--fail-on-warn` is clean.

### Phase 5 — Frontend SDK

```
Phase 5: the frontend half. docs/APP-DESIGN.md §12 and docs/CONTRACT.md item 6.

Create in frontend/:
- package.json per §12's excerpt — react, @tanstack/react-query, AND @hjtdev/appkit as
  peerDependencies ONLY (unless this repo IS appkit — see §0), openapi-typescript as a
  devDependency, a generate:types script, an exports map with just ".", files: ["dist"],
  version matching backend/pyproject.toml. If this repo IS appkit: `name` is the scoped
  `@hjtdev/appkit` (the registry publish target, docs/CONTRACT.md §22), plus `publishConfig:
  { access: "public" }` (NOT `provenance: true` here — that belongs on CI's own `npm publish
  --provenance` flag only, or every manual/bootstrap publish hard-fails outside a CI OIDC
  context), a `repository` field, and a `prepare` script that builds `dist/` — none of which
  apply to an ordinary app package, which installs by git tag, not registry.
- Run npm run generate:types (needs backend/schema.yml from Phase 4) to produce
  src/schema.d.ts. Never hand-edit this file — it's regenerated, not written.
- tsconfig.json (strict), tsconfig.build.json, vitest.config.ts, eslint config
- src/types.ts — hand-written, NOT a copy of the serializers: re-export narrowed aliases
  from schema.d.ts (export type Notification = components["schemas"]["Notification"]) plus
  whatever app-specific shape genuinely can't come from the schema, per §12's "Generated
  types" and "What stays hand-written". Do NOT declare HttpClient or an error-envelope type
  here — both come from appkit now; re-export HttpClient if convenient
  (export type { HttpClient } from "@hjtdev/appkit"), never redeclare it.
- src/api/config.ts — NOT a provider. One internal binding of this app's namespace and
  default basePath to appkit's shared useApiClient hook, per §12's "SDK-to-host client
  contract": `export const useNotificationsConfig = () => useApiClient("notifications",
  "/api/v1/notifications");`. Never exported from index.ts.
- src/api/manager.ts — instance-based, constructed from the injected client and basePath
  (never a static class); one method per endpoint; the ONLY place a raw HTTP call exists;
  never exported from index.ts
- src/hooks/* — thin react-query wrappers that read the app's own config hook from
  api/config.ts, build the manager with useMemo, one per CONTRACT.md item 6, with an
  exported key factory per hook family and mutations invalidating the right keys
- src/index.ts — hooks, key factories, and this app's own types only. NOT a provider —
  appkit's ApiClientProvider is what a host mounts, and this app never re-exports it. Never
  the manager, never the config hook.

Then tests/frontend with Vitest + MSW per §7.7: success AND error path per hook,
onUnhandledRequest: "error", retry: false. Wrap test renders in appkit's ApiClientProvider
with a stub client satisfying HttpClient — not a real fetcher.

Run npx tsc --noEmit, npm run lint, npm run test, npm run build. Paste all four.
```

**Verify:** all four pass; `dist/index.d.ts` exists; no `any` on any request/response type;
`git diff --exit-code src/schema.d.ts` after re-running `generate:types` is clean (the CI
check from §10.1 — worth running now rather than finding out in CI).

**Review for:** `react`, `@tanstack/react-query`, or `@hjtdev/appkit` accidentally in
`dependencies` instead of `peerDependencies` (causes two-copies-of-React-or-appkit bugs in
hosts that are miserable to debug — for `@hjtdev/appkit` specifically, `useApiClient` starts
returning `null` in half the tree); the manager or this app's own config hook (`useXConfig`)
leaking through `index.ts`; a `NotificationsProvider` or any other provider being exported at
all — there shouldn't be one; the manager built as a static class instead of constructed via
`useMemo` from the injected client; `HttpClient` or the error envelope redeclared in `types.ts`
instead of imported from `@hjtdev/appkit` — that's the hand-written half quietly regaining the
drift risk generation (and now appkit) exists to remove.

### Phase 6 — Playground

The step that catches what generation and neither test suite can: runtime behaviour.

Type drift is no longer this phase's job — §12's "Generated types" and the CI diffs in §10.1
make a `types.ts`/serializer mismatch impossible to commit in the first place, so this phase
is not the last line of defense against it the way it used to be. What it still is: the only
place the two halves ever actually talk to each other over a real HTTP connection, which
means it's still the only check for anything that only shows up at runtime.

```
Phase 6: the playground. docs/APP-DESIGN.md §11.2.

Create playground/ — a minimal Django + Next.js host with both halves linked by PATH:
- playground/backend/ — a minimal Django project (settings, urls, asgi) with this app in
  INSTALLED_APPS, and pyproject.toml using [tool.uv.sources] with
  { path = "../../backend", editable = true } per §11.2. NOT an editable-flag install.
- playground/frontend/ — a minimal Next app with QueryClientProvider mounted, package.json
  depending on "file:../../frontend", and one page exercising every exported hook
- playground/docker-compose.yml — Postgres, Redis, both halves

Then bring it up and exercise every hook through the UI. Check, and report on, what only a
live round trip can show:
- does <XProvider client={apiClient}> actually wire up against a real host client — auth
  headers, cookies, CORS — not just the stub client the Phase 5 tests used
- does a mutation hook's onSuccess actually invalidate the right query keys and refetch
- does pagination actually paginate against real data (next/previous, not an empty list)
- does the error envelope render the way the hand-written type in types.ts claims — this is
  the one shape with no generator behind it (§12), so it's still the only place this gets
  checked against a real error response
- anything environment-dependent: does the throttle_scope rate-limit for real, does a
  signal/task side effect actually fire

Report any discrepancy, and which of the two halves is actually wrong.
```

**Verify:** every hook round-trips against the real backend with correct runtime behaviour —
auth, cache invalidation, pagination, and the error envelope shape all confirmed live.

If a genuine type-level discrepancy still turns up here, that means a CI gate (§10.1) has a
hole — `--fail-on-warn` missed something, or a hand-written type in `types.ts` duplicated
rather than re-exported a generated one. Fix the immediate discrepancy, but also go back and
close the gap in the gate itself; this phase catching it means it was going to reach a host.

### Phase 7 — README (the config block)

```
Phase 7: README.md. docs/APP-DESIGN.md §8 is the required structure — every section.

Fill it from what we actually built, not from CONTRACT.md — the code is the truth now, and if
they disagree that's a bug to report, not paper over. Include:
installation (both halves) · compatibility · settings block · required/optional .env keys ·
URL mounting · migrations · signals table with exact payloads · services table with exact
signatures · test helpers note (factory-boy in the host's test group) · recommended periodic
schedule · suggested Jazzmin icon · frontend install and usage.

The settings/URL blocks must be copy-pasteable into a host with zero edits. Verify by copying
them into playground/backend and confirming it still boots.

Then list every place README, CONTRACT.md, and the code disagree.
```

**Verify:** copy the README's blocks into a fresh playground config and it boots. This is the
one test of README quality that means anything.

### Phase 8 — CI, changelog, first release

Every app package in this ecosystem is public and publishes **both** halves to a public
registry, automatically, on tag push — this is the standard shape (`APP-DESIGN.md` §10.2), not
something bolted on after the fact. Do the name-collision check and README sync **before**
writing any CI or registering any trusted publisher — a name collision found after code, docs,
and a first release exist is a breaking rename; found now, it's a five-minute fix.

```
Phase 8: CI and release.

1. Check the package's chosen name is free on BOTH registries before anything else — search
   pypi.org and npmjs.com for the exact name. If either is taken, this needs a prefixed name
   (the org account name is the usual choice, e.g. "yourorg-notifications-app" /
   "@yourorg/notifications-app") in EVERY file before continuing, not just the taken registry's
   side — see docs/CONTRACT.md §22 for the appkit precedent, including the pyproject.toml
   [project.urls]-placement pitfall if you add that table (§3.1's own note).
2. README sync (APP-DESIGN.md §8's README-sync note): `backend/pyproject.toml` declares
   `readme = "README.md"` (never "../README.md" — silently produces an empty PyPI description,
   §3.1). Copy the finished README.md from Phase 7 into backend/README.md and
   frontend/README.md verbatim. Add [project.urls] to pyproject.toml and homepage/bugs to
   package.json, pointing at the real repo.
3. .github/workflows/ci.yml — the caller from docs/APP-DESIGN.md §10.2, with
   `publish-npm: true` in the `with:` block AND a `publish-pypi` job committed alongside it
   (copy §10.2's template verbatim — it cannot live in the shared reusable workflow, see that
   section's own explanation of why PyPI and npm have opposite rules here). If the org reusable
   workflow doesn't exist yet, write it in full per §10.1 (including the OIDC-based
   `publish-npm` job, its `npm-environment` input, and the `readme-contract` job's README-sync
   check) and tell me it needs to be committed to yourorg/.github separately.
4. CHANGELOG.md — Keep a Changelog format per §11.3, with a 1.0.0 entry.
5. Verify version lockstep: backend/pyproject.toml, frontend/package.json, CHANGELOG.md all
   at 1.0.0.
6. Walk the security checklist in §9 item by item and report each as verified-or-not, with
   the evidence. Don't mark anything verified you haven't actually checked.
7. Walk the frontend security checklist in §12 the same way.
8. Register both trusted publishers before the first tag, not after:
   - PyPI: a *pending* trusted publisher (Publishing → Add a new pending publisher) naming this
     repo, `ci.yml`, and an environment (e.g. `publish-pypi`) — this works before the PyPI
     project exists at all.
   - npm: needs the package to exist first — `cd frontend && npm run build && npm publish
     --access public` by hand, once — then link the repo as a Trusted Publisher on npmjs.com
     (package → Settings), naming `ci.yml` and, if the config asks for one, a GitHub environment
     (set the reusable workflow's `npm-environment` input to match if it isn't the default
     `"publish-npm"`).
   - Create both named GitHub environments on this repo (Settings → Environments, no protection
     rules needed) — a trusted publisher naming an environment that doesn't exist on the repo,
     or isn't set on the job, fails every publish with a claim mismatch on either registry.

Then give me the exact commands to tag and push v1.0.0.
```

**Verify:** CI green on a PR; after the tag push, both the frontend package on the npm registry
and the backend package on PyPI appear under their published names, each showing a real
description/readme (check the registry page or its JSON API directly — an empty description is
the one failure mode CI cannot catch on its own, since the file being present and its content
actually rendering are different questions); then tag, push, and confirm the tag-match assertion
passes on both.

### Phase 9 — Install it into a real host

```
Phase 9: real-world verification. In a fresh clone of base-scaffold, install this package at
v1.0.0 following docs/INTEGRATION-GUIDE.md §2 — all 15 steps, using only README.md for
configuration values. Don't use anything you know from building the package.

Report every step that didn't work as documented, every value the README omitted, and every
place you had to guess. Then fix the README.
```

This is the real acceptance test. A package that installs cleanly into a scaffold you didn't
special-case is a package that will install into project number four.

Finally: add the app to the registry (`BASE-DESIGN.md` §11.3).

---

## 3. Prompt patterns specific to app packages

**Make the boundary a question, not a rule.** Rules get followed until they're inconvenient.
Periodically ask outright:

> "List everything in this package that depends on something outside it. For each, say whether
> it's `settings.AUTH_USER_MODEL` (allowed), an import from `appkit` declared in
> `pyproject.toml`/`package.json` (allowed — see `APP-DESIGN.md` §1.1), or a coupling we need
> to fix."

Run this at the end of phases 3, 4, and 5. It reliably surfaces things a checklist walk-through
misses, because it asks the agent to enumerate rather than to confirm.

**Ask for the host's perspective.** The best review question for an app package:

> "You're an agent in a host project that just installed this at v1.0.0, with only README.md
> to work from. Walk through wiring it up and tell me everywhere you'd have to guess."

**Force the version-impact question on every change** after v1.0.0:

> "Is this a major, minor, or patch bump, and why? Check specifically whether any signal
> payload, service signature, factory name, settings key, throttle scope, or exported hook
> changed."

**Refuse convenient coupling explicitly** when you see it in a plan:

> "You're proposing this app import `payments_app.models`. Don't. Give me two decoupled
> alternatives per `docs/APP-DESIGN.md` §6, including the option that these are really one
> package."

---

## 4. Adding a feature to an existing app package

The short loop, once v1.0.0 exists:

1. **Update `docs/CONTRACT.md` first.** If the feature adds a signal, service, endpoint,
   setting, or hook, it changes the contract — write it there before implementing, same as
   Phase 0.
2. **Both halves in the same PR.** A new endpoint without its hook is half a feature and
   guarantees the halves drift.
3. **Tests in the same PR.** Coverage threshold enforces this, which is the point.
4. **Playground check** if the API surface changed at all.
5. **README + CHANGELOG** in the same PR, with a **Host action:** line if hosts must change
   anything.
6. **Version bump in all three places**, then tag.

The prompt:

```
Add {{feature}} to this app package.

First update docs/CONTRACT.md with the new signals/services/endpoints/settings/hooks and
show me the diff — I'll approve before you implement.

Then implement both halves plus tests, update README.md and CHANGELOG.md (with a Host action:
line if a host must change anything), and tell me the version bump and why.

Same constraints as always: no cross-app imports, no host-specific imports, namespaced
everything, signal payloads documented exactly.
```

---

## 5. Failure modes specific to app packages

Ranked by how often they happen and how much they cost:

| Symptom | Cause | Why it's expensive |
|---|---|---|
| Two apps can't be installed together | exact pins on `django`/`drf` instead of ranges (§1.1) | Discovered by a host mid-project; needs a release on the app to fix |
| Host's `core/` receiver breaks after a minor upgrade | signal payload changed without a major bump (§6) | Fails in a background task, in production, silently |
| Hook returns `undefined` for a field the API sends | `types.ts` drifted from serializers | Was: only caught by the playground (Phase 6) or by a host. Now: caught by CI before the commit lands — §12's generated types make this the same class of bug as a missing migration |
| Templates/translations missing after install | package data not declared (§2) | Looks like a host misconfiguration; wastes hours on the wrong side |
| App works in the first host, breaks in the second | an assumption about host structure (`tools/`, a settings key, a URL prefix) | The failure the whole architecture exists to prevent |
| Two copies of React in a host | `react` in `dependencies` not `peerDependencies` (§12) | Bizarre hook errors with no obvious cause |
| Two copies of `appkit` in a host | `@hjtdev/appkit` in `dependencies` not `peerDependencies` on the frontend half (§12) | Same shape as the React row, now equally likely since every app declares `@hjtdev/appkit` — `useApiClient` returns `null` in half the tree |
| Throttle scope collides with another app | scope not namespaced (`APP-DESIGN.md` §1.2) | Two correct apps rate-limit each other |
| `factory-boy` in production installs | factories' dependency in `[project.dependencies]` | Ships test tooling to every host |

Every one of these is caught by something in `APP-DESIGN.md` §10's CI —
`resolution-matrix` for the first, `wheel-smoke-test` for the fourth, `no-inter-app-imports`
for the fifth, the lockstep job for the second, the `schema.yml`/`schema.d.ts` diff checks
(§12) for the third. **That's the argument for building CI in Phase 8 rather than "later"**:
each of these bugs is discovered by a host project, at the worst possible time, if the gate
isn't there. The third row used to be the one exception — the only failure mode in this table
with no CI gate behind it, caught only by a human clicking through Phase 6. It isn't anymore.

---

## 6. Templatize after the second one

Build app #1 and #2 with the phases above. By #3, most of phases 1, 6, 7, and 8 are identical
boilerplate — that's the signal to turn them into a template (`BASE-DESIGN.md` §11.2):

```
Using this repo as the reference, create a copier template that generates a new app package
skeleton. It should prompt for: package name, module name, whether it has a frontend half,
and the initial settings/.env keys — then emit a repo that already passes CI with no business
logic in it: pyproject.toml with the tooling and banned-api config, MANIFEST.in, the empty
module files with docstrings, tests/backend/settings.py, the playground, the CI caller
workflow, CHANGELOG.md, and a README with the §8 section headings stubbed out.

Then generate one from it and verify CI passes on the empty package.
```

`copier` over a plain template repo, specifically because it can update already-generated
projects when the template improves — which matters when the standard itself is still evolving,
as this one is.

---

## 7. Done means

- [ ] `docs/CONTRACT.md` and the code agree; `README.md` and the code agree.
- [ ] Both halves at the same version, in all three places; CI's lockstep job green.
- [ ] `uv run pytest` and `npm run test` green, over the coverage threshold.
- [ ] `ruff`, `mypy`, `tsc --noEmit`, `eslint` all clean.
- [ ] Zero imports of another app package; zero imports of anything host-specific.
- [ ] Every emitted signal has a test asserting its exact documented payload.
- [ ] Every endpoint has a 403-on-someone-else's-object test that actually fails when the
      permission check is removed.
- [ ] Playground verified: every hook round-trips with no type discrepancy.
- [ ] `wheel-smoke-test` passes — templates and translations really are in the wheel.
- [ ] `resolution-matrix` passes at both `lowest-direct` and `highest`.
- [ ] Security checklists (§9 and §12) walked with evidence, not assumed.
- [ ] Installed into a fresh `base-scaffold` clone using only the README.
- [ ] `backend/README.md` and `frontend/README.md` are current copies of the root `README.md`
      (`readme-contract` CI job green); `[project.urls]`/`homepage`/`bugs` point at the real repo.
- [ ] Tagged `v1.0.0`; PyPI and npm entries both added, each showing a real, non-empty
      description on the registry page or its JSON API — checked directly, not assumed from a
      green CI run, since a present-but-empty readme is a metadata bug CI's `readme-contract`
      job (checked before the tag) covers but a real registry check confirms end to end.
