#!/usr/bin/env python
"""Dev-only entrypoint — never packaged (setuptools only picks up ``src/``, per
``[tool.setuptools.packages.find]`` in ``pyproject.toml``).

This app ships no host project of its own; every other command in this repo boots Django
through pytest-django's ``DJANGO_SETTINGS_MODULE`` instead. This file exists solely so
``APP-DESIGN.md`` §12's documented ``manage.py spectacular --file schema.yml --fail-on-warn``
command (and the equivalent CI job) has something real to run against, using the same
``tests.backend.settings`` every other check already uses.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
# Mirrors pyproject.toml's [tool.pytest.ini_options] pythonpath = ["src", ".."] — src/ for the
# package itself, .. (the repo root) for the tests.backend.settings module one level up.
sys.path[:0] = [str(HERE / "src"), str(HERE.parent)]

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "tests.backend.settings")


def main() -> None:
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError(
            "Couldn't import Django. Are you sure it's installed and "
            "available on your PYTHONPATH environment variable? Did you "
            "forget to activate a virtual environment?"
        ) from exc
    execute_from_command_line(sys.argv)


if __name__ == "__main__":
    main()
