# Local dev/test targets. Every test target brings up docker-compose.test.yml's ephemeral
# Postgres first and tears it down after — a fresh clone needs nothing pre-installed beyond
# Docker and uv. Mirrors ../appkit's Makefile. See CLAUDE.md's Commands block for the
# equivalent raw commands.

.PHONY: test test-bare lint typecheck frontend-check check sync-readmes messages compilemessages \
	playground-up playground-down playground-logs playground-reset

# The authoritative gate — celery extra installed, >=85% coverage (this repo's CLAUDE.md
# Commands table).
test:
	docker compose -f docker-compose.test.yml up -d --wait
	trap 'docker compose -f docker-compose.test.yml down' EXIT; \
	(cd backend && \
	POSTGRES_HOST=localhost POSTGRES_PORT=55433 \
	POSTGRES_DB=test_cleanup POSTGRES_USER=postgres POSTGRES_PASSWORD=postgres \
	uv run --extra celery pytest)

# The bare-install leg — no celery extra, proves the core stands alone. `--exact` matters: it
# removes celery/django-celery-beat if a prior `make test` run left them in the venv. Restores
# the extra once the bare run finishes, either way — the venv is a shared dev environment, not
# something later targets (or a developer's next command) should find in a bare state.
test-bare:
	docker compose -f docker-compose.test.yml up -d --wait
	trap 'docker compose -f docker-compose.test.yml down' EXIT; \
	(cd backend && \
	POSTGRES_HOST=localhost POSTGRES_PORT=55433 \
	POSTGRES_DB=test_cleanup POSTGRES_USER=postgres POSTGRES_PASSWORD=postgres \
	uv run --exact pytest -m "not requires_extra" --no-cov; \
	status=$$?; \
	uv sync --extra celery >/dev/null; \
	exit $$status)

# `.` alone silently skips ../tests (a different root) — both are always checked together.
lint:
	cd backend && uv run ruff check . ../tests && uv run ruff format --check . ../tests

typecheck:
	cd backend && uv run mypy src

# The frontend half's own gate — Phase 6's four commands, run at the repo root since
# frontend/ is an npm workspace member (`npm install` here hoists react/@tanstack/react-query
# so the SDK and a host consuming it in the same workspace resolve one copy of each, per
# docs/APP-DESIGN.md §12's "same failure reproduces from a devDependency" note). Regenerating
# types before the diff check catches schema.yml drifting out from under a stale, committed
# schema.d.ts.
frontend-check:
	npm install
	cd frontend && npm run generate:types
	git diff --exit-code frontend/src/schema.d.ts
	cd frontend && npx tsc --noEmit
	cd frontend && npm run lint
	cd frontend && npm run format:check
	cd frontend && npm run test -- --run --coverage
	cd frontend && npm run build
	cd frontend && npm audit --audit-level=high

check: test lint typecheck test-bare frontend-check

# The root README.md is the single hand-maintained source; backend/README.md and
# frontend/README.md are committed, generated copies — PyPI and npm each read a package's
# `readme` file relative to ITS OWN project root, never the repo root, so a monorepo publishing
# from both halves needs a real file in each directory or the registry page shows no
# description at all. CI's `readme-contract` job fails the build if any copy drifts from the
# original — run this and commit the copies whenever README.md changes.
sync-readmes:
	cp README.md backend/README.md
	cp README.md frontend/README.md

# Regenerates locale/fa/LC_MESSAGES/django.po from source (admin.py, apps.py, models.py, and
# the Phase 5 templates) — new translatable strings land as empty msgstr entries for a
# translator to fill in; existing translations are preserved. Never run on its own before a
# release: compilemessages below must follow, or the .po drifts from the shipped .mo.
messages:
	cd backend/src/cleanup_app && uv run --project ../.. django-admin makemessages -l fa --no-obsolete

# Compiles locale/fa/LC_MESSAGES/django.po into the .mo the wheel-smoke-test CI job (and this
# app's own OrphanFileAdmin page) actually reads — a .po alone is never enough to ship.
compilemessages:
	cd backend/src/cleanup_app && msgfmt --check locale/fa/LC_MESSAGES/django.po -o locale/fa/LC_MESSAGES/django.mo

# Phase 7 — docs/APP-DESIGN.md §11.2. Run from the repo root (docker-compose.yml's build
# contexts assume it). `npm install`/`frontend` build first so the SDK's dist/ is fresh — it's
# path-linked via the npm workspace, not published, so a stale dist/ from a previous checkout
# would otherwise go unnoticed until the frontend container fails at runtime instead of at build.
playground-up:
	npm install
	cd frontend && npm run build
	cd playground/backend && uv sync
	docker compose -f playground/docker-compose.yml up -d --build --wait

playground-down:
	docker compose -f playground/docker-compose.yml down

playground-logs:
	docker compose -f playground/docker-compose.yml logs -f

# Re-seeds the demo media tree and DB rows without tearing the stack down — useful after a
# cleanup run has deleted the orphans and you want a clean slate for the next pass.
playground-reset:
	docker compose -f playground/docker-compose.yml exec backend python manage.py seed_media --reset
