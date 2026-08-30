"""Shared pytest fixtures for this app's own test suite.

The ``api_client``/``user``/``admin_user``/``auth_client``/``admin_client`` fixtures come from
``-p appkit.testing`` (wired in ``backend/pyproject.toml``'s addopts), prefixed ``appkit_`` —
this file only adds fixtures specific to this app's own models.
"""

from __future__ import annotations

import pytest

from cleanup_app.factories import CleanupRunFactory, CleanupRunFileFactory
from cleanup_app.models import CleanupRun, CleanupRunFile


@pytest.fixture
def cleanup_run(db: None) -> CleanupRun:
    return CleanupRunFactory()


@pytest.fixture
def cleanup_run_file(db: None, cleanup_run: CleanupRun) -> CleanupRunFile:
    return CleanupRunFileFactory(run=cleanup_run)
