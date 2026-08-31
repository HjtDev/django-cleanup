"""DRF serializers backing ``urls_admin.py``'s endpoints.

``docs/CONTRACT.md`` §4's six admin-only endpoints. Every field list is explicit — never
``fields = "__all__"`` (``APP-DESIGN.md`` §7's convention: an explicit list is what keeps a new
model field from silently reaching the API before someone decides it should).
"""

from __future__ import annotations

from typing import Any, ClassVar

from rest_framework import serializers

from cleanup_app.models import CleanupRun, CleanupRunFile
from cleanup_app.services import OrphanFileInfo, OrphanScanner

__all__ = [
    "CleanupRunDetailSerializer",
    "CleanupRunFileSerializer",
    "CleanupRunSerializer",
    "CleanupSummarySerializer",
    "CleanupTriggerRequestSerializer",
    "OrphanDeleteRequestSerializer",
    "OrphanFileSerializer",
]


class OrphanFileSerializer(serializers.Serializer[OrphanFileInfo]):
    """Serializes ``services.OrphanFileInfo`` — a frozen dataclass, not a model — for
    ``GET /orphans/``. ``docs/CONTRACT.md`` §4's frozen item shape: ``{file_path, file_size,
    modified_at}``, no ``file_url`` (``file_path`` is already storage-relative, never absolute —
    ``services._walk`` never yields anything else — so there is no ``MEDIA_ROOT`` leak to guard
    against).
    """

    file_path = serializers.CharField(source="path", read_only=True)
    file_size = serializers.IntegerField(source="size", read_only=True)
    modified_at = serializers.DateTimeField(read_only=True)


class OrphanDeleteRequestSerializer(serializers.Serializer[Any]):
    """Validates ``POST /orphans/delete/``'s ``{"file_paths": [...]}`` body against the
    *current* cached ``OrphanScanner`` snapshot — the rail that keeps an arbitrary client-supplied
    path from ever reaching ``CleanupService`` (``docs/CONTRACT.md`` §4: "never accepts an
    arbitrary client-supplied path").
    """

    file_paths = serializers.ListField(
        child=serializers.CharField(max_length=1024), allow_empty=False
    )

    def validate_file_paths(self, value: list[str]) -> list[str]:
        # OrphanScanner.scan() is wrapped in appkit.cache.cached_call — this is a cache hit in
        # the common case (GET /orphans/ already populated it), never a second storage walk just
        # to validate a delete request.
        snapshot = OrphanScanner.scan()
        known = {f.path for f in snapshot.files}
        unknown = [path for path in value if path not in known]
        if unknown:
            raise serializers.ValidationError(
                f"Not present in the current orphan snapshot: {unknown!r}"
            )
        return value


class CleanupRunSerializer(serializers.ModelSerializer[CleanupRun]):
    """Read-only — every field on ``CleanupRun`` is server-computed; nothing here is ever
    client-writable directly (``POST /runs/`` goes through ``CleanupTriggerRequestSerializer``
    instead).
    """

    initiated_by: serializers.PrimaryKeyRelatedField[Any] = serializers.PrimaryKeyRelatedField(
        read_only=True
    )

    class Meta:
        model = CleanupRun
        fields: ClassVar[list[str]] = [
            "id",
            "status",
            "trigger",
            "dry_run",
            "initiated_by",
            "started_at",
            "finished_at",
            "files_scanned",
            "files_deleted",
            "files_failed",
            "bytes_freed",
            "error",
        ]
        read_only_fields = fields


class CleanupRunFileSerializer(serializers.ModelSerializer[CleanupRunFile]):
    class Meta:
        model = CleanupRunFile
        fields: ClassVar[list[str]] = [
            "id",
            "file_path",
            "file_size",
            "deleted",
            "quarantined",
            "error",
        ]
        read_only_fields = fields


class CleanupRunDetailSerializer(CleanupRunSerializer):
    """``GET /runs/{id}/`` — the list serializer plus its ``CleanupRunFile`` rows."""

    files = CleanupRunFileSerializer(many=True, read_only=True)

    class Meta(CleanupRunSerializer.Meta):
        fields: ClassVar[list[str]] = [*CleanupRunSerializer.Meta.fields, "files"]
        read_only_fields = fields


class CleanupTriggerRequestSerializer(serializers.Serializer[Any]):
    """``POST /runs/``'s request body — the only client-writable field for a triggered run."""

    dry_run = serializers.BooleanField(required=False, default=False)


class CleanupSummarySerializer(serializers.Serializer[dict[str, Any]]):
    """Response shape for ``GET /summary/`` — used only for ``@extend_schema``'s declared
    response type; the view builds this dict itself rather than instantiating this serializer
    against a model instance.
    """

    total_runs = serializers.IntegerField(read_only=True)
    files_deleted_total = serializers.IntegerField(read_only=True)
    bytes_freed_total = serializers.IntegerField(read_only=True)
    last_run_at = serializers.DateTimeField(read_only=True, allow_null=True)
    last_run_status = serializers.CharField(read_only=True, allow_null=True)

    def create(self, validated_data: dict[str, Any]) -> Any:  # pragma: no cover - schema-only
        raise NotImplementedError("CleanupSummarySerializer is response-shape-only.")

    def update(self, instance: Any, validated_data: dict[str, Any]) -> Any:  # pragma: no cover
        raise NotImplementedError("CleanupSummarySerializer is response-shape-only.")
