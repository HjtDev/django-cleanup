"""Minimal LOGGING dict builder — playground-only, not part of hjtdev-django-cleanup's own
wiring. Exists so cleanup_app's own logger.warning/logger.exception calls (services.py,
apps.py, tasks.py) are actually visible in `docker compose logs backend`.
"""

from __future__ import annotations

from typing import Any


def build_logging_config(*, debug: bool) -> dict[str, Any]:
    return {
        "version": 1,
        "disable_existing_loggers": False,
        "filters": {
            # appkit.W005: LOGGING must reference this filter somewhere, or request-ID
            # correlation (appkit.request_id.RequestIDMiddleware) never reaches the log line.
            "request_id": {"()": "appkit.request_id.RequestIDFilter"},
        },
        "formatters": {
            "simple": {"format": "%(levelname)s [%(request_id)s] %(name)s: %(message)s"},
        },
        "handlers": {
            "console": {
                "class": "logging.StreamHandler",
                "formatter": "simple",
                "filters": ["request_id"],
            },
        },
        "root": {"handlers": ["console"], "level": "INFO"},
        "loggers": {
            "cleanup_app": {"handlers": ["console"], "level": "DEBUG" if debug else "INFO", "propagate": False},
            "django.request": {"handlers": ["console"], "level": "WARNING", "propagate": False},
        },
    }
