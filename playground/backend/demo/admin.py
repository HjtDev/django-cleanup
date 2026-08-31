"""Registers Document/Avatar so their rows are visible and deletable from the admin — deleting
one here is how upstream django_cleanup's own per-delete auto-hook, and this app's
TRACK_AUTO_DELETIONS receiver logging it into a ``CleanupRun(trigger="auto")`` row, get exercised
against a real file on real disk (verification pass A.8 in the plan).
"""

from __future__ import annotations

from django.contrib import admin

from demo.models import Avatar, Document


@admin.register(Document)
class DocumentAdmin(admin.ModelAdmin):
    list_display = ("name", "file")


@admin.register(Avatar)
class AvatarAdmin(admin.ModelAdmin):
    list_display = ("name", "image")
