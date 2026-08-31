"""Custom admin-dashboard API views.

``docs/CONTRACT.md`` §4's six admin-only DRF endpoints — every one gated by
``cleanup_app.permissions.IsAppAdmin`` (no fallback tier, ``docs/CONTRACT.md`` §0) and carrying a
``cleanup_``-prefixed ``throttle_scope`` literal (``docs/CONTRACT.md`` §4/§9.3: literals, not
``appkit.throttling.throttle_scope()`` calls — that helper rejects any argument containing ``_``,
and every scope name here has one).

Phase 5 may add the ``docs/CONTRACT.md`` §6 Option B fallback view here, reached through
``CleanupRunAdmin.get_urls()``, only if Option A (an unmanaged model in ``admin.py``) turns out
not to work cleanly against Django admin's changelist internals.
"""

from __future__ import annotations

import importlib.util
from typing import Any, cast

from appkit.cache import cache_endpoint, invalidate_namespace
from appkit.mixins import CachedListMixin
from appkit.pagination import DefaultPagination
from django.db.models import Count, QuerySet, Sum
from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework import generics, status
from rest_framework.exceptions import ValidationError
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from cleanup_app import conf
from cleanup_app.models import CleanupRun
from cleanup_app.permissions import IsAppAdmin
from cleanup_app.serializers import (
    CleanupRunDetailSerializer,
    CleanupRunSerializer,
    CleanupSummarySerializer,
    CleanupTriggerRequestSerializer,
    OrphanDeleteRequestSerializer,
    OrphanFileSerializer,
)
from cleanup_app.services import CleanupService, OrphanScanner
from cleanup_app.tasks import run_cleanup_run

__all__ = [
    "CleanupRunDetailView",
    "CleanupRunListCreateView",
    "CleanupSummaryView",
    "OrphanDeleteView",
    "OrphanFileListView",
    "OrphanScanPagination",
]


class OrphanScanPagination(DefaultPagination):
    """Adds ``total_size``/``files_scanned``/``truncated`` as extra top-level keys alongside the
    standard ``count``/``next``/``previous``/``results`` — ``docs/CONTRACT.md`` §9.6 says these
    exist so ``MAX_FILES_PER_RUN`` truncation is visible to the API response, but never says
    where; this is the resolution flagged in the plan. The per-item shape ``docs/CONTRACT.md``
    §4 freezes (``{file_path, file_size, modified_at}``) is untouched.
    """

    def paginate_queryset(
        self, queryset: Any, request: Request, view: Any = None
    ) -> list[Any] | None:
        page: list[Any] | None = super().paginate_queryset(queryset, request, view=view)
        # OrphanFileListView.get_queryset() stashes the full OrphanScanResult on the view before
        # this runs — read it back here rather than re-scanning, since the paginated `data`
        # (`page`) is only the OrphanFileInfo objects, not the result's own aggregate fields.
        self.scan_result = getattr(view, "scan_result", None)
        return page

    def get_paginated_response(self, data: Any) -> Response:
        response = super().get_paginated_response(data)
        scan_result = getattr(self, "scan_result", None)
        if scan_result is not None:
            response.data["total_size"] = scan_result.total_size
            response.data["files_scanned"] = scan_result.files_scanned
            response.data["truncated"] = scan_result.truncated
        return response

    def get_paginated_response_schema(self, schema: Any) -> dict[str, Any]:
        response_schema = super().get_paginated_response_schema(schema)
        response_schema["properties"]["total_size"] = {
            "type": "integer",
            "example": 123456,
        }
        response_schema["properties"]["files_scanned"] = {
            "type": "integer",
            "example": 42,
        }
        response_schema["properties"]["truncated"] = {
            "type": "boolean",
            "example": False,
        }
        return response_schema


@extend_schema_view(
    # Keyed by HTTP method ("get"), not the mixin action name ("list") — AutoSchema.
    # get_description()/get_summary()/get_tags() resolve the annotated method via
    # `getattr(self.view, getattr(self.view, "action", self.method.lower()))`, and a plain
    # GenericAPIView (as opposed to a ViewSet) has no `.action` attribute, so it falls back to
    # `self.method.lower()` — "get" here, never "list". Verified against the generated
    # schema.yml: `list=extend_schema(...)` silently produced no override at all.
    get=extend_schema(
        summary="List orphaned files",
        description=(
            "Paginated list of files found on the configured storage that no installed "
            "model currently references, served from the cached OrphanScanner snapshot — "
            "a cache miss triggers exactly one scan, a hit never re-scans storage."
        ),
        responses=OrphanFileSerializer,
        tags=["cleanup-admin"],
    )
)
class OrphanFileListView(CachedListMixin, generics.ListAPIView[Any]):
    """``GET /orphans/``. ``CachedListMixin`` must precede ``ListAPIView`` in the MRO (appkit's
    own requirement) so it wraps ``list()``. This is a second, independent cache layer from the
    ``OrphanScanner.scan()`` snapshot itself — one caches "the scan result," this one caches
    "this serialized page of it" (``docs/CONTRACT.md`` §4).
    """

    permission_classes = [IsAppAdmin]  # noqa: RUF012 -- APIView types this as an instance var
    throttle_scope = "cleanup_orphans_list"
    serializer_class = OrphanFileSerializer
    pagination_class = OrphanScanPagination
    cache_namespace = "cleanup"
    cache_timeout = 30
    # A host's own DEFAULT_FILTER_BACKENDS (e.g. DjangoFilterBackend) would choke trying to
    # filter the plain list of OrphanFileInfo objects this view returns — it isn't a queryset.
    filter_backends: list[Any] = []  # noqa: RUF012 -- GenericAPIView types this as an instance var

    def get_queryset(self) -> list[Any]:  # type: ignore[override]
        # This view's data source is a scan snapshot, not a QuerySet — the generic signature
        # ListAPIView inherits from GenericAPIView assumes a QuerySet, but ListModelMixin.list()
        # only ever iterates/paginates/serializes whatever get_queryset() returns, so a plain
        # list works at runtime; only the type is narrower than the declared supertype.
        # Stored on the view (not just returned) so OrphanScanPagination can read the result's
        # aggregate fields back off `view.scan_result` from inside paginate_queryset().
        self.scan_result = OrphanScanner.scan()
        return self.scan_result.files


class OrphanDeleteView(APIView):
    """``POST /orphans/delete/``. Order is load-bearing per ``docs/CONTRACT.md`` §4: validate
    via the serializer **first** (rejects any path absent from the current snapshot), then
    ``CleanupService.run()``, then ``invalidate_namespace("cleanup")`` **last** — so a rejected
    request never busts a good snapshot. ``CleanupService.run()`` already invalidates internally
    (``services.py``'s own tail) — this call is deliberate belt-and-braces for the same reason
    that comment gives: this view is the "did the caller-visible cache line up" boundary, not
    just the storage-side one.
    """

    permission_classes = [IsAppAdmin]  # noqa: RUF012 -- APIView types this as an instance var
    throttle_scope = "cleanup_orphans_delete"

    @extend_schema(
        summary="Delete orphaned files",
        description=(
            "Deletes the given files, each of which must be present in the current orphan "
            "snapshot. Rejects (400) any path not found there — never accepts an arbitrary "
            "client-supplied path."
        ),
        request=OrphanDeleteRequestSerializer,
        responses={202: CleanupRunSerializer},
        tags=["cleanup-admin"],
    )
    def post(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        serializer = OrphanDeleteRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        run = CleanupService.run(
            trigger=CleanupRun.Trigger.API,
            file_paths=serializer.validated_data["file_paths"],
            initiated_by=cast("Any", request.user),
        )
        invalidate_namespace("cleanup")

        return Response(CleanupRunSerializer(run).data, status=status.HTTP_202_ACCEPTED)


@extend_schema_view(
    # Keyed by HTTP method, not mixin action name — see OrphanFileListView's decorator comment
    # above for why ("list"/"create" are silently ignored on a plain GenericAPIView).
    get=extend_schema(
        summary="List cleanup runs",
        description="Paginated CleanupRun history, optionally filtered by status/trigger.",
        responses=CleanupRunSerializer,
        tags=["cleanup-admin"],
    ),
    post=extend_schema(
        summary="Trigger a cleanup run",
        description=(
            "If CLEANUP['USE_CELERY'] is on and celery is importable: enqueues the run and "
            "returns 202 with a PENDING CleanupRun. Otherwise runs synchronously and returns "
            "200 with the finished run."
        ),
        request=CleanupTriggerRequestSerializer,
        responses={200: CleanupRunSerializer, 202: CleanupRunSerializer},
        tags=["cleanup-admin"],
    ),
)
class CleanupRunListCreateView(generics.ListCreateAPIView[CleanupRun]):
    """``GET|POST /runs/``. One URL, two throttle scopes (decision 7 in the plan):
    ``throttle_scope`` stays the class attribute ``ListCreateAPIView``/appkit's ``W004`` check
    can see (it structurally can't see a scope assigned at request time), and ``get_throttles()``
    swaps in the POST-only scope. A local test in ``test_admin_views.py`` asserts all six scope
    literals exist in ``DEFAULT_THROTTLE_RATES`` to close the gap ``W004``'s own docstring admits
    it can't cover.
    """

    permission_classes = [IsAppAdmin]  # noqa: RUF012 -- APIView types this as an instance var
    throttle_scope = "cleanup_runs_list"
    pagination_class = DefaultPagination
    queryset = CleanupRun.objects.select_related("initiated_by").order_by("-started_at")

    def get_serializer_class(self) -> type[Any]:
        if self.request.method == "POST":
            return CleanupTriggerRequestSerializer
        return CleanupRunSerializer

    def get_throttles(self) -> list[Any]:
        if self.request.method == "POST":
            self.throttle_scope = "cleanup_runs_trigger"
        return super().get_throttles()

    def get_queryset(self) -> QuerySet[CleanupRun]:
        queryset = super().get_queryset()

        status_param = self.request.query_params.get("status")
        if status_param:
            if status_param not in CleanupRun.Status.values:
                raise ValidationError({"status": f"Unknown status {status_param!r}."})
            queryset = queryset.filter(status=status_param)

        trigger_param = self.request.query_params.get("trigger")
        if trigger_param:
            if trigger_param not in CleanupRun.Trigger.values:
                raise ValidationError({"trigger": f"Unknown trigger {trigger_param!r}."})
            queryset = queryset.filter(trigger=trigger_param)

        return queryset

    def create(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        dry_run: bool = serializer.validated_data["dry_run"]

        use_celery = conf.get_setting("USE_CELERY")
        # importlib.util.find_spec, never a module-scope `import celery` — a bare install (no
        # `celery` extra) must still be able to import this module without error.
        celery_available = importlib.util.find_spec("celery") is not None

        if use_celery and celery_available:
            run = CleanupRun.objects.create(
                trigger=CleanupRun.Trigger.API,
                dry_run=dry_run,
                initiated_by=cast("Any", request.user),
            )
            run_cleanup_run.delay(run.pk)
            return Response(CleanupRunSerializer(run).data, status=status.HTTP_202_ACCEPTED)

        run = CleanupService.run(
            trigger=CleanupRun.Trigger.API,
            dry_run=dry_run,
            initiated_by=cast("Any", request.user),
        )
        return Response(CleanupRunSerializer(run).data, status=status.HTTP_200_OK)


@extend_schema_view(
    # Keyed by HTTP method, not mixin action name — see OrphanFileListView's decorator comment.
    get=extend_schema(
        summary="Retrieve a cleanup run",
        description="A single CleanupRun plus its CleanupRunFile rows.",
        responses=CleanupRunDetailSerializer,
        tags=["cleanup-admin"],
    )
)
class CleanupRunDetailView(generics.RetrieveAPIView[CleanupRun]):
    """``GET /runs/{id}/``. ``select_related``/``prefetch_related`` up front — no N+1 regardless
    of how many ``CleanupRunFile`` rows the run has.
    """

    permission_classes = [IsAppAdmin]  # noqa: RUF012 -- APIView types this as an instance var
    throttle_scope = "cleanup_runs_retrieve"
    serializer_class = CleanupRunDetailSerializer
    queryset = CleanupRun.objects.select_related("initiated_by").prefetch_related("files")


class CleanupSummaryView(APIView):
    """``GET /summary/``. ``per_user`` is left at ``cache_endpoint``'s ``True`` default —
    appkit's own docstring calls ``per_user=False`` on a permission-gated view an authorization
    bypass, and this view is gated by ``IsAppAdmin``.
    """

    permission_classes = [IsAppAdmin]  # noqa: RUF012 -- APIView types this as an instance var
    throttle_scope = "cleanup_summary"

    @extend_schema(
        summary="Cleanup history summary",
        description="Aggregate totals across every CleanupRun, cached short-lived.",
        responses=CleanupSummarySerializer,
        tags=["cleanup-admin"],
    )
    @cache_endpoint(namespace="cleanup", timeout=30)
    def get(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        aggregates = CleanupRun.objects.aggregate(
            total_runs=Count("id"),
            files_deleted_total=Sum("files_deleted"),
            bytes_freed_total=Sum("bytes_freed"),
        )
        last_run = CleanupRun.objects.order_by("-started_at").first()

        data = {
            "total_runs": aggregates["total_runs"] or 0,
            "files_deleted_total": aggregates["files_deleted_total"] or 0,
            "bytes_freed_total": aggregates["bytes_freed_total"] or 0,
            "last_run_at": last_run.started_at if last_run else None,
            "last_run_status": last_run.status if last_run else None,
        }
        return Response(CleanupSummarySerializer(data).data)
