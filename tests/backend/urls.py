"""Test-tree URLconf — mounts the same URLconfs a real host's own ``backend/config/urls.py``
would mount per this app's README (``APP-DESIGN.md`` §7.1), nothing host-specific, plus Django
admin so Phase 2's admin tests exercise a real changelist.

``cleanup_app.urls``/``cleanup_app.urls_admin`` both ship intentionally empty at this phase
(``docs/CONTRACT.md`` §0/§4 — Phase 4 adds the six admin routes) — including them now proves
they resolve cleanly under a real ``ROOT_URLCONF`` from day one.
"""

from __future__ import annotations

from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/v1/cleanup/", include("cleanup_app.urls")),
    path("api/v1/cleanup/admin/", include("cleanup_app.urls_admin")),
]
