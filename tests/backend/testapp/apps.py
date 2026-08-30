"""``AppConfig`` for the test-only ``testapp`` — real models carrying ``FileField``/``ImageField``
so ``cleanup_app.services.OrphanScanner`` has something real to hook, scan, and reference-check
against. Ships no ``migrations`` package on purpose: Django's test-database creation runs
``migrate --run-syncdb`` for any installed app without one, which is all this needs.
"""

from __future__ import annotations

from django.apps import AppConfig


class TestAppConfig(AppConfig):
    name = "tests.backend.testapp"
    label = "testapp"
    default_auto_field = "django.db.models.BigAutoField"
