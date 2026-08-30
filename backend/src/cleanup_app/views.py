"""Intentionally unused.

This app has no user-facing surface at all (``docs/CONTRACT.md`` §0) — ``urls.py`` ships empty
and stays empty. Every endpoint this app exposes is admin-only and lives in ``admin_views.py``,
routed from ``urls_admin.py``, gated by ``appkit.permissions.IsAppAdmin`` with zero exceptions.

This module exists only so a host or tool that imports ``cleanup_app.views`` by convention
doesn't hit an ``ImportError``.
"""
