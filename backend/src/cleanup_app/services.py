"""This app's public callable interface, and the ONLY place a file is ever removed or moved.

Phase 3 implements ``OrphanScanner`` (``scan()``, ``build_reference_set()``) and
``CleanupService`` (``run()``, ``purge_history()``) exactly as ``docs/CONTRACT.md`` §3 specifies.

Every code path in this module that deletes or moves a file honours all four safety rails,
unconditionally, per this repo's ``CLAUDE.md`` rule 3 and ``docs/CONTRACT.md`` §0:

* **dry-run** — no storage call when ``dry_run=True``.
* **grace period** — a file modified within ``CLEANUP["GRACE_PERIOD_SECONDS"]`` is never a
  candidate.
* **exclude patterns** — ``CLEANUP["EXCLUDE_PATTERNS"]`` fnmatch globs are never candidates.
* **record-before-delete** — the ``CleanupRunFile`` row is written *before* the delete is
  attempted, never after.

These four rails govern ``CleanupService`` specifically. Upstream ``django_cleanup``'s own
per-save/per-delete deletion is a separate, pre-existing contract this package only observes
(logs, via the ``TRACK_AUTO_DELETIONS`` receiver) and never gates — it has already committed by
the time any receiver here runs (``docs/CONTRACT.md`` §9.4).
"""

from __future__ import annotations

import fnmatch
import logging
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any, cast

from appkit.cache import build_cache_key, cached_call, invalidate_namespace
from django.apps import apps as django_apps
from django.core.files.storage import Storage, default_storage, storages
from django.db import models
from django.utils import timezone

from cleanup_app import conf
from cleanup_app.models import CleanupRun, CleanupRunFile
from cleanup_app.signals import cleanup_run_finished, cleanup_run_started

if TYPE_CHECKING:
    from django.contrib.auth.base_user import AbstractBaseUser

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------------- data shapes


@dataclass(frozen=True)
class OrphanFileInfo:
    """One candidate orphan, with the size/mtime ``scan()`` already had to fetch to apply the
    grace-period rail and compute ``OrphanScanResult.total_size``.

    **Deviation from ``docs/CONTRACT.md`` §3's literal ``files: list[str]``**, recorded in §9:
    a bare path would discard data this module has already paid to fetch and force §4's
    ``GET /orphans/`` (``{file_path, file_size, modified_at}``) to re-stat every file on every
    page instead of reading it from the cached snapshot. Named ``OrphanFileInfo``, not
    ``OrphanFile``, to avoid colliding with Phase 5's unmanaged admin model of that name (§6).
    """

    path: str
    size: int
    modified_at: datetime


@dataclass(frozen=True)
class OrphanScanResult:
    files: list[OrphanFileInfo]
    total_size: int
    files_scanned: int
    truncated: bool


@dataclass(frozen=True)
class _Candidate:
    """Internal pairing of a target path with the size to record for it — covers both a real
    scan candidate (from the snapshot) and an unknown ``file_paths`` entry (size unknowable)."""

    path: str
    size: int
    known: bool = True


@dataclass
class _RunOutcome:
    files_scanned: int = 0
    files_deleted: int = 0
    files_failed: int = 0
    bytes_freed: int = 0


# --------------------------------------------------------------------------------- private helpers


def _get_storage() -> Storage:
    alias = conf.get_setting("STORAGE_ALIAS")
    if alias == "default":
        return default_storage
    return storages[alias]


def _join(path: str, name: str) -> str:
    return f"{path}/{name}" if path else name


def _walk(storage: Storage, path: str) -> Iterator[str]:
    """Recursively lists every file under ``path`` (empty string = storage root)."""
    directories, files = storage.listdir(path)
    for filename in files:
        yield _join(path, filename)
    for directory in directories:
        yield from _walk(storage, _join(path, directory))


def _iter_storage_files(storage: Storage, roots: list[str] | None) -> Iterator[str]:
    for root in roots or [""]:
        yield from _walk(storage, root)


def _is_excluded(name: str, patterns: list[str]) -> bool:
    basename = name.rsplit("/", 1)[-1]
    return any(
        fnmatch.fnmatch(name, pattern) or fnmatch.fnmatch(basename, pattern) for pattern in patterns
    )


def _within_grace_period(modified_at: datetime, grace_period_seconds: int) -> bool:
    """True if ``modified_at`` is more recent than ``grace_period_seconds`` ago — protects
    in-progress uploads and files referenced by an uncommitted transaction.

    ``get_modified_time()`` returns an aware UTC datetime when ``USE_TZ`` is on, otherwise a
    naive local one (verified against ``FileSystemStorage._datetime_from_timestamp`` — every
    storage backend is expected to follow the same convention) — compared against the matching
    flavour of "now" rather than assuming one or the other.
    """
    now = timezone.now() if timezone.is_aware(modified_at) else datetime.now()
    return now - modified_at < timedelta(seconds=grace_period_seconds)


def _scheduled_run_in_progress() -> bool:
    """Shared by ``tasks.run_scheduled_cleanup`` and the ``cleanup_orphans`` management command
    (``docs/CONTRACT.md`` §8): skip a new scheduled run if a ``SCHEDULED`` run is already
    ``PENDING``/``RUNNING``. Deliberately scoped to ``trigger=SCHEDULED`` only — an ``AUTO`` or
    ``API`` run in flight must never block the schedule (§9.4/§9.5), and per §9.4 an ``AUTO`` run
    can never carry ``PENDING``/``RUNNING`` status anyway.
    """
    return CleanupRun.objects.filter(
        trigger=CleanupRun.Trigger.SCHEDULED,
        status__in=(CleanupRun.Status.PENDING, CleanupRun.Status.RUNNING),
    ).exists()


# --------------------------------------------------------------------------------- OrphanScanner


class OrphanScanner:
    @staticmethod
    def build_reference_set() -> set[str]:
        """Every file name any installed model's FileField/ImageField currently points at,
        across every model — including one only reachable via a reverse relation, since this
        walks apps.get_models() directly rather than following relations from a starting model.
        A model in CLEANUP["IGNORED_MODELS"] is still included here (§9.1) — this set is purely
        protective, and dropping a model from it would make every file its live rows reference
        into a false-positive orphan.
        """
        referenced: set[str] = set()

        for model in django_apps.get_models():
            file_fields = [f for f in model._meta.get_fields() if isinstance(f, models.FileField)]
            if not file_fields:
                continue

            # ``_base_manager``, not ``.objects``/``_default_manager`` — a host model with a
            # soft-delete default manager would otherwise hide live rows from this walk and turn
            # their still-referenced files into false-positive orphans. This set exists purely
            # to protect files a live row still needs, so it must see every live row, not just
            # the ones a host's default manager chooses to expose.
            manager = model._base_manager
            for f in file_fields:
                for value in manager.values_list(f.name, flat=True).iterator():
                    if value:
                        referenced.add(str(value).replace("\\", "/"))

        return referenced

    @staticmethod
    def scan(*, dry_run: bool = False) -> OrphanScanResult:
        """Walk CLEANUP["STORAGE_ALIAS"] (default_storage if "default"), scoped to SCAN_ROOTS if
        set. A file is a candidate orphan iff: not in build_reference_set(), not matching any
        CLEANUP["EXCLUDE_PATTERNS"] glob, and storage.get_modified_time() is older than
        CLEANUP["GRACE_PERIOD_SECONDS"] ago. Capped at CLEANUP["MAX_FILES_PER_RUN"]; truncated=True
        on the result if the cap was hit. Caches the snapshot under
        appkit.cache.build_cache_key("cleanup", "orphans") via appkit.cache.cached_call, timeout
        CLEANUP["SCAN_CACHE_TIMEOUT"]. dry_run is accepted for signature symmetry with
        CleanupService.run() but scan() never writes to storage regardless of its value — it only
        reads and lists.
        """
        key = build_cache_key("cleanup", "orphans")
        timeout = conf.get_setting("SCAN_CACHE_TIMEOUT")
        return cached_call(key, timeout, OrphanScanner._run_scan)

    @staticmethod
    def _run_scan() -> OrphanScanResult:
        storage = _get_storage()
        roots: list[str] | None = conf.get_setting("SCAN_ROOTS")
        exclude_patterns: list[str] = conf.get_setting("EXCLUDE_PATTERNS")
        grace_period_seconds: int = conf.get_setting("GRACE_PERIOD_SECONDS")
        max_files: int = conf.get_setting("MAX_FILES_PER_RUN")

        reference_set = OrphanScanner.build_reference_set()

        files: list[OrphanFileInfo] = []
        total_size = 0
        files_scanned = 0
        truncated = False

        for name in _iter_storage_files(storage, roots):
            files_scanned += 1

            if name in reference_set:
                continue
            if _is_excluded(name, exclude_patterns):
                continue

            try:
                modified_at = storage.get_modified_time(name)
                size = storage.size(name)
            except (OSError, NotImplementedError):
                # An un-stattable file is never a candidate — fail safe rather than guess at
                # its age (grace period) or size.
                logger.warning("cleanup_app: could not stat %r during scan — skipping.", name)
                continue

            if _within_grace_period(modified_at, grace_period_seconds):
                continue

            if len(files) >= max_files:
                truncated = True
                continue

            files.append(OrphanFileInfo(path=name, size=size, modified_at=modified_at))
            total_size += size

        return OrphanScanResult(
            files=files,
            total_size=total_size,
            files_scanned=files_scanned,
            truncated=truncated,
        )


# --------------------------------------------------------------------------------- CleanupService


class CleanupService:
    @staticmethod
    def run(
        *,
        trigger: str = "manual",
        dry_run: bool = False,
        file_paths: list[str] | None = None,
        initiated_by: AbstractBaseUser | None = None,
    ) -> CleanupRun:
        """Create a CleanupRun(status=RUNNING, trigger=trigger, dry_run=dry_run,
        initiated_by=initiated_by), send cleanup_run_started. If file_paths is given, operate only
        on that subset of the CURRENT cached OrphanScanner snapshot; otherwise run a fresh
        OrphanScanner.scan(). For every candidate file: create its CleanupRunFile row
        (deleted=False) FIRST, then attempt delete-or-quarantine (CLEANUP["QUARANTINE_DIR"] set ->
        move there; otherwise storage.delete()), then update that same row with the outcome.
        dry_run=True writes every row with deleted=False and performs no storage operation at
        all. One file's failure never aborts the remaining files. On completion: status=SUCCESS
        if zero failures, PARTIAL if some failed, FAILED if all failed or an unhandled exception
        occurred; sets finished_at and the four aggregate counts; sends cleanup_run_finished.
        Returns the finished CleanupRun.
        """
        run = CleanupRun.objects.create(
            status=CleanupRun.Status.RUNNING,
            trigger=trigger,
            dry_run=dry_run,
            # django-stubs resolves initiated_by's ForeignKey(settings.AUTH_USER_MODEL) to the
            # concrete, swappable user model — not the abstract AbstractBaseUser this public
            # signature deliberately uses (docs/CONTRACT.md §3's own type-hint convention, since
            # the concrete model isn't knowable at this package's authoring time). A cast, not a
            # narrower parameter type, is what keeps the public signature swappable-user-safe.
            initiated_by=cast("Any", initiated_by),
        )
        cleanup_run_started.send(sender=CleanupRun, run_id=run.pk, trigger=trigger, dry_run=dry_run)

        try:
            candidates = CleanupService._resolve_candidates(file_paths)
            outcome = CleanupService._process_candidates(run, candidates, dry_run=dry_run)
        except Exception as exc:  # a run must finish and be recorded, never propagate
            logger.exception("cleanup_app: CleanupService.run() failed unexpectedly.")
            run.status = CleanupRun.Status.FAILED
            run.error = str(exc)
            run.finished_at = timezone.now()
            run.save(update_fields=["status", "error", "finished_at"])
            cleanup_run_finished.send(
                sender=CleanupRun,
                run_id=run.pk,
                status=run.status,
                files_deleted=run.files_deleted,
                bytes_freed=run.bytes_freed,
            )
            return run

        # SUCCESS if zero failures (including the trivial "nothing to do" case), FAILED if every
        # candidate failed, PARTIAL otherwise — the literal docs/CONTRACT.md §3 rule, applied
        # the same way whether or not dry_run is set. In dry_run, a "failure" can only come from
        # an unknown file_paths entry (a real delete is never attempted), so a plain dry run with
        # no unknown paths is always SUCCESS.
        if outcome.files_failed == 0:
            status = CleanupRun.Status.SUCCESS
        elif outcome.files_failed >= outcome.files_scanned:
            status = CleanupRun.Status.FAILED
        else:
            status = CleanupRun.Status.PARTIAL

        run.status = status
        run.finished_at = timezone.now()
        run.files_scanned = outcome.files_scanned
        run.files_deleted = outcome.files_deleted
        run.files_failed = outcome.files_failed
        run.bytes_freed = outcome.bytes_freed
        run.save(
            update_fields=[
                "status",
                "finished_at",
                "files_scanned",
                "files_deleted",
                "files_failed",
                "bytes_freed",
            ]
        )

        cleanup_run_finished.send(
            sender=CleanupRun,
            run_id=run.pk,
            status=run.status,
            files_deleted=run.files_deleted,
            bytes_freed=run.bytes_freed,
        )

        if not dry_run:
            # A run that actually touched storage invalidates the cached scan snapshot — the
            # next GET /orphans/ (Phase 4) or admin page load must not show files that were just
            # deleted. Phase 4's view also calls this after POST /orphans/delete/; doing it here
            # too is what makes the management command and Celery task (which never go through
            # that view) correct on their own.
            invalidate_namespace("cleanup")

        return run

    @staticmethod
    def _resolve_candidates(file_paths: list[str] | None) -> list[_Candidate]:
        snapshot = OrphanScanner.scan()

        if file_paths is None:
            return [_Candidate(path=f.path, size=f.size) for f in snapshot.files]

        known = {f.path: f.size for f in snapshot.files}
        candidates = []
        for path in file_paths:
            if path in known:
                candidates.append(_Candidate(path=path, size=known[path]))
            else:
                # Not present in the current snapshot — never touched on disk. Recorded as a
                # failed row rather than silently dropped, so a caller can see why a requested
                # path didn't get deleted. Phase 4's POST /orphans/delete/ already rejects this
                # case with a 400 before calling run() at all; this is defence-in-depth for any
                # other caller of CleanupService.run(), per docs/CONTRACT.md's own "this method
                # trusts its input" read alongside CLAUDE.md rule 3's unconditional rails.
                candidates.append(_Candidate(path=path, size=0, known=False))
        return candidates

    @staticmethod
    def _process_candidates(
        run: CleanupRun, candidates: list[_Candidate], *, dry_run: bool
    ) -> _RunOutcome:
        outcome = _RunOutcome(files_scanned=len(candidates))
        storage = _get_storage()
        quarantine_dir = conf.get_setting("QUARANTINE_DIR")

        for candidate in candidates:
            # record-before-delete: this row is written BEFORE any delete/quarantine attempt
            # below, never after — the one rail that governs ordering, not just per-file
            # bookkeeping.
            row = CleanupRunFile.objects.create(
                run=run,
                file_path=candidate.path,
                file_size=candidate.size,
                deleted=False,
            )

            if not candidate.known:
                row.error = "not present in the current orphan snapshot"
                row.save(update_fields=["error"])
                outcome.files_failed += 1
                continue

            if dry_run:
                continue

            try:
                if quarantine_dir:
                    CleanupService._quarantine(storage, candidate.path, quarantine_dir)
                    row.quarantined = True
                else:
                    storage.delete(candidate.path)
                row.deleted = True
                row.save(update_fields=["deleted", "quarantined"])
                outcome.files_deleted += 1
                outcome.bytes_freed += candidate.size
            except Exception as exc:  # one file's failure must never abort the remaining files
                row.error = str(exc)
                row.save(update_fields=["error"])
                outcome.files_failed += 1
                logger.warning(
                    "cleanup_app: failed to remove orphan file %r: %s", candidate.path, exc
                )

        return outcome

    @staticmethod
    def _quarantine(storage: Storage, path: str, quarantine_dir: str) -> None:
        destination = _join(quarantine_dir, path)
        with storage.open(path, "rb") as source:
            storage.save(destination, source)
        storage.delete(path)

    @staticmethod
    def purge_history(*, older_than_days: int | None = None) -> int:
        """Delete CleanupRun rows (cascading their CleanupRunFile rows) older than
        older_than_days, or CLEANUP["HISTORY_RETENTION_DAYS"] if None. Returns the count of
        CleanupRun rows deleted. Touches only history tables — never media storage.
        """
        days = (
            older_than_days
            if older_than_days is not None
            else conf.get_setting("HISTORY_RETENTION_DAYS")
        )
        cutoff = timezone.now() - timedelta(days=days)
        # .delete()'s bulk return is (total_rows, {label: count}) across CleanupRun AND its
        # cascaded CleanupRunFile rows — the CleanupRun-only count comes from the per-model dict,
        # not the total, since the contract's return value is "count of CleanupRun rows deleted".
        _, per_model = CleanupRun.objects.filter(started_at__lt=cutoff).delete()
        return per_model.get("cleanup_app.CleanupRun", 0)
