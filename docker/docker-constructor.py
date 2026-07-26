#!/usr/bin/env python3
"""Executable bootstrap for the Pi Docker constructor CLI.

This is a minimal wrapper that ensures the repository root is on
``sys.path`` and then delegates to the importable facade in
``docker.constructor_cli``.

``sys.path`` manipulation is confined to this file and only happens
under ``__name__ == "__main__"`` — ordinary imports (e.g. from tests)
never trigger it.
"""

from __future__ import annotations

import sys
from pathlib import Path


def _bootstrap() -> int:
    repo_root = Path(__file__).resolve().parent.parent
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))

    from docker.constructor_cli import main

    return main()


if __name__ == "__main__":
    raise SystemExit(_bootstrap())
