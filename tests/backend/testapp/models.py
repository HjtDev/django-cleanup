"""Test-only models carrying real ``FileField``/``ImageField`` attributes, standing in for a
host project's own models. ``cleanup_app`` itself ships none (``docs/CONTRACT.md`` §1) — Phase 3's
suite needs some to exercise ``OrphanScanner.build_reference_set()``, the reverse-relation case,
``IGNORED_MODELS``, and upstream ``django_cleanup``'s own auto-hook against something real.
"""

from __future__ import annotations

from django.db import models


class Folder(models.Model):
    """No file fields of its own. ``Document`` below is reachable from here only via a reverse
    FK — proves ``build_reference_set()`` sees files reachable only through a reverse relation,
    since it walks ``apps.get_models()`` directly rather than following relations outward from a
    starting model."""

    name = models.CharField(max_length=100)

    def __str__(self) -> str:
        return self.name


class Document(models.Model):
    folder = models.ForeignKey(Folder, on_delete=models.CASCADE, related_name="documents")
    attachment = models.FileField(upload_to="documents/")

    def __str__(self) -> str:
        return self.attachment.name or ""


class Avatar(models.Model):
    """A real ``ImageField``, not just a ``FileField`` — proves the
    ``isinstance(field, models.FileField)`` walk in ``build_reference_set()`` really covers
    ``ImageField`` (a ``FileField`` subclass) end-to-end, not just structurally."""

    image = models.ImageField(upload_to="avatars/")

    def __str__(self) -> str:
        return self.image.name or ""


class SoftDeletedManager(models.Manager["SoftDeleted"]):
    """Filters out ``is_deleted=True`` rows — the model that fails
    ``OrphanScanner.build_reference_set()`` if it queries through ``.objects``/the default
    manager instead of ``_base_manager``. Django auto-creates an unfiltered ``_base_manager`` for
    any model that doesn't set ``Meta.base_manager_name`` (verified against
    ``django.db.models.options.Options.base_manager``, which falls back to a plain, auto-created
    ``Manager()`` rather than the first declared manager) — so ``_base_manager`` sees this row's
    file even while it's soft-deleted and hidden from ``objects``.
    """

    def get_queryset(self) -> models.QuerySet[SoftDeleted]:
        return super().get_queryset().filter(is_deleted=False)


class SoftDeleted(models.Model):
    file = models.FileField(upload_to="soft-deleted/")
    is_deleted = models.BooleanField(default=False)

    objects: SoftDeletedManager = SoftDeletedManager()

    def __str__(self) -> str:
        return self.file.name or ""


class IgnoredDoc(models.Model):
    """The model ``CLEANUP["IGNORED_MODELS"]`` tests point at — deliberately plain, no
    soft-delete and no reverse-relation trickery, so those tests aren't entangled with either."""

    file = models.FileField(upload_to="ignored/")

    def __str__(self) -> str:
        return self.file.name or ""
