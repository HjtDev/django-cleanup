"""This app defines no permission classes of its own.

Every endpoint and every admin surface is gated by ``appkit.permissions.IsAppAdmin``
(``is_authenticated and is_staff``) with zero exceptions (``docs/CONTRACT.md`` §0) — there is no
lesser permission tier to fall back to, so there is nothing app-specific to add here. This module
exists for structural consistency with ``APP-DESIGN.md`` §2's package layout and so a host or
tool that imports ``cleanup_app.permissions`` by convention doesn't hit an ``ImportError``.
"""
