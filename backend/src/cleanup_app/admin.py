"""Jazzmin ``ModelAdmin`` registrations.

Phase 2 registers ``CleanupRun``/``CleanupRunFile`` (history, read-mostly). Phase 5 adds the
orphan-review page itself — an unmanaged ``OrphanFile`` model whose ``changelist_view`` is fully
overridden to call ``services.OrphanScanner.scan()`` instead of querying a database
(``docs/CONTRACT.md`` §6, Option A, chosen over a custom ``admin_views.py`` view because it earns
a real Jazzmin sidebar entry with zero ``JAZZMIN_SETTINGS`` edits from the host).

Both registrations below are fully read-only — no add, no change, no delete. History is written
only by ``services.CleanupService``; retention runs through ``CleanupService.purge_history()``
(Phase 3), never a staff user clicking delete on the changelist, so the record of a real file
deletion can never be silently erased from the admin.

Suggested Jazzmin icons for ``README.md`` §8 (host adds these to its own ``JAZZMIN_SETTINGS``,
this app never touches that dict itself): ``fas fa-broom`` for ``CleanupRun``, ``fas
fa-file-circle-xmark`` for ``CleanupRunFile``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from django.contrib import admin
from django.db.models import Count, QuerySet
from django.http import HttpRequest
from django.urls import reverse
from django.utils.html import format_html
from django.utils.safestring import SafeString
from django.utils.translation import gettext_lazy as _

from cleanup_app.models import CleanupRun, CleanupRunFile

# django-stubs declares admin.ModelAdmin as Generic[_ModelT] for mypy's benefit only — the
# REAL django.contrib.admin.ModelAdmin is not subscriptable at runtime (no __class_getitem__)
# unless a host calls django_stubs_ext.monkeypatch(), which this library cannot assume and must
# not require as a runtime dependency just to satisfy its own type checker. Branching on
# TYPE_CHECKING gives mypy the parameterized base it needs while `class Foo(_CleanupRunAdminBase)`
# subclasses the plain, unsubscripted class at actual import time.
if TYPE_CHECKING:
    _CleanupRunAdminBase = admin.ModelAdmin[CleanupRun]
    _CleanupRunFileAdminBase = admin.ModelAdmin[CleanupRunFile]
else:
    _CleanupRunAdminBase = admin.ModelAdmin
    _CleanupRunFileAdminBase = admin.ModelAdmin


class _ReadOnlyAdminMixin:
    """No add, no change, no delete — history is written only by ``services.CleanupService``."""

    def has_add_permission(self, request: HttpRequest) -> bool:
        return False

    def has_change_permission(self, request: HttpRequest, obj: Any = None) -> bool:
        return False

    def has_delete_permission(self, request: HttpRequest, obj: Any = None) -> bool:
        return False


@admin.register(CleanupRun)
class CleanupRunAdmin(_ReadOnlyAdminMixin, _CleanupRunAdminBase):
    list_display = (
        "id",
        "status",
        "trigger",
        "initiated_by",
        "dry_run",
        "files_scanned",
        "files_deleted",
        "files_failed",
        "bytes_freed",
        "started_at",
        "finished_at",
        "files_link",
    )
    list_filter = ("status", "trigger", "dry_run")
    date_hierarchy = "started_at"
    ordering = ("-started_at",)
    search_fields = ("error",)
    readonly_fields = (
        "status",
        "trigger",
        "initiated_by",
        "dry_run",
        "started_at",
        "finished_at",
        "files_scanned",
        "files_deleted",
        "files_failed",
        "bytes_freed",
        "error",
    )

    def get_queryset(self, request: HttpRequest) -> QuerySet[CleanupRun]:
        return (
            super()
            .get_queryset(request)
            .select_related("initiated_by")
            .annotate(_files_count=Count("files"))
        )

    @admin.display(description=_("Files"))
    def files_link(self, obj: CleanupRun) -> SafeString:
        count = getattr(obj, "_files_count", 0)
        url = reverse("admin:cleanup_app_cleanuprunfile_changelist")
        return format_html('<a href="{}?run__id__exact={}">{} file(s)</a>', url, obj.pk, count)


@admin.register(CleanupRunFile)
class CleanupRunFileAdmin(_ReadOnlyAdminMixin, _CleanupRunFileAdminBase):
    list_display = ("id", "file_path", "file_size", "deleted", "quarantined", "run")
    list_filter = ("deleted", "quarantined")
    search_fields = ("file_path",)
    readonly_fields = ("run", "file_path", "file_size", "deleted", "quarantined", "error")

    def get_queryset(self, request: HttpRequest) -> QuerySet[CleanupRunFile]:
        return super().get_queryset(request).select_related("run")
