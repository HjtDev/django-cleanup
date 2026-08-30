"""The only meaningful URLconf this app ships.

Phase 4 adds ``docs/CONTRACT.md`` §4's six routes here — ``GET /orphans/``,
``POST /orphans/delete/``, ``GET /runs/``, ``POST /runs/``, ``GET /runs/{id}/``, and
``GET /summary/`` — every one gated by ``appkit.permissions.IsAppAdmin`` and admin-throttle-scoped
(``cleanup_`` prefix). A host mounts this module under its own admin API namespace; ``urls.py``
(user-facing) ships intentionally empty since this app has no user-facing surface at all.
"""

urlpatterns: list = []
