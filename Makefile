# Local dev/test targets. Every test target brings up docker-compose.test.yml's ephemeral
# Postgres first and tears it down after — a fresh clone needs nothing pre-installed beyond
# Docker and uv. Mirrors ../appkit's Makefile. See CLAUDE.md's Commands block for the
# equivalent raw commands.

.PHONY: test test-bare lint typecheck check sync-readmes

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

check: test lint typecheck test-bare

# The root README.md is the single hand-maintained source; backend/README.md (and,
# once Phase 6 creates frontend/, frontend/README.md) are committed, generated copies — PyPI
# and npm each read a package's `readme` file relative to ITS OWN project root, never the repo
# root, so a monorepo publishing from both halves needs a real file in each directory or the
# registry page shows no description at all. CI's `readme-contract` job fails the build if any
# copy drifts from the original — run this and commit the copies whenever README.md changes.
sync-readmes:
	cp README.md backend/README.md
