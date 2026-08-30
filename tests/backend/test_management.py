"""Tests for the ``cleanup_orphans`` management command — the no-Celery cron path
(``docs/CONTRACT.md`` §8), sharing ``services._scheduled_run_in_progress`` with ``tasks.py`` so
the two concurrency guards cannot drift apart.
"""

from __future__ import annotations

from collections.abc import Callable
from io import StringIO
from unittest.mock import patch

import pytest
from django.core.files.storage import Storage
from django.core.management import CommandError, call_command

from cleanup_app.factories import CleanupRunFactory
from cleanup_app.models import CleanupRun
from cleanup_app.services import OrphanScanner

pytestmark = pytest.mark.django_db


def test_default_run_is_scheduled_and_reports_summary(media_storage: Storage) -> None:
    out = StringIO()

    call_command("cleanup_orphans", stdout=out)

    run = CleanupRun.objects.get()
    assert run.trigger == CleanupRun.Trigger.SCHEDULED
    assert f"run #{run.pk}" in out.getvalue()
    assert f"status={run.status}" in out.getvalue()


def test_dry_run_flag_performs_no_deletion(
    media_storage: Storage, write_file: Callable[..., str]
) -> None:
    write_file(media_storage, "uploads/orphan.bin", age_seconds=10_000)

    call_command("cleanup_orphans", "--dry-run", stdout=StringIO())

    run = CleanupRun.objects.get()
    assert run.dry_run is True
    assert media_storage.exists("uploads/orphan.bin")


def test_explicit_trigger_is_recorded_on_the_run(media_storage: Storage) -> None:
    call_command("cleanup_orphans", "--trigger", "manual", stdout=StringIO())

    run = CleanupRun.objects.get()
    assert run.trigger == CleanupRun.Trigger.MANUAL


def test_skips_when_a_scheduled_run_is_already_in_progress() -> None:
    CleanupRunFactory(trigger=CleanupRun.Trigger.SCHEDULED, status=CleanupRun.Status.RUNNING)
    out = StringIO()

    call_command("cleanup_orphans", stdout=out)

    assert "skipped" in out.getvalue()
    assert CleanupRun.objects.filter(trigger=CleanupRun.Trigger.SCHEDULED).count() == 1


def test_manual_trigger_is_not_subject_to_the_scheduled_guard(media_storage: Storage) -> None:
    CleanupRunFactory(trigger=CleanupRun.Trigger.SCHEDULED, status=CleanupRun.Status.RUNNING)

    call_command("cleanup_orphans", "--trigger", "manual", stdout=StringIO())

    assert CleanupRun.objects.filter(trigger=CleanupRun.Trigger.MANUAL).exists()


def test_failed_run_raises_command_error(media_storage: Storage) -> None:
    with (
        patch.object(OrphanScanner, "scan", side_effect=RuntimeError("scan exploded")),
        pytest.raises(CommandError),
    ):
        call_command("cleanup_orphans", stdout=StringIO())

    run = CleanupRun.objects.get()
    assert run.status == CleanupRun.Status.FAILED
