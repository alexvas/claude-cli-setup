"""Hermetic inventory fixtures for tests that do not exercise local companions."""
from __future__ import annotations

import atexit
import shutil
import tempfile
from pathlib import Path


_TEMPORARY_DIRECTORY = tempfile.TemporaryDirectory()
atexit.register(_TEMPORARY_DIRECTORY.cleanup)
INVENTORY_PATH = Path(_TEMPORARY_DIRECTORY.name) / "docker-constructor.toml"
shutil.copyfile(Path(__file__).resolve().parents[1] / "docker-constructor.toml", INVENTORY_PATH)
