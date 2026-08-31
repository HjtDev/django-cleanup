# Playground backend image. Built with the REPO ROOT as context (see
# playground/docker-compose.yml: `context: ..`) so the container preserves the same relative
# layout as the working tree — /app/backend (this app's own source) and
# /app/playground/backend — which is what lets pyproject.toml's `path = "../../backend"`
# [tool.uv.sources] entry resolve identically in and out of Docker, per docs/APP-DESIGN.md §11.2
# (path-linked, not tag-pinned). Mirrors ../appkit/playground/backend/Dockerfile.
FROM python:3.13-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl libpq5 \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:0.7 /uv /uvx /usr/local/bin/

WORKDIR /app

# This app's own source tree first (rarely changes during playground iteration — good layer
# cache). Only the parts a wheel build needs: src/, pyproject.toml, README.md (pyproject.toml's
# readme= key), MANIFEST.in.
COPY backend/pyproject.toml backend/README.md backend/MANIFEST.in backend/LICENSE /app/backend/
COPY backend/src/ /app/backend/src/
# The playground consumer, at the same relative depth it has on disk.
COPY playground/backend/ /app/playground/backend/

ENV UV_PROJECT_ENVIRONMENT=/opt/venv

WORKDIR /app/playground/backend

RUN uv sync --no-dev

ENV PATH="/opt/venv/bin:$PATH"

EXPOSE 8000

CMD ["sh", "-c", "python manage.py migrate --noinput && python manage.py seed_media && python manage.py collectstatic --noinput --clear && uvicorn config.asgi:application --host 0.0.0.0 --port 8000"]
