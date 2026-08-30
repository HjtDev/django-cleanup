"""Intentionally empty.

This app has no user-facing surface (``docs/CONTRACT.md`` §0) — every endpoint lives in
``urls_admin.py`` instead. A host that mounts this module by the usual per-app-``urls.py``
convention gets zero routes, not an ``ImportError``.
"""

urlpatterns: list = []
