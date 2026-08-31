"""Seeds a deterministic media tree plus the DB rows that make part of it "referenced" —
the ground truth every verification pass in the Phase 7 plan checks the API/admin against.

Writes, under ``MEDIA_ROOT``:

* 2 **referenced** files — a ``demo.Document`` row and a ``demo.Avatar`` row each point at one.
  ``OrphanScanner.build_reference_set()`` must exclude both.
* ``ORPHAN_COUNT`` genuinely **orphaned** files, spread across a few subdirectories (proving the
  recursive walk) and past the grace period (backdated with ``os.utime``) — more than one
  pagination page at the default page size, so page 2 has real data.
* 1 file inside the **grace period** — written with a fresh mtime, must never appear as a
  candidate regardless of reference status.
* 1 file matching ``CLEANUP["EXCLUDE_PATTERNS"]`` (``*.keep``) — backdated same as the orphans,
  so its protection is provably from the exclude pattern, not the grace period.

Idempotent by default (skips if ``demo.Document``/``demo.Avatar`` rows already exist);
``--reset`` wipes ``MEDIA_ROOT``, the demo rows, and all cleanup history first.
"""

from __future__ import annotations

import io
import os
import shutil
import time

from django.conf import settings
from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand, CommandParser
from django.core.files.storage import default_storage

from cleanup_app.conf import get_setting
from cleanup_app.models import CleanupRun
from demo.models import Avatar, Document

ORPHAN_COUNT = 30


def _backdate(name: str, seconds_ago: float) -> None:
    """Sets a file's mtime (and atime) ``seconds_ago`` in the past — real files on real disk,
    via ``storage.path()``, since this playground always runs against ``FileSystemStorage``.
    """
    path = default_storage.path(name)
    when = time.time() - seconds_ago
    os.utime(path, (when, when))


def _make_png_bytes() -> bytes:
    """A real, valid 1x1 PNG — Pillow is a real dependency here (playground/backend/pyproject.toml),
    and ImageField.save() / admin thumbnail rendering both need genuinely decodable image bytes,
    not a stub.
    """
    from PIL import Image

    buffer = io.BytesIO()
    Image.new("RGB", (1, 1), color=(200, 60, 60)).save(buffer, format="PNG")
    return buffer.getvalue()


class Command(BaseCommand):
    help = "Seed a deterministic playground media tree — referenced, orphaned, grace-period, and excluded files."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument(
            "--reset",
            action="store_true",
            help="Wipe MEDIA_ROOT, demo rows, and cleanup history before reseeding.",
        )

    def handle(self, *args: object, **options: object) -> None:
        if options["reset"]:
            self._reset()

        if Document.objects.exists() or Avatar.objects.exists():
            self.stdout.write("demo data already seeded — pass --reset to reseed.")
            return

        grace_period = get_setting("GRACE_PERIOD_SECONDS")
        safely_past_grace = grace_period + 3600  # comfortably past, regardless of setting

        referenced = self._seed_referenced()
        orphans = self._seed_orphans(safely_past_grace)
        grace_file = self._seed_grace_period_file()
        excluded_file = self._seed_excluded_file(safely_past_grace)

        self.stdout.write(
            self.style.SUCCESS(
                f"Seeded: {len(referenced)} referenced, {len(orphans)} orphaned, "
                f"1 grace-period ({grace_file}), 1 excluded ({excluded_file})."
            )
        )

    def _reset(self) -> None:
        Document.objects.all().delete()  # triggers upstream django_cleanup's own file delete
        Avatar.objects.all().delete()
        CleanupRun.objects.all().delete()  # cascades CleanupRunFile
        media_root = settings.MEDIA_ROOT
        if os.path.isdir(media_root):
            # Clears the CONTENTS of MEDIA_ROOT, never MEDIA_ROOT itself — in the containerized
            # playground (docker-compose.yml's named `media` volume) MEDIA_ROOT is a mount
            # point, and shutil.rmtree(media_root) (the first version of this method) failed
            # with "OSError: [Errno 16] Device or resource busy" trying to rmdir it, having
            # already deleted every file underneath — leaving an empty media tree and no
            # reseed, silently, since the exception then aborted before _seed_referenced() ran.
            # A bare host (no mount point) has no such restriction either way, so this fix costs
            # nothing there. See FINDINGS.md.
            for name in os.listdir(media_root):
                path = os.path.join(media_root, name)
                if os.path.isdir(path) and not os.path.islink(path):
                    shutil.rmtree(path)
                else:
                    os.remove(path)
        os.makedirs(media_root, exist_ok=True)

    def _seed_referenced(self) -> list[str]:
        doc = Document(name="Referenced Document")
        doc.file.save("readme.txt", ContentFile(b"This file is referenced by demo.Document.\n"))
        doc.save()

        avatar = Avatar(name="Referenced Avatar")
        avatar.image.save("profile.png", ContentFile(_make_png_bytes()))
        avatar.save()

        return [doc.file.name, avatar.image.name]

    def _seed_orphans(self, seconds_ago: float) -> list[str]:
        names = []
        # Spread across a few directories, including nested ones, so OrphanScanner's recursive
        # _walk() is genuinely exercised, not just a flat listdir().
        dirs = ["orphans", "orphans/2024", "orphans/2024/reports", "uploads/tmp"]
        for i in range(ORPHAN_COUNT):
            directory = dirs[i % len(dirs)]
            name = f"{directory}/orphan-{i:03d}.txt"
            saved = default_storage.save(name, ContentFile(f"orphan file #{i}\n".encode()))
            _backdate(saved, seconds_ago)
            names.append(saved)
        return names

    def _seed_grace_period_file(self) -> str:
        # No backdating — a fresh mtime is the whole point: still inside GRACE_PERIOD_SECONDS.
        return default_storage.save("orphans/fresh-upload.txt", ContentFile(b"just uploaded\n"))

    def _seed_excluded_file(self, seconds_ago: float) -> str:
        name = default_storage.save("orphans/important.keep", ContentFile(b"do not delete\n"))
        _backdate(name, seconds_ago)
        return name
