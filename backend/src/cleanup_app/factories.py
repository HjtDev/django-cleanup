"""``factory_boy`` factories — this app's public *test-only* surface (``APP-DESIGN.md`` §7.3).

Phases 2/7 add factories for ``CleanupRun``/``CleanupRunFile`` here. A host's own test suite is
expected to import from here rather than hand-rolling equivalents.

This module is ruff-banned from ``src/cleanup_app`` (see ``backend/pyproject.toml``'s
``banned-api`` block) — nothing under ``src/`` may import it, since importing test factories from
production code is exactly the mistake that guard exists to catch. The test tree
(``../tests/backend``) is exempted from that ban.
"""
