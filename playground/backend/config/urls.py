"""Playground URLconf. Mounts cleanup_app's admin-only API under
``/api/v1/cleanup/admin/...`` — matching the basePath (``/api/v1/cleanup``) the frontend's
``ApiClientProvider`` is configured with, plus the ``admin/`` segment
``frontend/src/api/manager.ts`` always appends itself.
"""

from __future__ import annotations

from django.conf import settings
from django.contrib import admin
from django.http import JsonResponse
from django.urls import include, path, re_path
from django.views.static import serve


def healthz(request):  # noqa: ANN001, ANN201 -- playground-only, not part of the app's contract
    return JsonResponse({"status": "ok"})


urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/v1/cleanup/admin/", include("cleanup_app.urls_admin")),
    path("healthz/", healthz),
    # django.views.static.serve() directly, not conf.urls.static.static() (which is a DEBUG-only
    # no-op) — this playground runs under uvicorn, not `runserver`'s auto-serving dev mode, and
    # ships no separate static/media server, so both need an explicit route regardless of DEBUG.
    re_path(r"^media/(?P<path>.*)$", serve, {"document_root": settings.MEDIA_ROOT}),
    re_path(r"^static/(?P<path>.*)$", serve, {"document_root": settings.STATIC_ROOT}),
]
