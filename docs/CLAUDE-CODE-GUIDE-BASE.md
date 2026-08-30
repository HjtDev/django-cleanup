# CLAUDE-CODE-GUIDE-BASE.md — Building the Base Scaffold with Claude Code

How to get from an empty directory to a working, CI-green `base-scaffold` repo, using Claude
Code as the implementer. This is a **one-time build**: every future project clones the result,
so time spent getting it right here is multiplied by every project you ever start, and so is
every mistake.

> Companion: `CLAUDE-CODE-GUIDE-APP.md` (same treatment for an app package).

---

## 0. The operating principle

The single biggest determinant of output quality is not prompt wording — it's **what's in the
context window and how the work is chunked.** Three rules carry most of the weight:

1. **The design docs are the spec.** Don't paraphrase them into a prompt. Put them on disk in
   the repo and tell the agent to read them. A paraphrase drops exactly the constraint that
   later turns out to matter.
2. **One phase per session.** A phase is "produce these 3–8 files and prove they work."
   Long sessions degrade: earlier decisions fall out of context, and the agent starts
   contradicting work it did an hour ago. End the session at a verified, committed checkpoint.
3. **Every phase ends with a command that either passes or fails.** "Looks right" is not a
   checkpoint. `uv run python manage.py check`, `make test`, `docker compose up --build` —
   something that returns an exit code. This is what stops plausible-but-broken code from
   compounding.

A fourth, softer rule: **review the diff of every phase yourself.** This scaffold is the
foundation of every future project. Reading ~400 lines of diff eight times is a cheap price
for not discovering a subtle settings mistake replicated across six client projects.

---

## 1. Before you open Claude Code

### 1.1 Create the repo skeleton and drop in the spec

```bash
mkdir base-scaffold && cd base-scaffold
git init
mkdir -p docs
cp /path/to/BASE-DESIGN.md        docs/
cp /path/to/APP-DESIGN.md         docs/
cp /path/to/INTEGRATION-GUIDE.md  docs/
cp /path/to/CLAUDE.md.template    ./CLAUDE.md.template
```

Why on disk and not pasted into chat: Claude Code reads files on demand, cheaply, at any point
in the session — including three phases later, when a pasted-once document has long since
scrolled out of context. It also means the docs are in the repo for every project cloned from
it, which is what makes `CLAUDE.md` able to say "read `docs/INTEGRATION-GUIDE.md`."

### 1.2 Write the scaffold's own `CLAUDE.md` — before writing any code

This is the highest-leverage twenty minutes of the whole build. It's read on every turn, so
it's what keeps the agent's behavior stable across eight sessions.

The shape — abridged here; this repo's own root `CLAUDE.md` is the current, complete version
and is what you should actually copy from, not this excerpt:

```markdown
# CLAUDE.md — base-scaffold (the template itself)

This repo is a one-time starter kit, not a running project: projects clone it, delete .git,
and own the result. There is no upstream pull, so a mistake here propagates into every future
project and has to be fixed N times. Bias hard toward correctness over speed.

## The spec
`docs/BASE-DESIGN.md` is authoritative for everything in this repo. Read the relevant section
before implementing — do not infer structure from convention or memory. `docs/APP-DESIGN.md`
and `docs/INTEGRATION-GUIDE.md` describe what will be installed into this scaffold later;
consult them whenever a decision here constrains them.

When this repo and the spec disagree, the spec wins — unless you believe the spec is wrong,
in which case **stop and say so** rather than silently implementing something better.

## Pinned versions & defaults
A table of the concrete version/tooling decisions behind this build — see §1.3 below for how
to fill it in. Cite the table instead of re-deriving a version from spec prose, and update it
in lockstep with every file a version is baked into (`.python-version`, Docker base images,
`pyproject.toml`, `package.json`, CI workflow).

## Non-negotiables for this repo
- `uv` only. No `requirements.txt`, no `pip install`, anywhere, ever.
- Postgres only. No SQLite, including in tests.
- Django 6+ on ASGI. No `gunicorn`, no `wsgi:application` in any run command.
- No authentication anywhere in this scaffold — auth is an installed app package.
- Nothing project-specific. No client names, no business logic, no domain models.
  Placeholders where a project must fill something in.
- Dev and prod are separate Dockerfiles and separate compose files. Never one shared.
- Prod containers run as a non-root user. Dev may run as root (bind-mount ownership).
- Every secret comes from .env via decouple.config, with no default for required values.

## Working agreement
- Implement one phase at a time. Do not create files outside the current phase's scope.
- Before writing a file that the spec shows, re-read that part of the spec.
- After each phase, run the phase's verification command and paste the real output.
  Never report success you haven't observed.
- If something in the spec is ambiguous or looks wrong, ask. Do not guess and proceed.
- Prefer boring, explicit, standard code. Cleverness here is a liability: this code gets
  read and modified by people (and agents) who have never seen it before.

## Git protocol
A commit-message format and review-before-commit protocol belongs here too — see this
repo's own root `CLAUDE.md` for the exact wording to reuse; it's a fixed protocol, not
something to re-derive per project.
```

### 1.3 Decide the handful of things the spec leaves open

Answer these before starting; each one is cheap now and annoying to change in phase 6:

| Decision | Reasonable default |
|---|---|
| Python version | 3.14 (must match `.python-version` and the Docker base image) |
| Node version | 24 LTS |
| Postgres version | 17 |
| Redis version | 7 |
| uv version | 0.11 — must track the toolchain that writes `backend/uv.lock`; see CLAUDE.md's pinned-versions table for why the pin isn't cosmetic |
| Package manager (frontend) | `npm` — switch to `pnpm` only if you've decided deliberately |
| Placeholder project name | `myproject` (what `rename-project.sh` replaces) |
| GitHub org | your real org, since it appears in install commands |
| Coverage threshold | 80% for the host scaffold |
| Sentry | included, inert without a DSN |

---

## 2. The build, phase by phase

Each phase below gives: the goal, the prompt to paste, and the verification that ends it.
Start a **fresh session** for each phase. Begin every session with the same two-line preamble:

> Read `CLAUDE.md`, then read `docs/BASE-DESIGN.md` §{{N}}. We're doing Phase {{N}} only —
> don't create files outside its scope. Tell me your plan before writing anything.

Asking for the plan first is not ceremony: it surfaces a misread of the spec in twenty seconds
instead of after 400 lines of generated code.

### Phase 1 — Repo skeleton, `uv` project, tooling config

**Goal:** the directory tree from §2, `backend/pyproject.toml` complete with dependencies,
dependency groups, and ruff/mypy/pytest config, plus `.gitignore`, `.dockerignore` files,
`.python-version`, `.pre-commit-config.yaml`.

```
Phase 1: repo skeleton and Python toolchain.

Create the directory structure exactly as in docs/BASE-DESIGN.md §2 (empty dirs get a
.gitkeep), then:

1. backend/pyproject.toml — dependencies, [dependency-groups] dev + test, [tool.uv]
   default-groups, and the ruff / mypy / pytest / coverage config, all per §4.2 and §5.
   Include the commented [tool.uv.sources] block from §4.2 verbatim — it's documentation.
   Include the flake8-tidy-imports banned-api section from §5.1 with a comment explaining
   that a line is added per installed app.
2. .python-version, .gitignore, backend/.dockerignore, frontend/.dockerignore,
   .pre-commit-config.yaml (§3.6 of docs/APP-DESIGN.md is the reference format).
3. Run `uv sync` in backend/ and paste the real output.

Do NOT create Django files, Docker files, or anything frontend yet.
```

**Verify:** `cd backend && uv sync` succeeds; `uv run ruff check .` runs (nothing to lint yet
is fine); `uv.lock` exists and is committed.

**Review for:** ranges vs. pins in `dependencies` (§4.2 wants the host pinning tightly — the
*opposite* of the app rule, and an easy thing for an agent to get backwards); `default-groups`
present; `.dockerignore` actually excludes `.venv` and `node_modules`.

### Phase 2 — Django project: settings, logging, health, ASGI, Celery

**Goal:** a Django project that boots, with settings, environment handling, split logging,
`/healthz/`, ASGI, and Celery wired.

```
Phase 2: the Django project. Read docs/BASE-DESIGN.md §3 and §4 again first.

Create:
- backend/manage.py, config/{__init__,settings,urls,asgi,wsgi,celery}.py
- config/logging.py — build_logging_config(debug) returning colored console config when
  debug else structlog JSON, both with a request id. §3.
- config/views.py — healthz: checks DB with SELECT 1 and Redis with ping, returns 503 if
  either fails, unauthenticated, exempt from throttling, excluded from Sentry sampling.
- backend/.env.example and backend/.env.prod.example — every key, commented, no real values.
- The startup validation from §4.3: a Django system check that fails when DEBUG is off and
  SECRET_KEY is the example value, or ALLOWED_HOSTS is empty or ["*"].
- Sentry init behind an empty-by-default SENTRY_DSN, with django + celery integrations.

settings.py must contain NO auth configuration of any kind — auth is an installed app
package (§3). INSTALLED_APPS gets a clearly marked comment showing where app packages go.

Then create a throwaway backend/.env from the example and run
`uv run python manage.py check` and `uv run python manage.py check --deploy`.
Paste both outputs.
```

**Verify:** both `check` commands pass (deploy warnings about SSL are expected without a real
prod env; note them, don't suppress them).

**Review for:** `SECRET_KEY` having no default; `Csv()` used for `ALLOWED_HOSTS`; no auth
anywhere; `celery.py` autodiscovering tasks so installed apps' `tasks.py` is picked up;
`/healthz/` actually touching both DB and Redis rather than returning a bare 200.

### Phase 3 — `core/`, `tools/`, and the test stack

**Goal:** the mediator layer and shared helpers, with their tests — plus the ephemeral
Postgres/Redis stack the test suite needs to run against Postgres at all (§5.3), pulled
forward from Phase 5 because nothing before this phase has tests to run yet, and no phase
before Phase 5 otherwise has a compose file for it to live in.

```
Phase 3: core/, tools/, and the test stack. Read docs/BASE-DESIGN.md §5.3, §5.4, §6, and
docs/INTEGRATION-GUIDE.md §4 + §6.

Create:
- core/{__init__,apps}.py with CoreConfig whose ready() imports core.signals
- core/signals.py — empty except a module docstring explaining the pattern and one
  fully-commented-out worked example (the payment→notification one from
  INTEGRATION-GUIDE.md §4, including transaction.on_commit and the **kwargs rule)
- core/services/__init__.py — same treatment: docstring + commented example
- core/views/__init__.py, core/tests/__init__.py
- tools/{mixins,cache,crypto}.py per §3 — real, working implementations, not stubs
- backend/conftest.py — api_client, user, admin_user, auth_client fixtures (§5.2)
- core/tests/conftest.py — placeholder with a comment showing the cross-app factory pattern
- tools/tests/ — real tests for crypto round-trip, cache helper, and the mixins' error shape
- config/tests/ — the two wiring smoke tests from §5.4: /api/schema/ returns 200 with
  expected tags, and every throttle_scope in the codebase exists in DEFAULT_THROTTLE_RATES
- docker-compose.test.yml per §5.3 — ephemeral Postgres + Redis on non-default ports, both
  with healthchecks, so `up -d --wait` actually blocks on both before pytest connects
- The Makefile's `test` target per §5.3 — brings the test stack up, exports the
  non-default-port credentials, runs `uv run pytest -n auto -m "not slow"`, tears the stack
  down. This is the only Makefile target this phase adds; the rest wait for Phase 5's
  compose file and Phase 8's polish.

Add core to INSTALLED_APPS. Then run `make test` (not a bare `uv run pytest` — the suite
must run against real Postgres, never SQLite) and paste the output.
```

**Verify:** `make test` passes with real (non-trivial) tests for `tools/`, against the
ephemeral Postgres/Redis stack, not SQLite.

**Review for:** commented examples being *correct* — they're the pattern every future project
copies, so a subtly wrong one propagates. Check `on_commit` is there, `**kwargs` is there,
and `CoreConfig.ready()` imports signals.

### Phase 4 — Frontend baseline

**Goal:** a Next.js app that builds, with the shared query client and API client every
installed SDK plugs into.

```
Phase 4: the Next.js frontend. Read docs/BASE-DESIGN.md §2 and §3, and
docs/APP-DESIGN.md §12 for what installed SDKs will expect from lib/.

Create a Next.js App Router app in frontend/ with TypeScript strict mode:
- package.json (npm, Node 24), tsconfig.json with strict + noUncheckedIndexedAccess,
  next.config.ts with output: "standalone", eslint.config.mjs, vitest.config.ts
- .prettierrc, .prettierignore, and `format`/`format:check` scripts in package.json — §7's
  CI and §10.2's `make fmt`/`make lint` both require them from the first commit, not added
  later
- lib/query-client.ts — the single shared QueryClient with sensible defaults
  (staleTime, retry policy) and a comment noting installed app SDKs depend on this
  being mounted, per APP-DESIGN.md §12's peer-dependency contract
- lib/api-client.ts — typed fetcher: base URL from NEXT_PUBLIC_API_URL, credentials
  handling, one consistent error shape. This is what app SDKs' own clients plug into.
- app/layout.tsx mounting QueryClientProvider
- app/page.tsx — a minimal placeholder that calls /healthz/ and shows backend status,
  so a fresh clone visibly proves the two halves are talking
- app/api/health/route.ts — the frontend healthcheck target from §8.2
- .env.example with NEXT_PUBLIC_API_URL
- tests/ — at least one real test per lib/ module (query-client, api-client). A vitest
  suite with zero test files exits non-zero, and §7's CI runs `npm run test -- --run`
  starting this phase, not later — an empty suite here fails CI on the very next phase.

Then run `npm ci`, `npx tsc --noEmit`, `npm run lint`, `npm run format:check`,
`npm run test -- --run`, `npm run build` and paste the output.
```

**Verify:** all six commands pass.

**Review for:** `output: "standalone"` present (phase 5's Dockerfile depends on it); no
hardcoded `localhost:8000` outside `.env.example`; `strict: true`.

### Phase 5 — Docker & Compose

**Goal:** four Dockerfiles and three compose files, all working.

```
Phase 5: Docker. Read docs/BASE-DESIGN.md §8 in full — every code block there is the target.

Create:
- backend/Dockerfile.prod — uv-based multi-stage, BuildKit cache mounts, UV_LINK_MODE=copy,
  UV_COMPILE_BYTECODE=1, git in builder only, non-root uid 10001, no migrate on boot,
  uvicorn with --proxy-headers and worker count from an env var
- backend/Dockerfile — dev, single-stage, dev+test groups, migrate+runserver on boot,
  UV_PROJECT_ENVIRONMENT outside the bind mount (see the .venv gotcha in §8.1)
- frontend/Dockerfile.prod — deps/builder/runner, standalone output, non-root,
  NEXT_PUBLIC_API_URL as a build ARG
- frontend/Dockerfile — dev, bind-mounted, npm run dev
- docker-compose.yml — db, redis, backend, frontend, celery, celery-beat; flower and
  mailpit (not mailhog — see §8.2) behind a "tooling" profile; healthchecks on ALL of
  db/redis/backend/celery/celery-beat/frontend per §8.2; depends_on with
  condition: service_healthy; container_name from ${PROJECT_NAME}
- docker-compose.prod.yml — Dockerfile.prod, no bind mounts, ports bound to 127.0.0.1,
  resource limits, json-file log rotation, no-new-privileges

docker-compose.test.yml is NOT this phase's work — it was pulled forward to Phase 3 because
§5.3's test target needed it before Phase 5 existed. Verify it's already correct rather than
recreating it.

Then: `docker compose up --build`, wait for every service to report healthy, and paste
`docker compose ps` showing the health column. Then `docker compose -f docker-compose.prod.yml
build` to prove the prod path builds too.
```

**Verify:** dev stack all-healthy in `docker compose ps`; prod images build; `curl
localhost:8000/healthz/` returns 200; `localhost:3000` loads and shows backend status.

**Review for:** this is the phase where an agent is most likely to produce something
plausible-but-wrong. Specifically check: `UV_LINK_MODE=copy` present (its absence causes
runtime `ImportError`s that only appear in the final stage); the `.venv` shadowing fix in dev;
prod not mounting source; prod actually running as the non-root user (`docker compose -f
docker-compose.prod.yml run --rm backend whoami`); healthchecks on all six services, not just
backend. Also check, empirically rather than by reading the spec — §8 shipped with several
defects that only a real build/run surfaces: the `frontend`
healthcheck resolving `localhost` on Alpine/musl, the `celery-beat` healthcheck's pidfile,
the `uv` image pin against `backend/uv.lock`'s actual revision, and whether `--no-dev` really
excludes every non-production dependency group.

### Phase 6 — CI

**Goal:** `.github/workflows/ci.yml` per §7, green.

```
Phase 6: CI. Read docs/BASE-DESIGN.md §7 and implement .github/workflows/ci.yml exactly as
specified — backend-quality, backend-tests (with postgres + redis services), frontend,
docker-build, security-audit.

Also create renovate.json per §7: uv.lock, package-lock.json, Docker base image digests,
GitHub Action versions, pre-commit revs, and the git+…@vX.Y.Z app package refs; patch/minor
grouped weekly, majors separate.

Note in your summary which secrets I need to add in GitHub settings before this passes.
```

**Verify:** push a branch, open a PR, watch it go green. `uv sync --locked` in CI is the check
that proves phases 1–5 committed a consistent lockfile.

**Review for:** `--locked` (not `--frozen`) in the sync steps; the `makemigrations --check`
step present; `docker-build` actually building the *prod* Dockerfiles.

### Phase 7 — Deploy script

**Goal:** `deploy/deploy-prod.sh` per §9, plus its env template.

```
Phase 7: deployment. Read docs/BASE-DESIGN.md §9 and write deploy/deploy-prod.sh
implementing all 8 steps in order, plus the two additions: --backup-db (pg_dump before
migrations) and a header comment explaining the backward-compatible-migration rule.

Requirements: `set -euo pipefail`; a usage/--help; validate deploy.prod.env and repo root
and a clean git tree before doing anything; every rsync exclude from §9 step 2; bounded
retries on the health poll with the last 100 log lines dumped on failure; verify every
container is healthy (not just running); nginx -t before reload; --follow flag.

Add deploy/deploy.prod.env.example. Run `shellcheck deploy/deploy-prod.sh` and `bash -n`,
and paste the output. Do not attempt a real deploy.
```

**Verify:** `shellcheck` clean; `./deploy/deploy-prod.sh --help` works; running it without a
`deploy.prod.env` fails loudly with a useful message.

**Review for:** `set -euo pipefail` at the top; no secret ever echoed; migrations after the
health gate, not before; `.env` files in the rsync excludes.

### Phase 8 — `Makefile`, `CLAUDE.md` template, rename script, README

**Goal:** the ergonomics layer that makes a fresh clone pleasant.

```
Phase 8: developer ergonomics.

- Makefile per docs/BASE-DESIGN.md §10.2, with a self-documenting help target — but the
  compose-stack targets (up/down/stop/ps/logs/shell/migrate/migrations/superuser/backup)
  already exist as of Phase 5, which is when docker-compose.yml first exists for them to
  wrap (same reasoning as pulling docker-compose.test.yml forward to Phase 3). This phase
  adds what's left: lint/fmt/typecheck/django-checks/test/build/check/deploy.
- scripts/rename-project.sh per §11.1 — replaces the placeholder project name across every
  tracked file that actually contains it (derive the list by grepping, don't hardcode it —
  §11.1's original file list was wrong in both directions); must be idempotent and must print
  what it changed
- This repo's own root CLAUDE.md is the scaffold's authoring instructions, not a host
  project's, and rename-project.sh must never write over it. CLAUDE.md.template (root, both
  variants) is what rename-project.sh renders the host-project CLAUDE.md from, at clone time,
  with placeholders it can fill in and {{...}} left for the ones it can't (§10.1)
- README.md — enough for a developer or an agent arriving at a cloned project to work
  productively without reading the design docs first: the §10 bootstrap walkthrough
  (verbatim and tested), the ownership model, the full Makefile target table, how to
  install an app package, where code goes, the `.env` inventory, what `make check` covers,
  deployment in brief, and a troubleshooting section for the gotchas this build actually
  hit (rebuild-vs-restart, the `.venv` bind-mount shadowing, `uv.lock`/`--locked` failures,
  the `tooling` profile). Scannable — headings and tables, not prose walls; this README is
  read once per project on day one and then grepped.

Then run every make target that doesn't need a server and paste the output.
```

**Verify:** `make help` lists everything; `make check` passes end to end; `make lint`, `fmt`,
`typecheck`, `test` all work.

### Phase 9 — Prove it from scratch

The phase people skip, and the only one that proves the thing works.

```
Phase 9: fresh-clone verification. `git clone` the repo into a new directory — not a copy of
the working tree — and do exactly what a new project would do from there, following
README.md literally. No shortcuts, no using knowledge from building it, and don't reuse a
directory that ever had `git add -A`/`git add .` run in it: a `git clone` is what proves
nothing needed by a build is only sitting on disk uncommitted or silently gitignored (Phase 5
found exactly this — an unanchored `.gitignore` pattern had excluded `frontend/lib/` for two
phases without a build ever failing locally). Build both `docker-compose.yml` and
`docker-compose.prod.yml` from the clone, not just `docker compose up`.

Then report: every step that didn't work as written, every command that needed a flag the
README omitted, and every place the walkthrough was ambiguous. Fix the README to match
reality; don't fix reality to match the README unless something is genuinely broken.
```

**Verify:** a clean clone reaches "all containers healthy, superuser created, Swagger loads,
frontend shows backend status" following only the README.

Then, ideally: **install one real app package into the fresh clone** following
`INTEGRATION-GUIDE.md` §2. Nothing else validates the scaffold's actual purpose. If you don't
have an app package yet, come back and do this after building your first one — it will find
problems in both.

---

## 3. Prompt patterns that work here

**Point at the spec, don't restate it.**
> ✅ "Implement `docker-compose.prod.yml` per `docs/BASE-DESIGN.md` §8.2, including every
> production-only hardening item in that section."
> ❌ "Make a prod compose file with resource limits and log rotation and healthchecks and…"

The first inherits every constraint including the ones you forgot; the second silently drops
them.

**Ask for the plan before the code**, on any phase touching more than three files. Twenty
seconds of plan review beats reviewing 400 lines of a misread spec.

**Demand real output.**
> "Run it and paste the actual output. If it fails, show me the failure — don't fix it and
> report success."

**Make disagreement a first-class option.**
> "If any part of §8 looks wrong or contradicts §4, stop and tell me rather than picking one."

This is the prompt that catches spec bugs. The docs are good but not infallible, and an agent
that's been told to just comply will implement a contradiction rather than surface it.

**Use `/clear` between phases**, and re-read `CLAUDE.md` at the start of each. A single session
carrying nine phases will start contradicting phase 2 by phase 7.

**When a phase goes wrong, revert rather than patch.** `git checkout .`, then re-prompt with
the specific constraint that was missed added explicitly. Iteratively patching a wrong
foundation produces something that works and that nobody can read.

---

## 4. Failure modes specific to this scaffold

Things to check for explicitly, because they're what an agent gets wrong here:

| Symptom | Cause | Where |
|---|---|---|
| `ImportError` in the prod container only | `UV_LINK_MODE=copy` missing — hardlinks point into the discarded cache mount | §8.1 |
| `makemigrations` fails in dev with permission errors | container running as non-root against a bind mount | §8.1 |
| Host's `.venv` shadows the container's | bind mount over `/app` with the venv inside it | §8.1 |
| `uv sync --locked` fails in CI | `pyproject.toml` hand-edited without re-locking | §7 |
| App packages pinned tightly in the *host* | correct here — but check the agent didn't apply the app rule (§APP 1.1) to the host by mistake | §4.2 |
| `requirements.txt` reappears | training-data pull toward the familiar Django Dockerfile | everywhere |
| `gunicorn` in a run command | same | §8.1 |
| SQLite in test settings | same | §5.3 |
| Auth config in `settings.py` | same — this scaffold is deliberately auth-less | §3 |
| Healthcheck returns 200 while the DB is down | `/healthz/` not actually querying anything | §8.2 |

The last four in that list share a cause worth naming: an agent's prior on "Django project
scaffold" is strong and *differs from this design* in exactly these places. Re-stating them in
`CLAUDE.md` (§1.2) is what suppresses the pull, and it's why they're listed there as
non-negotiables rather than left implicit in the spec.

---

## 5. Done means

- [ ] Fresh clone → all containers healthy, following only `README.md`.
- [ ] `make check` green.
- [ ] CI green on a PR, including `docker-build`.
- [ ] Prod images build, run as non-root, and contain no `git`, no `uv`, no dev dependencies.
- [ ] `shellcheck` clean on `deploy-prod.sh`; it fails loudly with no config.
- [ ] No `requirements.txt`, no `pip install`, no `gunicorn`, no SQLite, no auth config
      anywhere in the repo.
- [ ] `docs/` contains all three design documents; `CLAUDE.md` points at them.
- [ ] At least one real app package installed into a fresh clone successfully.
- [ ] Tagged `v1.0.0`, so `git commit -m "initial commit from base-scaffold v1.0.0"` in a new
      project means something specific.
