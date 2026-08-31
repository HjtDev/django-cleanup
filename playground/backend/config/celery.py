"""Celery app for the playground — the ``USE_CELERY`` path docs/CONTRACT.md §8 documents as
optional. Not part of cleanup_app itself; a host wires this exactly the same way for any Celery
app it wants to run.
"""

from __future__ import annotations

import os

from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

app = Celery("playground")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()
