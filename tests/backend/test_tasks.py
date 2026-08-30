"""Tests for ``cleanup_app.tasks`` — the ``celery`` extra's ``run_scheduled_cleanup``, and the
guarantee that ``cleanup_app.tasks`` itself imports fine on a bare install (no celery).
"""

from __future__ import annotations

import pytest
from django.core.files.storage import Storage

from cleanup_app.factories import CleanupRunFactory
from cleanup_app.models import CleanupRun


def test_tasks_module_imports_without_celery() -> None:
    """No hard ``import celery`` at module scope — ``docs/CONTRACT.md``'s dependencies table
    lists celery as an optional extra, never a core dependency. Deliberately not marked
    ``requires_extra`` — it must pass on the bare-install leg (``make test-bare``) too, which is
    exactly what it's proving."""
    import cleanup_app.tasks as tasks_module

    assert hasattr(tasks_module, "run_scheduled_cleanup")


@pytest.mark.requires_extra
@pytest.mark.django_db
def test_run_scheduled_cleanup_creates_a_scheduled_run(media_storage: Storage) -> None:
    from cleanup_app.tasks import run_scheduled_cleanup

    run_id = run_scheduled_cleanup()

    assert run_id is not None
    run = CleanupRun.objects.get(pk=run_id)
    assert run.trigger == CleanupRun.Trigger.SCHEDULED
    assert run.status in (
        CleanupRun.Status.SUCCESS,
        CleanupRun.Status.PARTIAL,
        CleanupRun.Status.FAILED,
    )


@pytest.mark.requires_extra
@pytest.mark.django_db
def test_run_scheduled_cleanup_skips_when_a_scheduled_run_is_in_progress() -> None:
    from cleanup_app.tasks import run_scheduled_cleanup

    CleanupRunFactory(trigger=CleanupRun.Trigger.SCHEDULED, status=CleanupRun.Status.RUNNING)

    result = run_scheduled_cleanup()

    assert result is None
    assert CleanupRun.objects.filter(trigger=CleanupRun.Trigger.SCHEDULED).count() == 1


@pytest.mark.requires_extra
@pytest.mark.django_db
def test_run_scheduled_cleanup_proceeds_when_a_non_scheduled_run_is_in_flight(
    media_storage: Storage,
) -> None:
    """docs/CONTRACT.md §8/§9.5: the concurrency guard is scoped to trigger=SCHEDULED only — an
    AUTO or API run in progress must never block the schedule. AUTO can never carry RUNNING per
    §9.4, so this uses an in-flight API run as the "unusual but real" case the trigger-scoping
    is meant to tolerate."""
    from cleanup_app.tasks import run_scheduled_cleanup

    CleanupRunFactory(trigger=CleanupRun.Trigger.API, status=CleanupRun.Status.RUNNING)

    result = run_scheduled_cleanup()

    assert result is not None
