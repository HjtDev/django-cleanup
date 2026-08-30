"""Settings access layer for this app's ``CLEANUP`` settings dict.

Every module in this package reads its configuration through :func:`get_setting`, never a
scattered ``getattr(settings, ...)`` call (``APP-DESIGN.md`` §3.5) — so a host that omits an
optional key gets this app's documented default instead of an ``AttributeError`` deep in a
service call.

Thirteen keys, all optional at the Python level (``docs/CONTRACT.md`` §5)::

    CLEANUP = {
        "STORAGE_ALIAS": "default",       # which configured storage backend to scan;
                                           # "default" resolves to django's default_storage
        "SCAN_ROOTS": None,               # None = walk the whole storage backend; else a list
                                           # of path prefixes to scope the walk to
        "EXCLUDE_PATTERNS": [],           # fnmatch globs; a matching file is never a candidate
                                           # orphan regardless of reference status
        "GRACE_PERIOD_SECONDS": 3600,     # a file modified more recently than this is never a
                                           # candidate — protects in-progress uploads and files
                                           # referenced by an uncommitted transaction
        "QUARANTINE_DIR": None,           # None = hard delete via storage.delete(); set = move
                                           # the file there instead of deleting
        "MAX_FILES_PER_RUN": 5000,        # caps candidates per scan()/run() call;
                                           # OrphanScanResult.truncated reports whether the cap
                                           # was hit
        "SCAN_CACHE_TIMEOUT": 300,        # seconds the OrphanScanner.scan() snapshot is
                                           # cached — what makes GET /orphans/ pagination never
                                           # re-walk storage per page
        "USE_CELERY": False,              # True makes POST /runs/ enqueue instead of running
                                           # inline, if the celery extra is installed — the view
                                           # checks for celery's presence rather than
                                           # hard-importing it
        "TRACK_AUTO_DELETIONS": True,     # connects the receiver logging what upstream
                                           # django_cleanup deletes on save/delete into
                                           # CleanupRun(trigger="auto") rows
        "HISTORY_RETENTION_DAYS": 90,     # default window for
                                           # CleanupService.purge_history() when
                                           # older_than_days isn't passed
        "AUTO_CONNECT": True,             # whether this app's own AppConfig.ready() calls
                                           # django_cleanup.cache.prepare()/handlers.connect()
                                           # at all
        "SELECT_MODE": False,             # maps to upstream's CleanupSelectedConfig vs.
                                           # CleanupConfig: False = every model with a FileField
                                           # is auto-hooked except those explicitly marked
                                           # cleanup_ignore; True = only models explicitly
                                           # marked cleanup_select are hooked
        "IGNORED_MODELS": [],             # list of "app_label.ModelName" strings — see below
    }

``IGNORED_MODELS`` is protective, not subtractive (``docs/CONTRACT.md`` §5, §9.1): it marks a
model via upstream's ``cleanup.ignore()`` so upstream stops auto-deleting its files on
save/delete, but ``OrphanScanner.build_reference_set()`` still includes that model's currently
referenced files, so a live row's file is never a false-positive orphan. It applies identically
under ``SELECT_MODE=True`` — see :meth:`cleanup_app.apps.CleanupAppConfig.ready`.

Zero ``.env`` keys, required or optional, under any installed extra (``docs/CONTRACT.md`` §5) —
this app configures entirely through ``CLEANUP``.
"""

from __future__ import annotations

from typing import Any, Final

from django.conf import settings

DEFAULTS: Final[dict[str, Any]] = {
    "STORAGE_ALIAS": "default",
    "SCAN_ROOTS": None,
    "EXCLUDE_PATTERNS": [],
    "GRACE_PERIOD_SECONDS": 3600,
    "QUARANTINE_DIR": None,
    "MAX_FILES_PER_RUN": 5000,
    "SCAN_CACHE_TIMEOUT": 300,
    "USE_CELERY": False,
    "TRACK_AUTO_DELETIONS": True,
    "HISTORY_RETENTION_DAYS": 90,
    "AUTO_CONNECT": True,
    "SELECT_MODE": False,
    "IGNORED_MODELS": [],
}


def get_setting(key: str) -> Any:
    """Read a ``CLEANUP`` setting, falling back to this app's documented default."""
    return getattr(settings, "CLEANUP", {}).get(key, DEFAULTS[key])
