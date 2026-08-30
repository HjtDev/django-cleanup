"""Migration-graph tests — ``docs/CLAUDE-CODE-GUIDE-APP-MEDIA-CLEANUP.md`` §2's own verification
requirement: ``0001_initial`` must depend on ``settings.AUTH_USER_MODEL`` via
``swappable_dependency``, and nothing should be missing from what's committed.
"""

from __future__ import annotations

from io import StringIO

import pytest
from django.conf import settings
from django.core.management import call_command
from django.db import migrations
from django.db.migrations.loader import MigrationLoader


def test_initial_migration_depends_on_swappable_user_model() -> None:
    loader = MigrationLoader(None, ignore_no_migrations=True)
    migration = loader.disk_migrations[("cleanup_app", "0001_initial")]

    assert migrations.swappable_dependency(settings.AUTH_USER_MODEL) in migration.dependencies


@pytest.mark.django_db
def test_no_missing_migrations() -> None:
    """The same guard docs/APP-DESIGN.md §10's CI runs: nothing in models.py has drifted from
    what's committed under migrations/. Needs a real connection (django_db) because
    makemigrations --check also consults django_migrations to check history consistency."""
    out = StringIO()
    # dry-run + check: raises CommandError (via SystemExit) if a migration is missing, and with
    # check=True call_command re-raises rather than exiting the test process.
    call_command("makemigrations", "cleanup_app", check=True, dry_run=True, stdout=out, verbosity=0)
