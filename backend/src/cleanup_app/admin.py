"""Jazzmin ``ModelAdmin`` registrations.

Phase 2 registers ``CleanupRun``/``CleanupRunFile`` (history, read-mostly). Phase 5 adds the
orphan-review page itself — an unmanaged ``OrphanFile`` model whose ``changelist_view`` is fully
overridden to call ``services.OrphanScanner.scan()`` instead of querying a database
(``docs/CONTRACT.md`` §6, Option A, chosen over a custom ``admin_views.py`` view because it earns
a real Jazzmin sidebar entry with zero ``JAZZMIN_SETTINGS`` edits from the host).
"""
