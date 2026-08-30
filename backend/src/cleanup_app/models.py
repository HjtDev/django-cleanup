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
