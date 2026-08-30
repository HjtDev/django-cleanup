"""``factory_boy`` factories — this app's public *test-only* surface (``APP-DESIGN.md`` §7.3).

Phases 2/7 add factories for ``CleanupRun``/``CleanupRunFile`` here. A host's own test suite is
expected to import from here rather than hand-rolling equivalents.

This module is ruff-banned from ``src/cleanup_app`` (see ``backend/pyproject.toml``'s
``banned-api`` block) — nothing under ``src/`` may import it, since importing test factories from
production code is exactly the mistake that guard exists to catch. The test tree
(``../tests/backend``) is exempted from that ban.
"""

from __future__ import annotations

import factory.django
from factory.declarations import Sequence, SubFactory

from cleanup_app.models import CleanupRun, CleanupRunFile

# factory/__init__.py imports Sequence/SubFactory without an __all__, so mypy's strict
# --no-implicit-reexport treats them as not re-exported from the top-level `factory` package —
# importing straight from factory.declarations (where they're actually defined) avoids that.


class CleanupRunFactory(factory.django.DjangoModelFactory[CleanupRun]):
    class Meta:
        model = CleanupRun

    status = CleanupRun.Status.SUCCESS
    trigger = CleanupRun.Trigger.MANUAL
    # No SubFactory to a UserFactory here — ``initiated_by`` is nullable, and a host's own test
    # suite already has a real user fixture (``-p appkit.testing``'s ``appkit_user``/
    # ``appkit_admin_user``, built reflectively against the host's own user model) to pass in.
    initiated_by = None
    dry_run = False
    files_scanned = 0
    files_deleted = 0
    files_failed = 0
    bytes_freed = 0


class CleanupRunFileFactory(factory.django.DjangoModelFactory[CleanupRunFile]):
    class Meta:
        model = CleanupRunFile

    run = SubFactory(CleanupRunFactory)
    file_path = Sequence(lambda n: f"uploads/orphan-{n}.bin")
    file_size = 1024
    deleted = False
    quarantined = False
