"""``manage.py cleanup_orphans`` — the cron-friendly equivalent of ``tasks.run_scheduled_cleanup``
for a host without Celery (``docs/CONTRACT.md`` §8). Same underlying ``CleanupService.run()``
call, same concurrency guard, re-implemented against the same private query via
``services._scheduled_run_in_progress`` so the two paths cannot drift apart.
"""

from __future__ import annotations

from argparse import ArgumentParser
from typing import Any

from django.core.management.base import BaseCommand, CommandError

from cleanup_app.models import CleanupRun
from cleanup_app.services import CleanupService, _scheduled_run_in_progress


class Command(BaseCommand):
    help = "Run a media cleanup pass — finds and removes orphaned files (docs/CONTRACT.md §8)."

    def add_arguments(self, parser: ArgumentParser) -> None:
        parser.add_argument(
            "--dry-run",
            action="store_true",
            default=False,
            help="Scan and record candidates without deleting or moving anything.",
        )
        parser.add_argument(
            "--trigger",
            choices=CleanupRun.Trigger.values,
            default=CleanupRun.Trigger.SCHEDULED,
            help="Trigger value recorded on the created CleanupRun (default: scheduled).",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        trigger = options["trigger"]
        dry_run = options["dry_run"]

        # The concurrency guard is scoped to trigger=SCHEDULED (docs/CONTRACT.md §8/§9.5) — a
        # host that deliberately runs this command with --trigger=manual or --trigger=api isn't
        # subject to the schedule-overlap guard at all, matching tasks.run_scheduled_cleanup's
        # own scope.
        if trigger == CleanupRun.Trigger.SCHEDULED and _scheduled_run_in_progress():
            self.stdout.write(
                self.style.WARNING(
                    "cleanup_orphans: skipped — a scheduled run is already in progress."
                )
            )
            return

        run = CleanupService.run(trigger=trigger, dry_run=dry_run)

        self.stdout.write(
            f"cleanup_orphans: run #{run.pk} finished with status={run.status} "
            f"(scanned={run.files_scanned}, deleted={run.files_deleted}, "
            f"failed={run.files_failed}, bytes_freed={run.bytes_freed})"
        )

        if run.status == CleanupRun.Status.FAILED:
            raise CommandError(f"cleanup_orphans: run #{run.pk} failed: {run.error}")
