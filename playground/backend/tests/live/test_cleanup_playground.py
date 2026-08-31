"""``pytest -m live`` — hits the real docker-compose stack over HTTP, not Django's test client.
Automates the manual curl checks in the Phase 7 plan's "Pass A" so they're re-runnable, not just
a one-time transcript. Requires the stack up (``docker compose -f playground/docker-compose.yml
up -d --wait``) and ``PLAYGROUND_BASE_URL``/``PLAYGROUND_ADMIN_USER``/``PLAYGROUND_ADMIN_PASSWORD``
set (see ``playground/.env.example``).
"""

from __future__ import annotations

import os

import httpx
import pytest

pytestmark = pytest.mark.live

BASE_URL = os.environ.get("PLAYGROUND_BASE_URL", "http://localhost:8000")
ADMIN_USER = os.environ.get("PLAYGROUND_ADMIN_USER", "admin")
ADMIN_PASSWORD = os.environ.get("PLAYGROUND_ADMIN_PASSWORD", "admin")


@pytest.fixture
def admin_client() -> httpx.Client:
    with httpx.Client(base_url=BASE_URL, auth=(ADMIN_USER, ADMIN_PASSWORD)) as client:
        yield client


def test_healthz() -> None:
    response = httpx.get(f"{BASE_URL}/healthz/")
    assert response.status_code == 200


def test_orphans_excludes_referenced_and_protected_files(admin_client: httpx.Client) -> None:
    response = admin_client.get("/api/v1/cleanup/admin/orphans/", params={"page_size": 100})
    assert response.status_code == 200
    paths = {row["file_path"] for row in response.json()["results"]}
    assert not any(p.endswith("readme.txt") or p.endswith("profile.png") for p in paths)
    assert not any(p.endswith("fresh-upload.txt") for p in paths)
    assert not any(p.endswith("important.keep") for p in paths)
    assert len(paths) >= 25  # enough to prove pagination is real


def test_delete_unknown_path_rejected(admin_client: httpx.Client) -> None:
    response = admin_client.post(
        "/api/v1/cleanup/admin/orphans/delete/",
        json={"file_paths": ["not/a/real/file.txt"]},
    )
    assert response.status_code == 400


def test_non_staff_gets_403() -> None:
    response = httpx.get(f"{BASE_URL}/api/v1/cleanup/admin/orphans/")
    assert response.status_code in (401, 403)
