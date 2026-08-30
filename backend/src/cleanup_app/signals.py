"""This app's own emitted events.

Phase 3 defines ``cleanup_run_started`` (sends: ``run_id``, ``trigger``, ``dry_run``) and
``cleanup_run_finished`` (sends: ``run_id``, ``status``, ``files_deleted``, ``bytes_freed``),
both with ``sender=CleanupRun``, exactly as ``docs/CONTRACT.md`` §2 specifies. Minimal payloads
by design — a host receiver that needs more fetches the row by ``run_id``
(``APP-DESIGN.md`` §6's versioned-contract rule: adding a kwarg later is a minor bump, removing
one is major, so payloads start as small as possible).
"""

from __future__ import annotations

import django.dispatch

cleanup_run_started = django.dispatch.Signal()
"""Sent when CleanupService.run() begins. sender=CleanupRun.
Payload: run_id: int, trigger: str, dry_run: bool"""

cleanup_run_finished = django.dispatch.Signal()
"""Sent when CleanupService.run() completes (success, partial, or failed). sender=CleanupRun.
Payload: run_id: int, status: str, files_deleted: int, bytes_freed: int"""
