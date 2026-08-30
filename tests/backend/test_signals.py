"""Tests for ``cleanup_app.signals`` — each payload asserted exactly against ``docs/CONTRACT.md``
§2, character for character (keys AND values), not just "the receiver was called".
"""

from __future__ import annotations

from typing import Any

import pytest

from cleanup_app.models import CleanupRun
from cleanup_app.services import CleanupService
from cleanup_app.signals import cleanup_run_finished, cleanup_run_started

pytestmark = pytest.mark.django_db


def test_cleanup_run_started_payload(media_storage: Any) -> None:
    received: list[dict[str, Any]] = []

    def _receiver(sender: Any, **kwargs: Any) -> None:
        received.append({"sender": sender, **kwargs})

    cleanup_run_started.connect(_receiver)
    try:
        run = CleanupService.run(trigger=CleanupRun.Trigger.MANUAL, dry_run=True)
    finally:
        cleanup_run_started.disconnect(_receiver)

    assert len(received) == 1
    payload = received[0]
    assert payload["sender"] is CleanupRun
    assert set(payload.keys()) == {"sender", "signal", "run_id", "trigger", "dry_run"}
    assert payload["run_id"] == run.pk
    assert payload["trigger"] == CleanupRun.Trigger.MANUAL
    assert payload["dry_run"] is True


def test_cleanup_run_finished_payload(media_storage: Any) -> None:
    received: list[dict[str, Any]] = []

    def _receiver(sender: Any, **kwargs: Any) -> None:
        received.append({"sender": sender, **kwargs})

    cleanup_run_finished.connect(_receiver)
    try:
        run = CleanupService.run(trigger=CleanupRun.Trigger.MANUAL, dry_run=True)
    finally:
        cleanup_run_finished.disconnect(_receiver)

    assert len(received) == 1
    payload = received[0]
    assert payload["sender"] is CleanupRun
    assert set(payload.keys()) == {
        "sender",
        "signal",
        "run_id",
        "status",
        "files_deleted",
        "bytes_freed",
    }
    assert payload["run_id"] == run.pk
    assert payload["status"] == run.status
    assert payload["files_deleted"] == run.files_deleted
    assert payload["bytes_freed"] == run.bytes_freed
