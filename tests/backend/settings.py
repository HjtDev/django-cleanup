"""Minimal Django settings for this app's own test suite.

Lives in the test tree, not the package — the package must never contain a settings file
(``APP-DESIGN.md`` §7.1). Kept deliberately minimal: if this app's tests only pass with extra
apps installed, it has an undeclared dependency on host configuration.

Modeled on ``../appkit/tests/backend/settings.py``, with points specific to this app:

* ``django.contrib.admin`` (+ ``sessions``/``messages``/``staticfiles``, its own dependencies)
  IS listed here, unlike appkit's settings — this app ships ``admin.py`` registrations that
  Phase 2's own tests exercise through a real Django admin changelist.
* ``INSTALLED_APPS`` lists ``cleanup_app`` BEFORE ``django_cleanup``, deliberately, and this
  ordering is load-bearing: ``django_cleanup``'s own default ``AppConfig``
  (``django_cleanup.apps.CleanupConfig``, ``default = True``, verified against the installed
  9.0.0 source) calls ``cache.prepare(False)`` from its own ``ready()``, and ``prepare()`` is
  non-reentrant (``django_cleanup/cache.py``: ``if FIELDS: return``). Listing it first would be
  exactly the misordering ``docs/CONTRACT.md`` §9.2 has ``cleanup_app.apps.CleanupAppConfig
  .ready()`` raise ``ImproperlyConfigured`` for.
* ``MIDDLEWARE`` and ``REST_FRAMEWORK["EXCEPTION_HANDLER"]`` are wired to appkit's,
  non-optionally: ``appkit.E001``/``E002`` are check Errors, so this app's own test settings
  must satisfy appkit's own system checks or ``manage.py check`` fails outright.
* No ``CLEANUP`` dict at all — every key in it is optional with a documented default
  (``cleanup_app/conf.py``), and omitting it entirely is what proves that. Individual tests use
  ``override_settings`` where a non-default value matters.
"""

from __future__ import annotations

import os

SECRET_KEY = "test-only-not-a-secret"
DEBUG = False
USE_TZ = True

INSTALLED_APPS = [
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.admin",
    "rest_framework",
    "drf_spectacular",
    "appkit",
    "cleanup_app",
    "django_cleanup",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "appkit.request_id.RequestIDMiddleware",  # before anything that logs
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
]

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

ROOT_URLCONF = "tests.backend.urls"

STATIC_URL = "/static/"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Every value below is overridable by an env var — the literal defaults are what a bare
# `uv run pytest` needs against a Postgres already listening on localhost:5432 with the
# postgres/postgres superuser; ``Makefile``'s `test`/`test-bare` targets export
# POSTGRES_HOST/POSTGRES_PORT to point at docker-compose.test.yml's non-default-port service
# instead (``docs/APP-DESIGN.md`` §7.5: "the connection host comes from an env var so the same
# config works" locally and in CI/Docker).
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.environ.get("POSTGRES_DB", "test_cleanup"),
        "USER": os.environ.get("POSTGRES_USER", "postgres"),
        "PASSWORD": os.environ.get("POSTGRES_PASSWORD", "postgres"),
        "HOST": os.environ.get("POSTGRES_HOST", "localhost"),
        "PORT": os.environ.get("POSTGRES_PORT", "5432"),
    }
}

CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
    }
}

REST_FRAMEWORK = {
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "EXCEPTION_HANDLER": "appkit.exceptions.standard_exception_handler",
    "DEFAULT_PAGINATION_CLASS": "appkit.pagination.DefaultPagination",
    # docs/CONTRACT.md §9.3: the six scope names are literals, not throttle_scope() calls — one
    # of the guide's argument-side names would contain an underscore, which that helper rejects.
    "DEFAULT_THROTTLE_RATES": {
        "cleanup_orphans_list": "60/min",
        "cleanup_orphans_delete": "20/min",
        "cleanup_runs_list": "60/min",
        "cleanup_runs_create": "20/min",
        "cleanup_runs_detail": "60/min",
        "cleanup_summary": "60/min",
    },
}

# COMPONENT_SPLIT_REQUEST is required, not optional (APP-DESIGN.md §12, "Generated types").
SPECTACULAR_SETTINGS = {
    "TITLE": "hjtdev-django-cleanup",
    "VERSION": "0.0.0",  # irrelevant here — the app's real version lives in pyproject.toml
    "COMPONENT_SPLIT_REQUEST": True,
}
