"""Celery task(s), behind the ``celery`` extra only.

``cleanup_app.tasks.run_scheduled_cleanup`` (Phase 3) calls
``services.CleanupService.run(trigger=CleanupRun.Trigger.SCHEDULED)`` with the concurrency guard
``docs/CONTRACT.md`` §8 specifies (skip if a ``CleanupRun`` with ``status in (PENDING, RUNNING)``
and ``trigger=SCHEDULED`` already exists). ``cleanup_app.tasks.run_cleanup_run`` (Phase 4) is the
enqueue target for ``admin_views.CleanupRunListCreateView``'s ``POST /runs/`` when
``CLEANUP["USE_CELERY"]`` is on — it drives an already-created row via
``CleanupService.execute_run()`` rather than creating a new one.

This module must not hard-import ``celery`` at module scope — a host without the ``celery``
extra installed must be able to import every other part of this package without error. This app
is fully functional with no Celery worker running at all; a host without Celery uses the
equivalent ``cleanup_orphans`` management command via plain cron instead.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any, TypeVar

from cleanup_app.models import CleanupRun
from cleanup_app.services import CleanupService, _scheduled_run_in_progress

logger = logging.getLogger(__name__)

_F = TypeVar("_F", bound=Callable[..., Any])

try:
    from celery import shared_task
except ModuleNotFoundError:
    # No hard dependency on celery — a bare install (no `celery` extra) must still be able to
    # `import cleanup_app.tasks` without error, per this module's own docstring and
    # docs/CONTRACT.md's dependencies table (celery is an optional extra, never a core
    # dependency). `name=` is accepted and ignored to match shared_task's call signature below.
    def shared_task(*_args: Any, **_kwargs: Any) -> Callable[[_F], _F]:
        def decorator(func: _F) -> _F:
            return func

        return decorator


@shared_task(name="cleanup_app.tasks.run_scheduled_cleanup")
def run_scheduled_cleanup() -> int | None:
    """Calls CleanupService.run(trigger=CleanupRun.Trigger.SCHEDULED). Returns the created run's
    id, or None if skipped due to the concurrency guard below.

    Concurrency guard: skip (log, return None) if a CleanupRun with
    status in (PENDING, RUNNING) and trigger=SCHEDULED already exists. Narrower than gating on
    status alone (any status) so a stuck AUTO or API run never blocks the schedule — and per §9.4,
    an AUTO run can never carry PENDING/RUNNING status, so it can never trip this guard regardless.
    """
    if _scheduled_run_in_progress():
        logger.info(
            "cleanup_app: run_scheduled_cleanup skipped — a scheduled run is already in progress."
        )
        return None

    run = CleanupService.run(trigger=CleanupRun.Trigger.SCHEDULED)
    return run.pk


@shared_task(name="cleanup_app.tasks.run_cleanup_run")
def run_cleanup_run(run_id: int) -> int:
    """Drives an already-created ``CleanupRun`` row to completion — the enqueue target for
    ``docs/CONTRACT.md`` §4's ``POST /runs/`` when ``CLEANUP["USE_CELERY"]`` is on and the
    ``celery`` extra is importable. The view creates the ``PENDING`` row synchronously (so its
    response always has a real id to return) and only the run itself is deferred to this task.

    Loads the row and calls ``CleanupService.execute_run(run)`` — not ``CleanupService.run()``,
    which would create a second, redundant row. Returns the run's id once finished.
    """
    run = CleanupRun.objects.get(pk=run_id)
    CleanupService.execute_run(run)
    return run.pk
