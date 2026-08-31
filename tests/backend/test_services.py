"""Tests for ``cleanup_app.services`` — ``docs/CONTRACT.md`` §3, and the four safety rails
(``CLAUDE.md`` rule 3): dry-run, grace period, exclude patterns, record-before-delete.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import timedelta
from typing import Any
from unittest.mock import patch

import pytest
from django.core.files.storage import Storage
from django.utils import timezone

from cleanup_app.factories import CleanupRunFactory, CleanupRunFileFactory
from cleanup_app.models import CleanupRun, CleanupRunFile
from cleanup_app.services import (
    CleanupService,
    OrphanFileInfo,
    OrphanScanner,
    _get_storage,
)
from tests.backend.testapp.models import Avatar, Document, Folder, IgnoredDoc, SoftDeleted

pytestmark = pytest.mark.django_db


# --------------------------------------------------------------------------------- _get_storage


def test_get_storage_resolves_default_alias_to_default_storage() -> None:
    from django.core.files.storage import default_storage

    # No CLEANUP override at all here — STORAGE_ALIAS's documented default ("default") must
    # resolve to Django's own default_storage, not require a host to opt in explicitly.
    assert _get_storage() is default_storage


# --------------------------------------------------------------------------- build_reference_set


def test_build_reference_set_includes_direct_reference(media_storage: Storage) -> None:
    IgnoredDoc.objects.create(file="uploads/direct.bin")

    assert "uploads/direct.bin" in OrphanScanner.build_reference_set()


def test_build_reference_set_includes_reverse_relation_only_reachable_file(
    media_storage: Storage,
) -> None:
    """A file referenced by Document, itself only reachable from Folder via a reverse FK, must
    still show up — build_reference_set() walks apps.get_models() directly rather than following
    relations outward from a starting model."""
    folder = Folder.objects.create(name="reports")
    Document.objects.create(folder=folder, attachment="documents/via-reverse.pdf")

    assert "documents/via-reverse.pdf" in OrphanScanner.build_reference_set()


def test_build_reference_set_covers_imagefield(media_storage: Storage) -> None:
    Avatar.objects.create(image="avatars/pic.png")

    assert "avatars/pic.png" in OrphanScanner.build_reference_set()


def test_build_reference_set_sees_soft_deleted_rows_via_base_manager(
    media_storage: Storage,
) -> None:
    """A soft-deleted row is hidden from SoftDeleted.objects (its filtering default manager) but
    the DB row — and its file reference — still exists. build_reference_set() must use
    _base_manager, not .objects, or this file becomes a false-positive orphan."""
    obj = SoftDeleted.objects.create(file="soft-deleted/still-there.bin", is_deleted=True)

    assert not SoftDeleted.objects.filter(pk=obj.pk).exists()  # hidden from the default manager
    assert "soft-deleted/still-there.bin" in OrphanScanner.build_reference_set()


def test_build_reference_set_skips_empty_values(media_storage: Storage) -> None:
    IgnoredDoc.objects.create(file="")

    assert "" not in OrphanScanner.build_reference_set()


# --------------------------------------------------------------------------------- scan()


def test_scan_finds_unreferenced_file(
    media_storage: Storage, write_file: Callable[..., str]
) -> None:
    write_file(media_storage, "uploads/orphan.bin", age_seconds=10_000)

    result = OrphanScanner.scan()

    assert [f.path for f in result.files] == ["uploads/orphan.bin"]
    assert result.total_size == len(b"orphan-file-contents")
    assert result.files_scanned == 1
    assert result.truncated is False


def test_scan_excludes_referenced_file(
    media_storage: Storage, write_file: Callable[..., str]
) -> None:
    IgnoredDoc.objects.create(file="uploads/keep.bin")
    write_file(media_storage, "uploads/keep.bin", age_seconds=10_000)

    result = OrphanScanner.scan()

    assert result.files == []


def test_scan_protects_file_within_grace_period(
    media_storage: Storage, settings: Any, write_file: Callable[..., str]
) -> None:
    settings.CLEANUP = {**settings.CLEANUP, "GRACE_PERIOD_SECONDS": 3600}
    write_file(media_storage, "uploads/fresh.bin", age_seconds=10)  # well within the window

    result = OrphanScanner.scan()

    assert result.files == []


def test_scan_returns_file_aged_past_grace_period(
    media_storage: Storage, settings: Any, write_file: Callable[..., str]
) -> None:
    settings.CLEANUP = {**settings.CLEANUP, "GRACE_PERIOD_SECONDS": 60}
    write_file(media_storage, "uploads/old-enough.bin", age_seconds=120)

    result = OrphanScanner.scan()

    assert [f.path for f in result.files] == ["uploads/old-enough.bin"]


def test_scan_protects_excluded_pattern(
    media_storage: Storage, settings: Any, write_file: Callable[..., str]
) -> None:
    settings.CLEANUP = {**settings.CLEANUP, "EXCLUDE_PATTERNS": ["*.tmp"]}
    write_file(media_storage, "uploads/cache.tmp", age_seconds=10_000)

    result = OrphanScanner.scan()

    assert result.files == []


def test_scan_truncates_at_max_files_per_run(
    media_storage: Storage, settings: Any, write_file: Callable[..., str]
) -> None:
    settings.CLEANUP = {**settings.CLEANUP, "MAX_FILES_PER_RUN": 2}
    for i in range(4):
        write_file(media_storage, f"uploads/orphan-{i}.bin", age_seconds=10_000)

    result = OrphanScanner.scan()

    assert len(result.files) == 2
    assert result.truncated is True
    assert result.files_scanned == 4


def test_scan_skips_file_that_fails_to_stat(
    media_storage: Storage, write_file: Callable[..., str]
) -> None:
    write_file(media_storage, "uploads/good.bin", age_seconds=10_000)
    write_file(media_storage, "uploads/bad.bin", age_seconds=10_000)

    original_get_modified_time = type(media_storage).get_modified_time

    def _flaky(self: Storage, name: str) -> Any:
        if name == "uploads/bad.bin":
            raise OSError("simulated stat failure")
        return original_get_modified_time(self, name)

    with patch.object(type(media_storage), "get_modified_time", _flaky):
        result = OrphanScanner.scan()

    assert [f.path for f in result.files] == ["uploads/good.bin"]
    assert result.files_scanned == 2


def test_scan_caches_snapshot_and_does_not_rewalk_storage(
    media_storage: Storage, write_file: Callable[..., str]
) -> None:
    write_file(media_storage, "uploads/orphan.bin", age_seconds=10_000)

    OrphanScanner.scan()

    with patch.object(type(media_storage), "listdir") as spy:
        OrphanScanner.scan()

    spy.assert_not_called()


# --------------------------------------------------------------------------- CleanupService.run()


def test_run_deletes_orphan_and_updates_counts(
    media_storage: Storage, write_file: Callable[..., str]
) -> None:
    write_file(media_storage, "uploads/orphan.bin", age_seconds=10_000)

    run = CleanupService.run(trigger=CleanupRun.Trigger.MANUAL)

    assert run.status == CleanupRun.Status.SUCCESS
    assert run.files_scanned == 1
    assert run.files_deleted == 1
    assert run.files_failed == 0
    assert run.bytes_freed == len(b"orphan-file-contents")
    assert run.finished_at is not None
    assert not media_storage.exists("uploads/orphan.bin")

    row = CleanupRunFile.objects.get(run=run, file_path="uploads/orphan.bin")
    assert row.deleted is True
    assert row.error == ""


def test_run_dry_run_deletes_nothing_but_writes_rows(
    media_storage: Storage, write_file: Callable[..., str]
) -> None:
    write_file(media_storage, "uploads/orphan.bin", age_seconds=10_000)

    run = CleanupService.run(trigger=CleanupRun.Trigger.MANUAL, dry_run=True)

    assert run.status == CleanupRun.Status.SUCCESS
    assert run.files_deleted == 0
    assert run.bytes_freed == 0
    assert media_storage.exists("uploads/orphan.bin")

    row = CleanupRunFile.objects.get(run=run, file_path="uploads/orphan.bin")
    assert row.deleted is False
    assert row.error == ""


def test_run_record_before_delete_ordering(
    media_storage: Storage, write_file: Callable[..., str]
) -> None:
    """The row for a candidate must already exist in the DB at the moment delete() is called —
    proved by having delete()'s own side effect query for it."""
    write_file(media_storage, "uploads/orphan.bin", age_seconds=10_000)
    seen_row_exists_at_delete_time = []

    original_delete = type(media_storage).delete

    def _spy_delete(self: Storage, name: str) -> Any:
        seen_row_exists_at_delete_time.append(
            CleanupRunFile.objects.filter(file_path=name, deleted=False).exists()
        )
        return original_delete(self, name)

    with patch.object(type(media_storage), "delete", _spy_delete):
        CleanupService.run(trigger=CleanupRun.Trigger.MANUAL)

    assert seen_row_exists_at_delete_time == [True]


def test_run_one_failure_does_not_abort_remaining_files_and_reports_partial(
    media_storage: Storage, write_file: Callable[..., str]
) -> None:
    write_file(media_storage, "uploads/good.bin", age_seconds=10_000)
    write_file(media_storage, "uploads/bad.bin", age_seconds=10_000)

    original_delete = type(media_storage).delete

    def _flaky(self: Storage, name: str) -> Any:
        if name == "uploads/bad.bin":
            raise OSError("simulated delete failure")
        return original_delete(self, name)

    with patch.object(type(media_storage), "delete", _flaky):
        run = CleanupService.run(trigger=CleanupRun.Trigger.MANUAL)

    assert run.status == CleanupRun.Status.PARTIAL
    assert run.files_deleted == 1
    assert run.files_failed == 1
    assert not media_storage.exists("uploads/good.bin")
    assert media_storage.exists("uploads/bad.bin")

    bad_row = CleanupRunFile.objects.get(run=run, file_path="uploads/bad.bin")
    assert bad_row.deleted is False
    assert "simulated delete failure" in bad_row.error


def test_run_all_failures_reports_failed(
    media_storage: Storage, write_file: Callable[..., str]
) -> None:
    write_file(media_storage, "uploads/bad.bin", age_seconds=10_000)

    with patch.object(type(media_storage), "delete", side_effect=OSError("boom")):
        run = CleanupService.run(trigger=CleanupRun.Trigger.MANUAL)

    assert run.status == CleanupRun.Status.FAILED
    assert run.files_deleted == 0
    assert run.files_failed == 1


def test_run_no_candidates_is_success(media_storage: Storage) -> None:
    run = CleanupService.run(trigger=CleanupRun.Trigger.MANUAL)

    assert run.status == CleanupRun.Status.SUCCESS
    assert run.files_scanned == 0


def test_run_unhandled_exception_is_recorded_as_failed(media_storage: Storage) -> None:
    with patch.object(OrphanScanner, "scan", side_effect=RuntimeError("scan exploded")):
        run = CleanupService.run(trigger=CleanupRun.Trigger.MANUAL)

    assert run.status == CleanupRun.Status.FAILED
    assert "scan exploded" in run.error
    assert run.finished_at is not None


def test_run_with_unknown_file_path_is_never_touched_and_recorded_as_failed(
    media_storage: Storage, write_file: Callable[..., str]
) -> None:
    write_file(media_storage, "uploads/orphan.bin", age_seconds=10_000)
    OrphanScanner.scan()  # populate the snapshot

    run = CleanupService.run(
        trigger=CleanupRun.Trigger.API, file_paths=["uploads/not-in-snapshot.bin"]
    )

    assert run.status == CleanupRun.Status.FAILED
    assert run.files_deleted == 0
    row = CleanupRunFile.objects.get(run=run, file_path="uploads/not-in-snapshot.bin")
    assert row.deleted is False
    assert row.error == "not present in the current orphan snapshot"
    # the real orphan, untouched by this call, is still on disk
    assert media_storage.exists("uploads/orphan.bin")


def test_run_file_paths_deletes_only_the_requested_subset(
    media_storage: Storage, write_file: Callable[..., str]
) -> None:
    write_file(media_storage, "uploads/one.bin", age_seconds=10_000)
    write_file(media_storage, "uploads/two.bin", age_seconds=10_000)
    OrphanScanner.scan()

    run = CleanupService.run(trigger=CleanupRun.Trigger.API, file_paths=["uploads/one.bin"])

    assert run.status == CleanupRun.Status.SUCCESS
    assert not media_storage.exists("uploads/one.bin")
    assert media_storage.exists("uploads/two.bin")


def test_run_quarantines_instead_of_deleting_when_configured(
    media_storage: Storage, settings: Any, write_file: Callable[..., str]
) -> None:
    settings.CLEANUP = {**settings.CLEANUP, "QUARANTINE_DIR": "quarantine"}
    write_file(media_storage, "uploads/orphan.bin", age_seconds=10_000)

    run = CleanupService.run(trigger=CleanupRun.Trigger.MANUAL)

    assert run.status == CleanupRun.Status.SUCCESS
    assert not media_storage.exists("uploads/orphan.bin")
    assert media_storage.exists("quarantine/uploads/orphan.bin")

    row = CleanupRunFile.objects.get(run=run, file_path="uploads/orphan.bin")
    assert row.deleted is True
    assert row.quarantined is True


def test_run_invalidates_cache_when_not_dry_run(
    media_storage: Storage, write_file: Callable[..., str]
) -> None:
    write_file(media_storage, "uploads/orphan.bin", age_seconds=10_000)
    first = OrphanScanner.scan()
    assert len(first.files) == 1

    CleanupService.run(trigger=CleanupRun.Trigger.MANUAL)

    second = OrphanScanner.scan()
    assert second.files == []  # re-scanned, not served from the stale cached snapshot


def test_run_does_not_invalidate_cache_on_dry_run(
    media_storage: Storage, write_file: Callable[..., str]
) -> None:
    write_file(media_storage, "uploads/orphan.bin", age_seconds=10_000)
    OrphanScanner.scan()

    with patch("cleanup_app.services.invalidate_namespace") as spy:
        CleanupService.run(trigger=CleanupRun.Trigger.MANUAL, dry_run=True)

    spy.assert_not_called()


# --------------------------------------------------------------------------------- execute_run()


def test_execute_run_drives_an_already_created_row(
    media_storage: Storage, write_file: Callable[..., str]
) -> None:
    """Phase 4's ``POST /runs/`` (when ``USE_CELERY`` enqueues ``tasks.run_cleanup_run``) already
    holds a ``CleanupRun`` row before this runs — ``execute_run()`` must drive that row to
    completion without ``CleanupService.run()`` creating a second, redundant one."""
    write_file(media_storage, "uploads/orphan.bin", age_seconds=10_000)
    run = CleanupRun.objects.create(trigger=CleanupRun.Trigger.API, dry_run=False)
    assert run.status == CleanupRun.Status.PENDING

    result = CleanupService.execute_run(run)

    assert result.pk == run.pk
    assert result.status == CleanupRun.Status.SUCCESS
    assert not media_storage.exists("uploads/orphan.bin")
    assert CleanupRun.objects.count() == 1


def test_run_creates_a_pending_row_before_delegating(media_storage: Storage) -> None:
    """``run()`` is now a thin wrapper — proves the row it creates starts at the model's default
    (``PENDING``) rather than jumping straight to ``RUNNING``, since ``execute_run()`` is what
    performs that transition."""
    created_statuses: list[str] = []
    original = CleanupService.execute_run

    def _spy(run: CleanupRun, *, file_paths: list[str] | None = None) -> CleanupRun:
        created_statuses.append(run.status)
        return original(run, file_paths=file_paths)

    with patch.object(CleanupService, "execute_run", side_effect=_spy):
        CleanupService.run(trigger=CleanupRun.Trigger.MANUAL)

    assert created_statuses == [CleanupRun.Status.PENDING]


# --------------------------------------------------------------------------------- purge_history()


def test_purge_history_default_retention(settings: Any) -> None:
    settings.CLEANUP = {**getattr(settings, "CLEANUP", {}), "HISTORY_RETENTION_DAYS": 30}
    old_run = CleanupRunFactory()
    CleanupRun.objects.filter(pk=old_run.pk).update(started_at=timezone.now() - timedelta(days=40))
    recent_run = CleanupRunFactory()

    deleted = CleanupService.purge_history()

    assert deleted == 1
    assert not CleanupRun.objects.filter(pk=old_run.pk).exists()
    assert CleanupRun.objects.filter(pk=recent_run.pk).exists()


def test_purge_history_explicit_older_than_days_overrides_setting(settings: Any) -> None:
    settings.CLEANUP = {**getattr(settings, "CLEANUP", {}), "HISTORY_RETENTION_DAYS": 9999}
    run = CleanupRunFactory()
    CleanupRun.objects.filter(pk=run.pk).update(started_at=timezone.now() - timedelta(days=5))

    deleted = CleanupService.purge_history(older_than_days=1)

    assert deleted == 1
    assert not CleanupRun.objects.filter(pk=run.pk).exists()


def test_purge_history_cascades_run_files(cleanup_run: CleanupRun) -> None:
    row = CleanupRunFileFactory(run=cleanup_run)
    CleanupRun.objects.filter(pk=cleanup_run.pk).update(
        started_at=timezone.now() - timedelta(days=200)
    )

    CleanupService.purge_history()

    assert not CleanupRunFile.objects.filter(pk=row.pk).exists()


def test_purge_history_never_touches_storage(
    media_storage: Storage, write_file: Callable[..., str]
) -> None:
    write_file(media_storage, "uploads/still-here.bin", age_seconds=10_000)
    run = CleanupRunFactory()
    CleanupRun.objects.filter(pk=run.pk).update(started_at=timezone.now() - timedelta(days=200))

    CleanupService.purge_history()

    assert media_storage.exists("uploads/still-here.bin")


# --------------------------------------------------------------------------------- IGNORED_MODELS


def test_ignored_models_scanner_still_protects_live_row_file(
    media_storage: Storage, settings: Any, write_file: Callable[..., str]
) -> None:
    """docs/CONTRACT.md §5/§9.1: IGNORED_MODELS is protective, not subtractive — an ignored
    model's live row's file must still be found in the reference set, never treated as orphaned
    by the scanner, even though upstream's auto-hook has stopped deleting it on save/delete."""
    settings.CLEANUP = {**settings.CLEANUP, "IGNORED_MODELS": ["testapp.IgnoredDoc"]}
    IgnoredDoc.objects.create(file="ignored/live.bin")
    write_file(media_storage, "ignored/live.bin", age_seconds=10_000)

    result = OrphanScanner.scan()

    assert result.files == []


def test_ignored_models_dangling_file_is_still_an_orphan(
    media_storage: Storage, settings: Any, write_file: Callable[..., str]
) -> None:
    """A file left dangling after an ignored model's row is deleted is a genuine orphan — the
    protection is "don't delete what a live row still needs", not "protect every file an ignored
    model ever touched forever"."""
    settings.CLEANUP = {**settings.CLEANUP, "IGNORED_MODELS": ["testapp.IgnoredDoc"]}
    write_file(media_storage, "ignored/dangling.bin", age_seconds=10_000)

    result = OrphanScanner.scan()

    assert [f.path for f in result.files] == ["ignored/dangling.bin"]


def test_orphan_file_info_shape(media_storage: Storage, write_file: Callable[..., str]) -> None:
    write_file(media_storage, "uploads/one.bin", age_seconds=10_000)

    result = OrphanScanner.scan()

    assert isinstance(result.files[0], OrphanFileInfo)
    assert result.files[0].size == len(b"orphan-file-contents")
    assert result.files[0].modified_at is not None
