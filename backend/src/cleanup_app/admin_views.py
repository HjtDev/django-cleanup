"""Custom admin-dashboard API views.

Phases 4/5 implement the DRF views backing ``urls_admin.py``'s routes, and — only if
``docs/CONTRACT.md`` §6's Option A (an unmanaged model in ``admin.py``) turns out not to work
cleanly against Django admin's changelist internals — the documented Option B fallback view
reached through ``CleanupRunAdmin.get_urls()``.
"""
