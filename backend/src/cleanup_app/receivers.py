"""The ``TRACK_AUTO_DELETIONS`` receiver — logs, never gates, upstream ``django_cleanup``'s own
per-save/per-delete deletions into this app's history tables.

Connected from ``cleanup_app.apps.CleanupAppConfig.ready()`` when
``CLEANUP["TRACK_AUTO_DELETIONS"]`` is true (default), independently of
``CLEANUP["AUTO_CONNECT"]`` — a host that sets ``AUTO_CONNECT=False`` and wires
``django_cleanup`` itself still gets its deletions logged here, since ``cleanup_post_delete``
fires regardless of who connected upstream's own handlers.

**This module is a log, not a gate** (``docs/CONTRACT.md`` §9.4): by the time
``cleanup_post_delete`` fires, upstream has already deleted the file inside
``django.db.transaction.on_commit`` (verified against ``django_cleanup/handlers.py:105-120``) —
there is no rail left to apply. The dry-run/grace-period/exclude-pattern/record-before-delete
rails govern ``services.CleanupService`` only; a host that wants those files rail-governed
instead adds the model to ``CLEANUP["IGNORED_MODELS"]`` and lets ``OrphanScanner`` find and clean
them on its own schedule, under its own rails.

**Grouping: one ``CleanupRun(trigger=AUTO)`` per UTC calendar day** (``docs/CONTRACT.md`` §9.4),
looked up via an explicit ``[day_start, day_end)`` range rather than the ``__date`` lookup —
``__date`` converts to the currently active timezone before extracting a date, which would make
the "day" this groups by depend on request-local timezone activation instead of a stable UTC (or,
under ``USE_TZ=False``, local-naive) boundary. Chosen over a thread-local-per-request run because
it needs no middleware and behaves identically whether the deletion happens in a request, a
Celery task, a management command, or a shell. A rare duplicate day-row under concurrent
first-events-of-the-day is tolerated, not guarded against — this is a log, and a second row for
the same day is a cosmetic artifact, not a correctness or safety issue.

**Status: never ``PENDING``/``RUNNING``.** Created ``SUCCESS``; the first event reporting
``success=False`` flips it to ``PARTIAL`` and it stays there. This is what keeps a day-spanning
``AUTO`` row from ever tripping ``services._scheduled_run_in_progress()``'s ``SCHEDULED``-only
concurrency guard (``docs/CONTRACT.md`` §8/§9.5).
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from django.utils import timezone

from cleanup_app.models import CleanupRun, CleanupRunFile

_DISPATCH_UID = "cleanup_app_track_auto_deletions"


def _day_bounds(now: datetime) -> tuple[datetime, datetime]:
    day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    return day_start, day_start + timedelta(days=1)


def _get_or_create_daily_auto_run() -> CleanupRun:
    day_start, day_end = _day_bounds(timezone.now())
    existing = (
        CleanupRun.objects.filter(
            trigger=CleanupRun.Trigger.AUTO,
            started_at__gte=day_start,
            started_at__lt=day_end,
        )
        .order_by("-started_at")
        .first()
    )
    if existing is not None:
        return existing

    return CleanupRun.objects.create(
        trigger=CleanupRun.Trigger.AUTO,
        status=CleanupRun.Status.SUCCESS,
        dry_run=False,
    )


def track_auto_deletion(sender: Any, **kwargs: Any) -> None:
    """Receiver for ``django_cleanup.signals.cleanup_post_delete``.

    Payload verified against ``django_cleanup/handlers.py`` 9.0.0's actual
    ``cleanup_post_delete.send(sender=sender, error=error, success=success, **event)`` call —
    ``file``, ``file_name``, ``model_name``, ``field_name``, ``instance``, ``default_file_name``,
    ``deleted``, ``updated``, ``success``, ``error``. ``error`` is an ``Exception`` instance or
    ``None``, never a string (§9.4) — stored as ``str(error)`` when present.
    """
    success = bool(kwargs.get("success"))
    error = kwargs.get("error")
    file_name = kwargs.get("file_name") or ""

    run = _get_or_create_daily_auto_run()

    CleanupRunFile.objects.create(
        run=run,
        file_path=file_name,
        # The file is already gone by the time this receiver runs (upstream deletes inside
        # on_commit before sending this signal) — its size is unrecoverable, and there is
        # nothing left to stat. AUTO run rows always carry file_size=0 for this reason.
        file_size=0,
        deleted=success,
        error=str(error) if error else "",
    )

    run.files_scanned += 1
    if success:
        run.files_deleted += 1
    else:
        run.files_failed += 1
        run.status = CleanupRun.Status.PARTIAL
    run.finished_at = timezone.now()
    run.save(
        update_fields=["files_scanned", "files_deleted", "files_failed", "status", "finished_at"]
    )


def connect() -> None:
    """Connects :func:`track_auto_deletion` to upstream's ``cleanup_post_delete`` signal.

    Called from ``CleanupAppConfig.ready()`` only when ``CLEANUP["TRACK_AUTO_DELETIONS"]`` is
    true. Guarded by an explicit ``dispatch_uid`` so Django's autoreloader (or a host that also
    imports this module directly) can never double-connect it.
    """
    from django_cleanup.signals import cleanup_post_delete

    cleanup_post_delete.connect(track_auto_deletion, dispatch_uid=_DISPATCH_UID)
