"""Hermetic inventory fixtures for tests that do not exercise local companions."""
from __future__ import annotations

import atexit
import shutil
import tempfile
import uuid
from pathlib import Path


_TEMPORARY_DIRECTORY = tempfile.TemporaryDirectory()
_FIXTURE_DIRECTORY = tempfile.TemporaryDirectory()
atexit.register(_FIXTURE_DIRECTORY.cleanup)
atexit.register(_TEMPORARY_DIRECTORY.cleanup)


def fixture_directory(prefix: str) -> Path:
    """Create a unique test fixture directory beneath one managed root."""
    path = Path(_FIXTURE_DIRECTORY.name) / f"{prefix}{uuid.uuid4().hex}"
    path.mkdir()
    return path
INVENTORY_PATH = Path(_TEMPORARY_DIRECTORY.name) / "docker-constructor.toml"
shutil.copyfile(Path(__file__).resolve().parents[1] / "docker-constructor.toml", INVENTORY_PATH)
