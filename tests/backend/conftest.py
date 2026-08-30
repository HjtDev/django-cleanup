"""Shared pytest fixtures for this app's own test suite.

The ``api_client``/``user``/``admin_user``/``auth_client``/``admin_client`` fixtures come from
``-p appkit.testing`` (wired in ``backend/pyproject.toml``'s addopts), prefixed ``appkit_`` —
this file only adds fixtures specific to this app's own models.
"""

from __future__ import annotations

import os
import time
from collections.abc import Callable, Iterator
from typing import TYPE_CHECKING

import pytest
from django.core.cache import cache
from django.core.files.base import ContentFile
from django.core.files.storage import Storage, storages

from cleanup_app.factories import CleanupRunFactory, CleanupRunFileFactory
from cleanup_app.models import CleanupRun, CleanupRunFile

if TYPE_CHECKING:
    from pathlib import Path

    from pytest_django.fixtures import Settings


@pytest.fixture
def cleanup_run(db: None) -> CleanupRun:
    return CleanupRunFactory()


@pytest.fixture
def cleanup_run_file(db: None, cleanup_run: CleanupRun) -> CleanupRunFile:
    return CleanupRunFileFactory(run=cleanup_run)


@pytest.fixture(autouse=True)
def _cleanup_cache_isolation() -> Iterator[None]:
    """Clears Django's cache before and after every test.

    This suite exercises ``appkit.cache.cached_call()``'s ``"cleanup:orphans"`` snapshot
    directly, and test settings use ``LocMemCache`` — a process-level dict that a test's DB
    transaction rollback never touches, so a snapshot cached in one test would otherwise leak
    into the next. Autouse here is safe (unlike ``-p appkit.testing``'s own
    ``appkit_clear_cache``, deliberately *not* autouse — its own docstring's concern is a shared
    Redis instance under ``pytest -n auto``): ``LocMemCache`` is already isolated per
    pytest-xdist worker process, so there is no *shared* external cache an autouse clear could
    clobber for another worker's in-flight test.
    """
    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def media_storage(tmp_path: Path, settings: Settings) -> Storage:
    """Points ``CLEANUP["STORAGE_ALIAS"]`` at a fresh, ``tmp_path``-backed ``FileSystemStorage``
    for one test, via the ``settings`` fixture's ``STORAGES`` assignment.

    Deliberately not a bare ``override_settings(MEDIA_ROOT=...)`` — verified against
    ``django/test/signals.py``'s ``storages_changed`` receiver, only ``STORAGES``/
    ``STATIC_ROOT``/``STATIC_URL`` changes reset the already-instantiated ``default_storage``
    and the ``storages`` registry's cache; a lone ``MEDIA_ROOT`` override is silently ignored by
    any storage object that already resolved its location. Assigning ``settings.STORAGES``
    (a whole new dict, under a fresh alias) is what actually gets picked up.
    """
    location = tmp_path / "media"
    location.mkdir()
    settings.STORAGES = {
        **settings.STORAGES,
        "test-media": {
            "BACKEND": "django.core.files.storage.FileSystemStorage",
            "OPTIONS": {"location": str(location)},
        },
    }
    settings.CLEANUP = {**getattr(settings, "CLEANUP", {}), "STORAGE_ALIAS": "test-media"}
    return storages["test-media"]


@pytest.fixture
def write_file() -> Callable[..., str]:
    """Returns a helper that writes a file to a storage and optionally backdates its mtime —
    the deterministic way to test ``GRACE_PERIOD_SECONDS`` without sleeping in tests.
    """

    def _write(
        storage: Storage,
        path: str,
        content: bytes = b"orphan-file-contents",
        *,
        age_seconds: float = 0,
    ) -> str:
        name = storage.save(path, ContentFile(content))
        if age_seconds:
            # FileSystemStorage-only: .path() resolves the real filesystem location so os.utime
            # can backdate it directly, rather than mocking get_modified_time().
            full_path = storage.path(name)
            stamp = time.time() - age_seconds
            os.utime(full_path, (stamp, stamp))
        return name

    return _write
