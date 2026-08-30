"""``cleanup_app`` — the importable module for the ``hjtdev-django-cleanup`` distribution.

Finds and removes orphaned media files (files on disk that no ``FileField``/``ImageField``
references anymore) in a host Django project, auto-hooks every model with a file field via the
upstream ``django-cleanup`` package (a declared dependency, imported as ``django_cleanup``), and
keeps a full history of every cleanup — automatic (per-save/per-delete, upstream's own signals)
and manual (a full orphan scan, this app's own).

The module is ``cleanup_app``, never ``django_cleanup``: upstream already owns that name in the
same ``site-packages`` this app installs into, so reusing it is a hard import collision, not a
style choice (``docs/CONTRACT.md`` §0). The PyPI distribution is ``hjtdev-django-cleanup``; npm
is ``@hjtdev/django-cleanup``; the GitHub repo stays ``HjtDev/django-cleanup``. Only the local
directory and this importable module are ``cleanup_app``.
"""
