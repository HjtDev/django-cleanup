"""The only meaningful URLconf this app ships.

``docs/CONTRACT.md`` §4's six routes — ``GET /orphans/``, ``POST /orphans/delete/``,
``GET /runs/``, ``POST /runs/``, ``GET /runs/{id}/``, and ``GET /summary/`` — every one gated by
``cleanup_app.permissions.IsAppAdmin`` and admin-throttle-scoped (``cleanup_`` prefix). A host
mounts this module under its own admin API namespace; ``urls.py`` (user-facing) ships
intentionally empty since this app has no user-facing surface at all.

No ``app_name`` here, deliberately — a host including this module shouldn't be forced into a URL
namespace it didn't ask for.
"""

from __future__ import annotations

from django.urls import URLPattern, path

from cleanup_app.admin_views import (
    CleanupRunDetailView,
    CleanupRunListCreateView,
    CleanupSummaryView,
    OrphanDeleteView,
    OrphanFileListView,
)

urlpatterns: list[URLPattern] = [
    path("orphans/", OrphanFileListView.as_view(), name="cleanup-orphan-list"),
    path("orphans/delete/", OrphanDeleteView.as_view(), name="cleanup-orphan-delete"),
    path("runs/", CleanupRunListCreateView.as_view(), name="cleanup-run-list"),
    path("runs/<int:pk>/", CleanupRunDetailView.as_view(), name="cleanup-run-detail"),
    path("summary/", CleanupSummaryView.as_view(), name="cleanup-summary"),
]
