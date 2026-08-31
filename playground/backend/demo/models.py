"""Throwaway host models with real FileField/ImageField — the two "referenced" files in the
seeded media tree are pointed at from here, so OrphanScanner.build_reference_set() has something
real to protect, and so deleting a row here exercises upstream django_cleanup's own per-delete
auto-hook (and, in turn, cleanup_app's TRACK_AUTO_DELETIONS receiver) end to end.
"""

from __future__ import annotations

from django.db import models


class Document(models.Model):
    name = models.CharField(max_length=255)
    file = models.FileField(upload_to="documents/")

    def __str__(self) -> str:
        return self.name


class Avatar(models.Model):
    name = models.CharField(max_length=255)
    image = models.ImageField(upload_to="avatars/")

    def __str__(self) -> str:
        return self.name
