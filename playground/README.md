# django-cleanup playground

Phase 7, `docs/APP-DESIGN.md` §11.2 / `docs/CLAUDE-CODE-GUIDE-APP-MEDIA-CLEANUP.md`'s own Phase 7
brief: proves the two halves of `hjtdev-django-cleanup` agree with each other over a real HTTP
connection, against real files on real disk — the one check nothing else in this repo's test
suite can give, since every existing test mocks either storage or the HTTP layer. See
`FINDINGS.md` for what this actually found (two real bugs, both fixed here).

## What's here

| Path | What it is |
|---|---|
| `backend/` | A minimal Django host — `config/settings.py` wires `appkit` then `cleanup_app`, path-linked to `../../backend` via `[tool.uv.sources]`, never to a tagged release |
| `backend/demo/` | A throwaway app with `Document`/`Avatar` (`FileField`/`ImageField`) whose live rows make some seeded files "referenced"; `manage.py seed_media` writes the rest of the ground-truth media tree |
| `backend/tests/live/` | `pytest -m live` — hits the real running stack over HTTP, not Django's test client |
| `frontend/` | A minimal Next App Router app — one page (`CleanupClient.tsx`) exercising every exported hook, proxied same-origin to the backend via `next.config.ts`'s `rewrites()` |
| `docker-compose.yml` | Postgres, Redis, the backend, a Celery worker sharing the backend's own media volume, and the frontend |

`playground/frontend` is a member of the **repo-root** npm workspace (`../package.json`), not a
separate one — see `FINDINGS.md` §6 for why that differs from `docs/APP-DESIGN.md` §11.2's literal
template.

## Running it

```bash
# From the repo root:
npm install                              # hoists frontend/'s deps for BOTH workspace members
cd frontend && npm run build && cd ..    # path-linked SDK dist/ — build explicitly, it can go stale
cd playground/backend && uv sync && cd ../..

cp playground/.env.example playground/.env    # only knob: CLEANUP_USE_CELERY

docker compose -f playground/docker-compose.yml --env-file playground/.env up -d --wait
docker compose -f playground/docker-compose.yml exec backend python manage.py createsuperuser
```

Or via `make playground-up` from the repo root (does the same four steps).

Then:

- Frontend: <http://localhost:3000> — the orphan-review panel, proxied to the backend
- Django admin (Jazzmin): <http://localhost:3000/admin/> — same session, same data
- Backend direct: <http://localhost:8000>

To exercise the Celery path: set `CLEANUP_USE_CELERY=true` in `playground/.env`, then
`docker compose -f playground/docker-compose.yml up -d --wait` again (the `worker` service is
always up; the flag only changes what `POST /runs/` does).

To reset the demo data without tearing the stack down: `make playground-reset` (or
`docker compose -f playground/docker-compose.yml exec backend python manage.py seed_media --reset`).

## Verification

```bash
# System checks
docker compose -f playground/docker-compose.yml exec backend python manage.py check

# The live suite — real HTTP against the running stack
cd playground/backend
uv run pytest -m live
```

The manual checks this was actually verified against — real disk, real DB rows, a real headless
browser — are recorded with full output in `FINDINGS.md` §5.

## `.env.example`

Only one knob is exposed: `CLEANUP_USE_CELERY` (default `false`). Every other setting has a
working default baked into `docker-compose.yml`/`config/settings.py`.
