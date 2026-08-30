"""Celery task(s), behind the ``celery`` extra only.

Phase 3 implements ``cleanup_app.tasks.run_scheduled_cleanup``, calling
``services.CleanupService.run(trigger=CleanupRun.Trigger.SCHEDULED)`` with the concurrency guard
``docs/CONTRACT.md`` §8 specifies (skip if a ``CleanupRun`` with ``status in (PENDING, RUNNING)``
and ``trigger=SCHEDULED`` already exists).

This module must not hard-import ``celery`` at module scope — a host without the ``celery``
extra installed must be able to import every other part of this package without error. This app
is fully functional with no Celery worker running at all; a host without Celery uses the
equivalent ``cleanup_orphans`` management command via plain cron instead.
"""
