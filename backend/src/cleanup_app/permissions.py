"""This app defines no permission classes of its own — a re-export only.

Every endpoint and every admin surface is gated by ``appkit.permissions.IsAppAdmin``
(``is_authenticated and is_staff``) with zero exceptions (``docs/CONTRACT.md`` §0) — there is no
lesser permission tier to fall back to, so there is no object-level logic to add here (no
per-user ownership exists anywhere in this package; every row belongs to "staff", not to a
particular user). Re-exporting here, rather than every view importing
``appkit.permissions.IsAppAdmin`` directly, keeps ``cleanup_app.permissions`` the one import site
``admin_views.py`` uses — consistent with ``APP-DESIGN.md`` §2's package layout, and so a host or
tool that imports ``cleanup_app.permissions`` by convention doesn't hit an ``ImportError``.
"""

from __future__ import annotations

from appkit.permissions import IsAppAdmin

__all__ = ["IsAppAdmin"]
