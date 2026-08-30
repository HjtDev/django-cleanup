"""This app's ``AppConfig`` — wires upstream ``django_cleanup``'s auto-hook cache and signal
handlers from inside :meth:`CleanupAppConfig.ready`, so a host only ever adds ``cleanup_app`` to
``INSTALLED_APPS`` and never has to also list ``django_cleanup.apps.CleanupConfig`` itself.

This app defines no models of its own with file fields, so there is no ``default_auto_field``
concern beyond the standard one set below for :mod:`cleanup_app.models`'s own tables.
"""

from __future__ import annotations

import logging

from django.apps import AppConfig
from django.core.exceptions import ImproperlyConfigured
from django.utils.translation import gettext_lazy as _

logger = logging.getLogger(__name__)


class CleanupAppConfig(AppConfig):
    name = "cleanup_app"
    verbose_name = _("Media Cleanup")
    default_auto_field = "django.db.models.BigAutoField"

    def ready(self) -> None:
        """Wire upstream ``django_cleanup``'s cache and signal handlers, unless a host opted out
        via ``CLEANUP["AUTO_CONNECT"] = False``.

        Calling ``django_cleanup.cache.prepare()`` and ``django_cleanup.handlers.connect()``
        unconditionally from here is safe, verified against ``django-cleanup`` 9.0.0's actual
        source (``docs/CONTRACT.md`` §9.2, §11) rather than assumed from documentation:

        * ``handlers.connect()`` guards every ``post_init``/``pre_save``/``post_save``/
          ``post_delete`` connection with a ``dispatch_uid`` derived from the model name, so a
          second call — from this app, from a host that also lists
          ``django_cleanup.apps.CleanupConfig``, or from Django's autoreloader — is a no-op, not
          a duplicate-signal bug.
        * ``cache.prepare(select_mode)`` returns immediately if its internal ``FIELDS`` cache is
          already populated (``django_cleanup/cache.py``: ``if FIELDS: return``) — it is
          explicitly non-reentrant.

        That non-reentrance is also the hazard this method guards against, not just tolerates:
        if a host lists ``django_cleanup`` (with its own default ``CleanupConfig``) *before*
        ``cleanup_app`` in ``INSTALLED_APPS``, upstream's own ``ready()`` populates ``FIELDS``
        first, and this app's later ``prepare(SELECT_MODE)`` call becomes a silent no-op —
        ``IGNORED_MODELS`` and ``SELECT_MODE`` would then never take effect, with no error
        raised anywhere. Rather than accept that silent failure (which the build guide's own
        prompt assumed was harmless), this method raises :class:`ImproperlyConfigured` the
        moment it detects the cache was already populated *and* either setting is non-default —
        there is nothing to protect if both are still at their defaults, so that combination is
        allowed through.

        With zero ``FileField`` models on a host, ``django_cleanup.cache.FIELDS`` simply stays
        empty: ``prepare()`` iterates every installed model, adds nothing, and ``connect()``
        iterates ``cache.cleanup_models()`` (driven by that same empty ``FIELDS``), connecting
        nothing. Neither call raises. Confirmed by reading ``django_cleanup/cache.py`` and
        ``django_cleanup/handlers.py`` directly, not assumed.
        """
        from cleanup_app import conf

        if not conf.get_setting("AUTO_CONNECT"):
            return

        from django.apps import apps as django_apps
        from django_cleanup import cache as cleanup_cache
        from django_cleanup import cleanup, handlers

        select_mode = conf.get_setting("SELECT_MODE")
        ignored_models = conf.get_setting("IGNORED_MODELS")

        if cleanup_cache.FIELDS and (
            select_mode != conf.DEFAULTS["SELECT_MODE"]
            or ignored_models != conf.DEFAULTS["IGNORED_MODELS"]
        ):
            raise ImproperlyConfigured(
                "cleanup_app.AppConfig.ready() found django_cleanup's cache already populated "
                "while CLEANUP['SELECT_MODE'] and/or CLEANUP['IGNORED_MODELS'] is set to a "
                "non-default value. This means django_cleanup.apps.CleanupConfig (or another "
                "app calling django_cleanup.cache.prepare()) ran before cleanup_app in "
                "INSTALLED_APPS, so those settings would silently never take effect — "
                "django_cleanup.cache.prepare() is non-reentrant. Fix: move 'cleanup_app' "
                "before any explicit django_cleanup app config entry in INSTALLED_APPS, or set "
                "CLEANUP['AUTO_CONNECT'] = False and let the host wire django_cleanup itself."
            )

        # IGNORED_MODELS is applied BEFORE cache.prepare() — prepare() reads these markers while
        # building its cache, so applying them after would have no effect (docs/CONTRACT.md
        # §5, §9.2's ordering note).
        for label in ignored_models:
            try:
                model = django_apps.get_model(label)
            except LookupError:
                # A typo'd or not-yet-migrated model name must not break manage.py entirely —
                # log and skip rather than raise, unlike the cache-ordering hazard above, which
                # is a genuine misconfiguration worth failing loudly on.
                logger.warning(
                    "cleanup_app: CLEANUP['IGNORED_MODELS'] names %r, which does not resolve "
                    "to an installed model — skipping.",
                    label,
                )
                continue

            cleanup.ignore(model)

            if select_mode:
                # Upstream's cache.ignore_model() consults ONLY the cleanup_select marker when
                # select_mode=True (django_cleanup/cache.py: `not hasattr(model,
                # get_mangled_select(model))`) — cleanup.ignore() alone does not exempt a model
                # under SELECT_MODE. Without also stripping any select marker, docs/CONTRACT.md
                # §5's "permanently un-hooked regardless of whether something later marks them
                # cleanup_select" would not hold: a model ignored here but later decorated with
                # @cleanup.select elsewhere would become hooked again despite IGNORED_MODELS.
                select_attr = cleanup_cache.get_mangled_select(model)
                if select_attr in model.__dict__:
                    delattr(model, select_attr)

        cleanup_cache.prepare(select_mode)
        handlers.connect()
