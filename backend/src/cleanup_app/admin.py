"""Jazzmin ``ModelAdmin`` registrations.

Phase 2 registers ``CleanupRun``/``CleanupRunFile`` (history, read-mostly). Phase 5 adds the
orphan-review page itself — an unmanaged ``OrphanFile`` model whose ``changelist_view`` is fully
overridden to call ``services.OrphanScanner.scan()`` instead of querying a database
(``docs/CONTRACT.md`` §6, Option A — chosen over a custom ``admin_views.py`` view because it earns
a real Jazzmin sidebar entry with zero ``JAZZMIN_SETTINGS`` edits from the host).

**Amendment to §6, recorded here and in ``docs/CONTRACT.md``:** the changelist renders this
app's own template (``templates/admin/cleanup_app/orphanfile/change_list.html``), not django
admin's stock ``admin/change_list.html``. That template is driven entirely by a real
``ChangeList`` object — ``cl.result_list``, ``cl.get_queryset()``, ``cl.formset``, filter specs —
all queryset-backed, and ``OrphanFile`` has no table to back one with. Fabricating a fake
``ChangeList`` is exactly the "fighting the framework" case the build guide's own escape hatch
names, for zero visible benefit. The registration itself — the unmanaged model, and the free
Jazzmin sidebar entry that is the entire reason Option A was chosen over Option B — is unchanged;
only the template source is.

Both history registrations below are fully read-only — no add, no change, no delete. History is
written only by ``services.CleanupService``; retention runs through
``CleanupService.purge_history()`` (Phase 3), never a staff user clicking delete on the
changelist, so the record of a real file deletion can never be silently erased from the admin.
``OrphanFile`` is the one exception in this module: it is delete-*capable*, deliberately, since
that is the entire point of this page — but every delete goes through
``services.CleanupService.run()``, never a direct storage call from admin code, behind a
mandatory confirmation step. See ``OrphanFileAdmin.changelist_view`` below.

Suggested Jazzmin icons for ``README.md`` §8 (host adds these to its own ``JAZZMIN_SETTINGS``,
this app never touches that dict itself): ``fas fa-broom`` for ``CleanupRun``, ``fas
fa-file-circle-xmark`` for ``CleanupRunFile``, ``fas fa-trash-can`` for ``OrphanFile``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from appkit.cache import invalidate_namespace
from django.contrib import admin, messages
from django.contrib.admin.helpers import ACTION_CHECKBOX_NAME
from django.core.exceptions import PermissionDenied
from django.db import models
from django.db.models import Count, QuerySet
from django.http import HttpRequest, HttpResponse, HttpResponseRedirect
from django.shortcuts import render
from django.template.defaultfilters import filesizeformat
from django.urls import URLPattern, path, reverse
from django.utils.decorators import method_decorator
from django.utils.html import format_html
from django.utils.safestring import SafeString
from django.utils.translation import gettext_lazy as _
from django.utils.translation import ngettext
from django.views.decorators.csrf import csrf_protect

from cleanup_app.models import CleanupRun, CleanupRunFile
from cleanup_app.services import CleanupService, OrphanScanner

# django-stubs declares admin.ModelAdmin as Generic[_ModelT] for mypy's benefit only — the
# REAL django.contrib.admin.ModelAdmin is not subscriptable at runtime (no __class_getitem__)
# unless a host calls django_stubs_ext.monkeypatch(), which this library cannot assume and must
# not require as a runtime dependency just to satisfy its own type checker. Branching on
# TYPE_CHECKING gives mypy the parameterized base it needs while `class Foo(_CleanupRunAdminBase)`
# subclasses the plain, unsubscripted class at actual import time.
if TYPE_CHECKING:
    _CleanupRunAdminBase = admin.ModelAdmin[CleanupRun]
    _CleanupRunFileAdminBase = admin.ModelAdmin[CleanupRunFile]
    _OrphanFileAdminBase = admin.ModelAdmin["OrphanFile"]
else:
    _CleanupRunAdminBase = admin.ModelAdmin
    _CleanupRunFileAdminBase = admin.ModelAdmin
    _OrphanFileAdminBase = admin.ModelAdmin


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


# --------------------------------------------------------------------------------- OrphanFile


class OrphanFile(models.Model):
    """One row of an ``OrphanScanner.scan()`` result — never a real table.

    ``docs/CONTRACT.md`` §6's sketch, verbatim on the fields. ``default_permissions = ()`` is
    deliberate: every permission check below is overridden on ``OrphanFileAdmin`` directly (down
    to plain ``is_staff``, per §6), so the four ``add``/``change``/``delete``/``view``
    ``Permission`` rows Django would otherwise create per installed host are pure noise — nothing
    ever consults them.
    """

    file_path = models.CharField(_("file path"), max_length=1024, primary_key=True)
    file_size = models.PositiveBigIntegerField(_("file size"))

    class Meta:
        managed = False  # no migration ever creates a table for this — see migration 0002,
        # which records the model in migration STATE (for makemigrations' own bookkeeping)
        # without a CREATE TABLE, exactly as Django's autodetector generates for managed=False.
        app_label = "cleanup_app"
        default_permissions = ()
        verbose_name = _("orphaned file")
        verbose_name_plural = _("orphaned files")

    def __str__(self) -> str:
        return self.file_path


@admin.register(OrphanFile)
class OrphanFileAdmin(_OrphanFileAdminBase):
    """The orphan-review page. ``docs/CONTRACT.md`` §6, Option A, with this module's own
    template-source amendment recorded at the top of this file.

    Every permission check below reduces to plain ``request.user.is_staff`` — including
    ``has_module_permission``, which a bare ``is_staff`` user with no assigned model
    permissions would otherwise fail (Django's default checks ``user.has_module_perms()``,
    which walks the now-empty permission set ``default_permissions = ()`` leaves behind), hiding
    this entire app from the sidebar. ``has_add_permission``/``has_change_permission`` are
    always ``False`` — there is nothing to add, and a scan result cannot be edited, only acted
    on. ``has_delete_permission`` is the one permission this page actually exercises.
    """

    def has_module_permission(self, request: HttpRequest) -> bool:
        return bool(request.user.is_staff)

    def has_view_permission(self, request: HttpRequest, obj: Any = None) -> bool:
        return bool(request.user.is_staff)

    def has_add_permission(self, request: HttpRequest) -> bool:
        return False

    def has_change_permission(self, request: HttpRequest, obj: Any = None) -> bool:
        return False

    def has_delete_permission(self, request: HttpRequest, obj: Any = None) -> bool:
        return bool(request.user.is_staff)

    def get_urls(self) -> list[URLPattern]:
        """Only the changelist route — never Django's default add/change/delete/history routes.

        Those assume a real table: ``_changeform_view`` calls ``self.get_object()`` (a
        ``QuerySet.get()`` against ``OrphanFile.objects`` — which has no table to query) *before*
        its own permission check, so a staff user simply guessing
        ``.../orphanfile/<path>/change/`` would hit a database error instead of a clean 404/403.
        Restricting the URLconf to only the changelist is what keeps this registration safe.
        """
        app_label, model_name = self.model._meta.app_label, self.model._meta.model_name
        return [
            path(
                "",
                self.admin_site.admin_view(self.changelist_view),
                name=f"{app_label}_{model_name}_changelist",
            ),
        ]

    @method_decorator(csrf_protect)
    def changelist_view(
        self, request: HttpRequest, extra_context: dict[str, Any] | None = None
    ) -> HttpResponse:
        """Dispatches on method/action. A bare ``GET`` — with any query string, including one
        engineered to look like a delete request — only ever renders the current scan; it never
        deletes, never busts the cache, never writes a ``CleanupRun`` row. Only a ``POST`` with
        ``action=delete`` **and** ``confirm=yes`` reaches ``CleanupService.run()``.

        ``self.admin_site.admin_view(...)`` (wrapping this view in ``get_urls()`` above) already
        gates every request on ``request.user.is_active and .is_staff`` — the same check the
        history admins get automatically from being registered on ``AdminSite`` at all — and
        redirects an unauthenticated or non-staff request to the login page. The explicit
        ``has_view_permission`` check below is defence-in-depth for a direct call to this method,
        and is what ``docs/CONTRACT.md`` §6 names explicitly.
        """
        if not self.has_view_permission(request):
            raise PermissionDenied

        if request.method == "POST":
            action = request.POST.get("action")
            if action == "rescan":
                return self._handle_rescan(request)
            if action == "delete":
                return self._handle_delete(request)

        return self._render_changelist(request)

    # ----------------------------------------------------------------------------- POST actions

    def _handle_rescan(self, request: HttpRequest) -> HttpResponse:
        invalidate_namespace("cleanup")
        messages.success(request, _("Orphan scan cache cleared — results refreshed."))
        return self._redirect_to_changelist()

    def _handle_delete(self, request: HttpRequest) -> HttpResponse:
        if not self.has_delete_permission(request):
            raise PermissionDenied

        selected = request.POST.getlist(ACTION_CHECKBOX_NAME)
        validated = self._validate_selection(request, selected)
        if validated is None:
            return self._redirect_to_changelist()

        if request.POST.get("confirm") != "yes":
            return self._render_delete_confirmation(request, validated)

        # The one call in this module that ever removes a file, and it never touches storage
        # directly — CleanupService.run() is what applies the grace period, exclude patterns,
        # and record-before-delete rails (already satisfied by _validate_selection reusing the
        # same scan snapshot those rails were applied to build) and record-before-delete
        # (services._process_candidates writes the CleanupRunFile row before any delete attempt).
        run = CleanupService.run(
            trigger=CleanupRun.Trigger.MANUAL,
            file_paths=list(validated.keys()),
            initiated_by=cast("Any", request.user),
        )
        # Belt-and-braces, same reasoning as admin_views.OrphanDeleteView: CleanupService.run()
        # already invalidates internally once it actually deletes anything, but this call is the
        # caller-visible boundary for THIS view, independent of that internal detail.
        invalidate_namespace("cleanup")

        self._message_run_outcome(request, run)
        return self._redirect_to_changelist()

    # -------------------------------------------------------------------------------- rendering

    def _render_changelist(self, request: HttpRequest) -> HttpResponse:
        scan_result = OrphanScanner.scan()
        context = {
            **self.admin_site.each_context(request),
            "title": self.model._meta.verbose_name_plural,
            "opts": self.model._meta,
            "files": scan_result.files,
            "total_size": scan_result.total_size,
            "files_scanned": scan_result.files_scanned,
            "truncated": scan_result.truncated,
            "action_checkbox_name": ACTION_CHECKBOX_NAME,
            "has_delete_permission": self.has_delete_permission(request),
        }
        return render(request, "admin/cleanup_app/orphanfile/change_list.html", context)

    def _render_delete_confirmation(
        self, request: HttpRequest, validated: dict[str, int]
    ) -> HttpResponse:
        context = {
            **self.admin_site.each_context(request),
            "title": _("Are you sure?"),
            "opts": self.model._meta,
            "files": [{"path": path_, "size": size} for path_, size in validated.items()],
            "total_size": sum(validated.values()),
            "selected_paths": list(validated.keys()),
            "action_checkbox_name": ACTION_CHECKBOX_NAME,
        }
        return render(request, "admin/cleanup_app/orphanfile/delete_confirmation.html", context)

    # --------------------------------------------------------------------------------- helpers

    def _validate_selection(
        self, request: HttpRequest, selected: list[str]
    ) -> dict[str, int] | None:
        """Re-validates every selected path against the *current* ``OrphanScanner.scan()``
        snapshot — the same rule ``serializers.OrphanDeleteRequestSerializer.validate_file_paths``
        enforces for the API — so a form value tampered with client-side (or simply stale against
        a file that stopped being an orphan between page-load and submit) can never reach
        ``CleanupService``. Rejects the *entire* request on any unknown path rather than silently
        dropping it: a partial, surprise-shaped delete is worse than making the staff user rescan
        and reselect. Returns ``None`` (having already queued an error message) on rejection,
        otherwise ``{path: size}`` for exactly the requested paths.
        """
        if not selected:
            messages.error(request, _("No files were selected."))
            return None

        snapshot = OrphanScanner.scan()
        known = {f.path: f.size for f in snapshot.files}
        unknown = [path_ for path_ in selected if path_ not in known]
        if unknown:
            messages.error(
                request,
                _(
                    "These are no longer valid orphan candidates (already deleted, referenced "
                    "again, or excluded) — rescan and try again: %(paths)s"
                )
                % {"paths": ", ".join(unknown)},
            )
            return None

        return {path_: known[path_] for path_ in selected}

    def _message_run_outcome(self, request: HttpRequest, run: CleanupRun) -> None:
        if run.files_deleted:
            messages.success(
                request,
                ngettext(
                    "Deleted %(count)d file, freeing %(bytes)s.",
                    "Deleted %(count)d files, freeing %(bytes)s.",
                    run.files_deleted,
                )
                % {"count": run.files_deleted, "bytes": filesizeformat(run.bytes_freed)},
            )
        if run.files_failed:
            messages.warning(
                request,
                ngettext(
                    "%(count)d file could not be deleted — see the cleanup run history for "
                    "details.",
                    "%(count)d files could not be deleted — see the cleanup run history for "
                    "details.",
                    run.files_failed,
                )
                % {"count": run.files_failed},
            )

    def _redirect_to_changelist(self) -> HttpResponseRedirect:
        return HttpResponseRedirect(reverse("admin:cleanup_app_orphanfile_changelist"))
