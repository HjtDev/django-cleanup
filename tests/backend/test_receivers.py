"""Tests for ``cleanup_app.receivers`` — the ``TRACK_AUTO_DELETIONS`` log of upstream
``django_cleanup``'s own per-save/per-delete deletions (``docs/CONTRACT.md`` §9.4).
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

import pytest
from django.utils import timezone
from django_cleanup.signals import cleanup_post_delete

from cleanup_app.models import CleanupRun, CleanupRunFile
from cleanup_app.receivers import _get_or_create_daily_auto_run, track_auto_deletion
from tests.backend.testapp.models import Document, Folder

pytestmark = pytest.mark.django_db


def test_deleting_a_real_row_fires_the_receiver_and_creates_an_auto_run(
    django_capture_on_commit_callbacks: Any,
) -> None:
    """Deletes a real Document row (whose file field upstream django_cleanup auto-hooks) rather
    than hand-sending the signal — proves TRACK_AUTO_DELETIONS is wired end to end through
    apps.py, not just that the receiver function works in isolation. Upstream's own
    FileSystemStorage.delete() silently no-ops on a missing file (verified: it catches
    FileNotFoundError), so success=True is reported even without a real file on disk — this test
    is about the signal wiring, not storage content.

    Upstream schedules its actual delete via django.db.transaction.on_commit
    (django_cleanup/handlers.py) — under plain @pytest.mark.django_db's atomic-rollback wrapping,
    on_commit callbacks never fire at all, so this needs django_capture_on_commit_callbacks
    (execute=True) to actually run them within the test's transaction.
    """
    folder = Folder.objects.create(name="reports")

    with django_capture_on_commit_callbacks(execute=True):
        document = Document.objects.create(folder=folder, attachment="documents/real.pdf")
        document.delete()

    run = CleanupRun.objects.get(trigger=CleanupRun.Trigger.AUTO)
    assert run.status == CleanupRun.Status.SUCCESS
    assert run.files_deleted == 1
    assert run.files_scanned == 1

    row = CleanupRunFile.objects.get(run=run)
    assert row.file_path == "documents/real.pdf"
    assert row.deleted is True
    assert row.file_size == 0  # unrecoverable — the file is already gone by receiver time


def test_hand_sent_failure_event_flips_run_to_partial() -> None:
    cleanup_post_delete.send(
        sender=Document,
        file=None,
        file_name="documents/first.pdf",
        model_name="testapp.document",
        field_name="attachment",
        instance=None,
        default_file_name="",
        deleted=True,
        updated=False,
        success=True,
        error=None,
    )
    cleanup_post_delete.send(
        sender=Document,
        file=None,
        file_name="documents/second.pdf",
        model_name="testapp.document",
        field_name="attachment",
        instance=None,
        default_file_name="",
        deleted=True,
        updated=False,
        success=False,
        error=RuntimeError("disk gone"),
    )

    run = CleanupRun.objects.get(trigger=CleanupRun.Trigger.AUTO)
    assert run.status == CleanupRun.Status.PARTIAL
    assert run.files_deleted == 1
    assert run.files_failed == 1

    failed_row = CleanupRunFile.objects.get(run=run, file_path="documents/second.pdf")
    assert failed_row.deleted is False
    assert failed_row.error == "disk gone"  # str(error), never the raw Exception object


def test_error_is_stored_as_string_not_exception_object() -> None:
    error = ValueError("boom")

    track_auto_deletion(
        sender=Document,
        file_name="x.bin",
        model_name="testapp.document",
        field_name="attachment",
        success=False,
        error=error,
    )

    row = CleanupRunFile.objects.get(file_path="x.bin")
    assert row.error == "boom"
    assert isinstance(row.error, str)


def test_events_on_the_same_day_group_into_one_run() -> None:
    track_auto_deletion(
        sender=Document,
        file_name="a.bin",
        model_name="testapp.document",
        field_name="attachment",
        success=True,
        error=None,
    )
    track_auto_deletion(
        sender=Document,
        file_name="b.bin",
        model_name="testapp.document",
        field_name="attachment",
        success=True,
        error=None,
    )

    assert CleanupRun.objects.filter(trigger=CleanupRun.Trigger.AUTO).count() == 1
    run = CleanupRun.objects.get(trigger=CleanupRun.Trigger.AUTO)
    assert run.files_scanned == 2
    assert run.files_deleted == 2


def test_events_on_different_utc_days_create_separate_runs() -> None:
    run_yesterday = _get_or_create_daily_auto_run()
    CleanupRun.objects.filter(pk=run_yesterday.pk).update(
        started_at=timezone.now() - timedelta(days=1)
    )

    track_auto_deletion(
        sender=Document,
        file_name="today.bin",
        model_name="testapp.document",
        field_name="attachment",
        success=True,
        error=None,
    )

    assert CleanupRun.objects.filter(trigger=CleanupRun.Trigger.AUTO).count() == 2


def test_auto_run_status_never_pending_or_running() -> None:
    """§9.4/§9.5: an AUTO run must never carry PENDING/RUNNING — that status is what would let a
    day-spanning row trip services._scheduled_run_in_progress()'s SCHEDULED-only guard."""
    track_auto_deletion(
        sender=Document,
        file_name="a.bin",
        model_name="testapp.document",
        field_name="attachment",
        success=True,
        error=None,
    )

    run = CleanupRun.objects.get(trigger=CleanupRun.Trigger.AUTO)
    assert run.status not in (CleanupRun.Status.PENDING, CleanupRun.Status.RUNNING)
