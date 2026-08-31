"""Playground settings — Phase 7, docs/APP-DESIGN.md §11.2.

Split into two halves, mirroring ../../appkit/playground/backend/config/settings.py's own
convention:

  1. "HOST BASELINE" — what a fresh Django host already has before any app package is installed.
  2. "CLEANUP_APP WIRING — VERBATIM FROM README.md" — README.md's own "Settings" fence, in that
     fence's own order. If the project doesn't boot with only what's between the banners, that
     gap belongs in FINDINGS.md as a README defect, not silently patched here.

Deliberately does NOT add ``django_cleanup.apps.CleanupConfig`` to ``INSTALLED_APPS`` — proving
this app's own ``AppConfig.ready()`` (Phase 1) drives upstream's cache/handler wiring on its own,
with no explicit host action required.

No reverse proxy sits between the browser and this backend at the HTTP layer: the Next.js app's
`rewrites()` (playground/frontend/next.config.ts) proxy same-origin requests server-side, which
does not forward X-Forwarded-For — so NUM_PROXIES/TRUSTED_PROXY_COUNT stay at 0, not 1. See
FINDINGS.md for why this playground took that shape instead of appkit's own nginx-fronted one.
"""

from __future__ import annotations

from pathlib import Path

from decouple import config

BASE_DIR = Path(__file__).resolve().parent.parent

# ============================================================================================
# HOST BASELINE — what a fresh Django host already has before any app package is installed.
# ============================================================================================

SECRET_KEY = config("SECRET_KEY", default="playground-not-a-secret")
DEBUG = config("DEBUG", default=False, cast=bool)
ALLOWED_HOSTS = config(
    "ALLOWED_HOSTS", default="localhost,127.0.0.1,backend", cast=lambda v: v.split(",")
)

INSTALLED_APPS = [
    "jazzmin",
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "drf_spectacular",
    # appkit is a prerequisite of cleanup_app, not part of its own wiring block below — a real
    # host installs and wires appkit FIRST (per appkit's own README), then adds cleanup_app on
    # top. Omitting this (as an earlier draft of this file did) left REST_FRAMEWORK on DRF's
    # stock exception handler, so IsAppAdmin's 403 came back as DRF's bare {"detail": ...} shape
    # instead of appkit's error envelope — caught live by curl, not by any unit test, since every
    # existing test mocks the exception handler via override_settings. See FINDINGS.md.
    "appkit",
    "demo",
    # ---- CLEANUP_APP WIRING adds "cleanup_app" below, per README.md ----
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "appkit.request_id.RequestIDMiddleware",  # right after SecurityMiddleware, per appkit's README
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
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

ROOT_URLCONF = "config.urls"
ASGI_APPLICATION = "config.asgi.application"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": config("POSTGRES_DB", default="playground"),
        "USER": config("POSTGRES_USER", default="playground"),
        "PASSWORD": config("POSTGRES_PASSWORD", default="playground"),
        "HOST": config("POSTGRES_HOST", default="db"),
        "PORT": config("POSTGRES_PORT", default="5432"),
    }
}

# A real cache backend, not locmem — OrphanScanner.scan()'s cached_call snapshot and
# CachedListMixin's own list cache both need one shared across the backend and celery worker
# processes to mean anything here.
CACHES = {
    "default": {
        "BACKEND": "django_redis.cache.RedisCache",
        "LOCATION": config("REDIS_URL", default="redis://redis:6379/0"),
        "OPTIONS": {"CLIENT_CLASS": "django_redis.client.DefaultClient"},
    }
}

CELERY_BROKER_URL = config("REDIS_URL", default="redis://redis:6379/0")
CELERY_RESULT_BACKEND = config("REDIS_URL", default="redis://redis:6379/0")
CELERY_TASK_ALWAYS_EAGER = False

AUTH_USER_MODEL = "auth.User"

MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"
STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

USE_TZ = True
TIME_ZONE = "UTC"

CSRF_COOKIE_HTTPONLY = False  # must stay JS-readable — the frontend sends it as a header
SESSION_COOKIE_HTTPONLY = True

# The Next.js dev server proxies same-origin (localhost:3000 -> backend:8000 server-side), so
# the browser's own origin for CSRF purposes is localhost:3000, not this container.
CSRF_TRUSTED_ORIGINS = config(
    "CSRF_TRUSTED_ORIGINS",
    default="http://localhost:3000",
    cast=lambda v: v.split(","),
)

REST_FRAMEWORK: dict[str, object] = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework.authentication.SessionAuthentication",
        "rest_framework.authentication.BasicAuthentication",
    ],
    "DEFAULT_THROTTLE_CLASSES": ["rest_framework.throttling.ScopedRateThrottle"],
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    # appkit's own required wiring (appkit.E002/its README's "Settings" section) — every
    # IsAppAdmin rejection and every ValidationError this app raises renders through this, not
    # DRF's stock {"detail": ...} shape.
    "EXCEPTION_HANDLER": "appkit.exceptions.standard_exception_handler",
    "DEFAULT_PAGINATION_CLASS": "appkit.pagination.DefaultPagination",
    # No untrusted reverse proxy sits between the browser and this backend: the Next.js app's
    # server-side rewrites() (playground/frontend/next.config.ts) do not forward
    # X-Forwarded-For, so there are zero trusted hops to skip — matches APPKIT["TRUSTED_PROXY_
    # COUNT"] below (appkit.W006 fires on any disagreement between the two).
    "NUM_PROXIES": 0,
    # docs/CONTRACT.md §9.3: literal scope names, matching cleanup_app's own six throttle_scope
    # values exactly — a host declares its own DEFAULT_THROTTLE_RATES entry per scope this app
    # uses, same as README.md's "Settings" section documents.
    "DEFAULT_THROTTLE_RATES": {
        "cleanup_orphans_list": "60/min",
        "cleanup_orphans_delete": "20/min",
        "cleanup_runs_list": "60/min",
        "cleanup_runs_trigger": "20/min",
        "cleanup_runs_retrieve": "60/min",
        "cleanup_summary": "60/min",
    },
}

APPKIT = {
    "TRUSTED_PROXY_COUNT": 0,
}

SPECTACULAR_SETTINGS = {
    "TITLE": "cleanup_app playground",
    "VERSION": "0.1.0",
    "COMPONENT_SPLIT_REQUEST": True,
}

JAZZMIN_SETTINGS = {
    "site_title": "cleanup_app playground",
    "site_header": "Playground",
    "site_brand": "cleanup_app",
    "welcome_sign": "Media Cleanup Playground",
    # README.md §8's suggested icons (backend/src/cleanup_app/admin.py's own docstring) — this
    # is the live check that the snippet Phase 8 ships is actually copy-pasteable.
    "icons": {
        "cleanup_app.CleanupRun": "fas fa-broom",
        "cleanup_app.CleanupRunFile": "fas fa-file-circle-xmark",
        "cleanup_app.OrphanFile": "fas fa-trash-can",
        "demo.Document": "fas fa-file",
        "demo.Avatar": "fas fa-image",
    },
}

# ============================================================================================
# CLEANUP_APP WIRING — VERBATIM FROM README.md's "Installation — backend" / settings guidance.
# Do not reorder, merge, or "improve" anything between these banners. See module docstring.
# ============================================================================================

INSTALLED_APPS += ["cleanup_app"]
# django_cleanup is deliberately NOT listed here — not "django_cleanup" and not
# "django_cleanup.apps.CleanupConfig". This is the specific thing Phase 7's brief asks the
# playground to prove: cleanup_app.apps.CleanupAppConfig.ready() (Phase 1) calls
# django_cleanup.cache.prepare()/handlers.connect() directly via plain Python import, so
# upstream's own auto-hook works with zero INSTALLED_APPS entry of its own. Listing
# "django_cleanup" here would trigger ITS OWN default AppConfig
# (django_cleanup.apps.CleanupConfig, default=True) via Django's app-loading machinery, which
# would call cache.prepare() first and make this app's own AUTO_CONNECT wiring a no-op — see
# cleanup_app/apps.py's own ImproperlyConfigured guard against exactly that ordering hazard.

CLEANUP = {
    "GRACE_PERIOD_SECONDS": 300,  # short enough to demo, long enough the freshly-seeded file
    # is reliably protected across the seed->scan window
    "EXCLUDE_PATTERNS": ["*.keep"],
    "MAX_FILES_PER_RUN": 5000,
    "SCAN_CACHE_TIMEOUT": 30,  # short — this playground deliberately re-scans often
    "USE_CELERY": config("CLEANUP_USE_CELERY", default=False, cast=bool),
    "TRACK_AUTO_DELETIONS": True,
    "HISTORY_RETENTION_DAYS": 90,
    "AUTO_CONNECT": True,
}

# ============================================================================================
# END CLEANUP_APP WIRING
# ============================================================================================

from config.logging import build_logging_config  # noqa: E402

LOGGING = build_logging_config(debug=DEBUG)
