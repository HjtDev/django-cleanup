"""Data models for this app's cleanup history.

Phase 2 implements ``CleanupRun`` (per-run aggregates: status, trigger, dry_run, counts,
bytes_freed) and ``CleanupRunFile`` (per-file rows, FK to ``CleanupRun``) exactly as
``docs/CONTRACT.md`` §1 specifies.

The orphan-review page's backing model (``OrphanFile``, an unmanaged model with no table,
``docs/CONTRACT.md`` §6) is NOT defined here — it belongs to Phase 5's ``admin.py``, since it
represents a live scan result, not a stored row.

Every FK-shaped reference in this module is ``settings.AUTH_USER_MODEL`` (``initiated_by`` on
``CleanupRun``) or nothing — never a concrete ``User`` import, and never a reference to another
app package's model (``docs/CONTRACT.md`` §1: "Requires another app package: No").
"""

from __future__ import annotations

from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _


class CleanupRun(models.Model):
    """One cleanup pass — a full orphan scan or a day's worth of auto-deletions.

    ``docs/CONTRACT.md`` §1. ``Trigger`` has FOUR values, not the three the build guide's prose
    lists — ``AUTO`` groups upstream django-cleanup's own per-save/per-delete deletions into one
    row per UTC calendar day when ``CLEANUP["TRACK_AUTO_DELETIONS"]`` is on (§9.4). An ``AUTO``
    run's status is never ``PENDING``/``RUNNING`` (§9.4) — this is what keeps a day-spanning
    ``AUTO`` row from ever tripping §8's ``SCHEDULED``-only concurrency guard.
    """

    class Status(models.TextChoices):
        PENDING = "pending", _("Pending")
        RUNNING = "running", _("Running")
        SUCCESS = "success", _("Success")
        FAILED = "failed", _("Failed")
        PARTIAL = "partial", _("Partial")

    class Trigger(models.TextChoices):
        MANUAL = "manual", _("Manual")  # a human clicked "run" in the admin or API
        SCHEDULED = "scheduled", _("Scheduled")  # tasks.run_scheduled_cleanup or the mgmt command
        API = "api", _("API")  # POST /runs/ from an external caller
        AUTO = "auto", _("Auto")  # upstream's own per-save/per-delete deletions, logged (§9.4)

    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)
    trigger = models.CharField(max_length=10, choices=Trigger.choices)
    initiated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="cleanup_runs",
    )
    dry_run = models.BooleanField(default=False)
    started_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    files_scanned = models.PositiveIntegerField(default=0)
    files_deleted = models.PositiveIntegerField(default=0)
    files_failed = models.PositiveIntegerField(default=0)
    bytes_freed = models.PositiveBigIntegerField(default=0)
    error = models.TextField(blank=True)

    class Meta:
        indexes = (
            models.Index(fields=["status", "-started_at"]),
            models.Index(fields=["trigger"]),
        )

    def __str__(self) -> str:
        return f"CleanupRun #{self.pk} ({self.trigger}/{self.status})"


class CleanupRunFile(models.Model):
    """One file touched by a :class:`CleanupRun` — deleted, quarantined, or failed.

    ``docs/CONTRACT.md`` §1. Written *before* the delete/quarantine is attempted, never after
    (the record-before-delete rail, ``docs/CONTRACT.md`` §0) — that ordering is enforced by
    ``services.CleanupService``, not by this model.
    """

    run = models.ForeignKey(CleanupRun, on_delete=models.CASCADE, related_name="files")
    file_path = models.CharField(max_length=1024)
    file_size = models.PositiveBigIntegerField(default=0)
    deleted = models.BooleanField(default=False)
    quarantined = models.BooleanField(default=False)
    error = models.TextField(blank=True)

    class Meta:
        indexes = (models.Index(fields=["run", "deleted"]),)

    def __str__(self) -> str:
        return f"{self.file_path} (run #{self.run_id})"
