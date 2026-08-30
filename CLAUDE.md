# graphify

This project has a knowledge graph at graphify-out/ with god nodes, community structure, and cross-file relationships.

Rules:
- For codebase questions, first run `graphify query "<question>"` when graphify-out/graph.json exists. Use `graphify path "<A>" "<B>"` for relationships and `graphify explain "<concept>"` for focused concepts. These return a scoped subgraph, usually much smaller than GRAPH_REPORT.md or raw grep output.
- If graphify-out/wiki/index.md exists, use it for broad navigation instead of raw source browsing.
- Read graphify-out/GRAPH_REPORT.md only for broad architecture review or when query/path/explain do not surface enough context.
- After modifying code, run `graphify update .` to keep the graph current (AST-only, no API cost).

# CLAUDE.md — hjtdev-django-cleanup (app package #2)

A standalone, versioned, dual-package Django + React app package that auto-hooks every model
with a `FileField`/`ImageField` in a host project (via upstream `django-cleanup`, a declared
dependency), scans configured storage for **orphaned files** (on disk, referenced by nothing),
gives a Jazzmin admin page to review and delete them, and keeps a full history of every cleanup —
automatic (per-save/per-delete) and manual (a full scan). It depends on `appkit` (app package #1)
for the cache mixin, error envelope, permissions, and `HttpClient`/provider, exactly like every
other app in this ecosystem.

**Read `docs/APP-DESIGN.md` in full before making changes.** For the actual build order, use
**`docs/CLAUDE-CODE-GUIDE-APP-MEDIA-CLEANUP.md`** — it is this project's own pre-customized
instance of `docs/CLAUDE-CODE-GUIDE-APP.md`, with every phase prompt, model, endpoint, setting,
and hook already decided so a phase session is paste-and-go instead of a re-derive-the-prompt
session. Once `docs/CONTRACT.md` exists (Phase 0), read that too — it's the frozen contract this
file's summary reflects. This file is the fast reference; the guide is the map.

## The rules that define this package

1. **Two declared dependencies, and nothing else.** `appkit` (cache mixin, error envelope,
   permissions, pagination, `HttpClient`/provider) and `django-cleanup` (upstream — auto file
   deletion on save/delete, imported as `django_cleanup`) are both real, versioned dependencies in
   `pyproject.toml`/`package.json`, exactly the category `APP-DESIGN.md` §1.1 carves the `appkit`
   exception for. **Neither is a sibling app package** — no other app package is ever imported,
   in any form.
2. **This app's own importable module is `cleanup_app`, never `django_cleanup`.** Upstream
   already owns that name in the same `site-packages` this app installs into — reusing it is not
   a style choice, it's a hard collision. PyPI distribution is `hjtdev-django-cleanup`; npm is
   `@hjtdev/django-cleanup`; the repo stays `HjtDev/django-cleanup`. Only the local directory and
   the importable module are `cleanup_app`.
3. **This app deletes files off disk.** Every code path that removes or moves a file goes through
   `services.CleanupService` and honours all four rails, unconditionally: dry-run, grace period,
   exclude patterns, and record-before-delete (the `CleanupRunFile` row for a file is written
   *before* the delete is attempted, never after). A delete path shipped without all four is not
   done, no matter what else works. See `docs/CLAUDE-CODE-GUIDE-APP-MEDIA-CLEANUP.md` §0 item 2
   and §3's boundary questions — run them at the end of every phase that touches a delete path.
4. **No user-facing surface, ever.** Every endpoint, every admin surface, every mutation is gated
   by `appkit.permissions.IsAppAdmin` (`is_authenticated and is_staff`) with zero exceptions.
   `urls.py` ships intentionally empty — only `urls_admin.py` is meaningful. There is no "regular
   user" tier to accidentally fall back to.
5. **Wide dependency ranges, never exact pins**, on `django`, `djangorestframework`,
   `drf-spectacular`, `appkit`, and `django-cleanup` — anything a host also depends on directly.
6. **Both halves release under one tag** — `pyproject.toml`, `package.json`, `CHANGELOG.md`
   agree; CI fails the build otherwise.
7. **Namespace everything landing in a shared namespace** — settings dict `CLEANUP`, throttle
   prefix `cleanup_`, cache namespace `cleanup`, frontend basePath key `cleanup`, Celery task
   names `cleanup_app.tasks.*`. `APP-DESIGN.md` §1.2.

## Scope boundary

| In | Out |
|---|---|
| Orphan scanning (storage vs. every `FileField` reference across all installed models) | Re-implementing what upstream `django-cleanup` already does (per-save/per-delete deletion) — that's a dependency, not something to rebuild |
| `CleanupRun`/`CleanupRunFile` history, an opt-in auto-deletion log fed by upstream's own `cleanup_post_delete` signal | Thumbnail generation, image processing, storage backend implementations |
| A Jazzmin admin review page + admin-only DRF endpoints + frontend hooks | Any user-facing (non-admin) surface |
| An optional Celery task for scheduled cleanup, a management command for cron-based hosts | Requiring Celery — the app must be fully functional with no worker running |
| `CLEANUP` settings dict, all optional, all defaulted | Any `.env` key — this app needs none |

## Dependency ranges & pinned versions

| Decision | Value |
|---|---|
| Python | `requires-python = ">=3.13"` (range); `.python-version` pins `3.14` locally |
| Django / DRF | `>=5.2,<7.0` / `>=3.15,<4.0` |
| `appkit` | `hjtdev-appkit>=2.0,<3.0` |
| `django-cleanup` | `django-cleanup>=9.0,<10.0` |
| Celery (optional `celery` extra) | `celery[redis]>=5.4,<6.0`, `django-celery-beat>=2.7,<3.0` |
| React / `@tanstack/react-query` (peer deps) | `>=18` / `>=5` |
| `@hjtdev/appkit` (peer dep) | matching appkit's own published major |
| Vitest | 4.x |
| Coverage gate | **85%** — the standard app-package bar, not `appkit`'s 95% blast-radius exception |

## Commands

Tests run on Postgres, not SQLite (`docs/APP-DESIGN.md` §7.5).

```bash
cd backend && uv sync                              # core only
uv sync --extra celery                              # prove the optional extra resolves
uv run pytest                                        # gate: authoritative, >=85% coverage
uv run --exact pytest -m "not requires_extra" --no-cov   # bare-install check, no celery extra
uv run ruff check --fix . ../tests && uv run ruff format . ../tests
uv run mypy src
uv build

cd frontend && npm ci
npm run test                      # Vitest + MSW — authoritative gate for the TS half
npx tsc --noEmit && npm run lint

# Verify against a real host before tagging — the one check that deletes a real file for real
cd playground/backend && uv sync
docker compose -f playground/docker-compose.yml up
```

CI: `.github/workflows/ci.yml` here is a ~10-line caller only, per `docs/APP-DESIGN.md` §10.2,
using the org-level reusable workflow at `HjtDev/.github`'s `app-package-ci.yml` — not recreated
locally, plus this repo's own `publish-pypi` job (§10.2 explains why that one can't live in the
shared workflow).

## Semver triggers — MAJOR bumps even when the diff is small

- Removing/renaming a signal (`cleanup_run_started`/`cleanup_run_finished`), a `services.py`
  method signature, an exported hook, or a `CleanupRun`/`CleanupRunFile` field a host might query.
- Changing what counts as an orphan (a stricter or looser reference-set rule) without a
  corresponding `CLEANUP` setting to opt back into the old behavior.
- Renaming a `CLEANUP` settings key.
- Renaming the published distribution name (`hjtdev-django-cleanup` / `@hjtdev/django-cleanup`).
- Weakening a default safety rail (shortening the default grace period, changing the default
  delete mode) — treat as breaking even if it's "just a default," since a host that never
  overrode it inherits the new behavior silently.

Every one needs a **Host action:** line in `CHANGELOG.md`.

## Working agreement (delete after v1.0.0 ships)

- One phase at a time, per `docs/CLAUDE-CODE-GUIDE-APP-MEDIA-CLEANUP.md`. Don't create files
  outside the current phase's scope.
- Re-read the relevant `docs/APP-DESIGN.md` section, and this app's own guide section, before
  writing files it specifies.
- After each phase, run its verification command and paste the real output. Never report success
  you haven't observed.
- If the spec is ambiguous or looks wrong, ask. Don't guess and proceed.
- This package must work in ANY host project. **Whenever you're about to rely on something
  existing outside this package** (other than `appkit` and `django_cleanup`, the two declared
  exceptions), **stop** — that's the constraint this whole design exists for.
- Whenever you're about to write code that deletes or moves a file, stop and confirm it goes
  through `CleanupService` and all four rails. This is the one constraint that matters more than
  the boundary rule above.

## Definition of done

- `docs/CONTRACT.md` and the code agree; `README.md` and the code agree.
- `backend/README.md` and `frontend/README.md` are current copies of `README.md`
  (`readme-contract` CI job green).
- Both halves at the same version, in all three places; CI's lockstep job green.
- `uv run pytest` and `npm run test` green, over 85% coverage.
- `ruff`, `mypy`, `tsc --noEmit`, `eslint` all clean.
- Zero imports of another app package; `appkit` and `django_cleanup` are the only exceptions.
- Every emitted signal has a test asserting its exact documented payload.
- Every endpoint has a non-admin-gets-403 test that actually fails when `IsAppAdmin` is swapped
  for something weaker.
- Every delete-capable path verified to honour dry-run, grace period, exclude patterns, and
  record-before-delete.
- Playground verified: a real orphaned file on real disk was found and actually removed, with
  `CleanupRun`/`CleanupRunFile` counts matching reality.
- Security checklists (`APP-DESIGN.md` §9 and §12) walked with evidence, not assumed.
- Installed into a fresh `base-scaffold` clone using only the README.
- Tagged `v1.0.0`; PyPI and npm entries both show a real, non-empty description — checked
  directly against the registry, not assumed from green CI.

## Git protocol

- Never stage or commit unless explicitly asked. Every diff gets reviewed before it lands.
- Never `git push`, `git reset --hard`, `git checkout <branch>`, force-push, or amend an existing
  commit. Ever. Ask instead.
- When a phase or task is done, don't commit — summarise what changed and the verification output
  that passed, propose a commit message in the format below (fenced, copy-pasteable), then stop
  and wait for review.
- If something needs reverting, say so and let the reviewer do it.

### Commit message format

```
semantic(<scope>): <short_commit_message>

- Add <what was added>
- Remove <what was removed>
- Update <what was changed>
```

Rules for it:
- `semantic` is one of: `feat`, `fix`, `chore`, `docs`, `refactor`, `test`, `build`, `ci`, `perf`,
  `style`. Use `!` after the scope for a breaking change: `feat(services)!:`.
- `<scope>`: lowercase, one word — `backend`, `frontend`, `api`, `hooks`, `ci`, `deps`,
  `playground`, `docs`, `admin`. Narrowest scope that covers the change.
- `<short_commit_message>`: imperative mood, lowercase, no trailing period, under 60 chars.
- Blank line after the title, then literal `- `-prefixed bullets, each starting with an
  imperative verb (`Add`, `Remove`, `Update`, `Move`, `Rename`, `Fix`, `Pin`, `Enable`,
  `Disable`), capitalised, no trailing period. Group trivia, don't list every file.
- Host action required (new settings key, a config block to copy)? Final line:
  `Host action: <what to do>`.
- No co-author trailers, no "generated with" footers, no emoji.
- A commit changing a signal payload, a service signature, a settings key, or a default safety
  rail uses `!` and always gets a `Host action:` line.

Example:

```
chore(backend): add uv project config and tooling baseline

- Add backend/pyproject.toml with dependencies, dev/test dependency groups and uv default-groups
- Add ruff, mypy, pytest and coverage configuration
- Add commented banned-api table enforcing the no-inter-app-import rule
- Add MANIFEST.in, .python-version and .gitignore
```
