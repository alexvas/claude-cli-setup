"""Immutable, minimal BuildKit named-context snapshots for build artifacts."""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import stat
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from .build_cache import BuildCacheError, prepare_build_cache, validate_host_owner_traversal
from .build_materialization import SelectedBuildArtifact

_LOGICAL_NAMES = {
    "rustup": "rustup-init",
    "uv": "uv.tar.gz",
    "rtk": "rtk.deb",
    "fd": "fd.deb",
}


class SnapshotError(RuntimeError):
    """A snapshot cannot safely be created or imported."""


@dataclass(frozen=True)
class MaterializedSnapshot:
    path: Path
    manifest: Path


def _digest(path: Path, expected: str) -> None:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    if digest.hexdigest() != expected:
        raise SnapshotError(f"snapshot payload {path.name!r} failed digest verification")


def _readonly_tree(root: Path) -> None:
    # Files first: directory permissions must not prevent traversal during
    # finalisation.  Snapshot payloads are newly-created private copies/links.
    for path in root.rglob("*"):
        if path.is_symlink():
            raise SnapshotError("selected prebuilt-artifact snapshot contains a symlink")
        if path.is_file():
            os.chmod(path, 0o444)
    for path in sorted((p for p in root.rglob("*") if p.is_dir()), key=lambda p: len(p.parts), reverse=True):
        os.chmod(path, 0o555)
    os.chmod(root, 0o555)


def create_artifact_snapshot(
    selected: Iterable[SelectedBuildArtifact], blobs: Iterable[Path], *, checkout_root: str | Path,
) -> MaterializedSnapshot:
    """Create a narrow immutable snapshot, preferring hard links to blobs.

    The manifest is canonical JSON and contains no cache paths or URLs.  A
    copied fallback is hashed after copy; links are also revalidated so an
    unlink of the cache name cannot alter the imported bytes.
    """
    entries = tuple(zip(selected, blobs, strict=True))
    if {entry.name for entry, _ in entries} != set(_LOGICAL_NAMES):
        raise SnapshotError("snapshot requires exactly the selected reviewed artifacts")
    paths = prepare_build_cache(checkout_root)
    staging = Path(tempfile.mkdtemp(prefix="transaction-", dir=paths.generated_root))
    try:
        manifest_entries: list[dict[str, str]] = []
        for item, blob in sorted(entries, key=lambda pair: _LOGICAL_NAMES[pair[0].name]):
            destination = staging / _LOGICAL_NAMES[item.name]
            try:
                os.link(blob, destination, follow_symlinks=False)
            except OSError:
                shutil.copyfile(blob, destination, follow_symlinks=False)
            _digest(destination, item.identity.hex_digest())
            manifest_entries.append({"name": item.name, "filename": destination.name,
                                     "sha256": item.identity.hex_digest()})
        manifest = staging / "manifest.json"
        manifest.write_bytes((json.dumps({"artifacts": manifest_entries}, sort_keys=True,
                                         separators=(",", ":")) + "\n").encode())
        _readonly_tree(staging)
        validate_host_owner_traversal(staging)
        return MaterializedSnapshot(path=staging, manifest=manifest)
    except BaseException:
        # Preserve the construction failure even if best-effort cleanup meets
        # an unrelated filesystem error after finalisation.
        try:
            cleanup_artifact_snapshot(staging)
        except BaseException:
            pass
        raise


def cleanup_artifact_snapshot(snapshot: MaterializedSnapshot | Path | None) -> None:
    if snapshot is None:
        return
    path = snapshot.path if isinstance(snapshot, MaterializedSnapshot) else snapshot
    # A readonly tree is removable only after its parent control directory
    # unlinks it; shutil handles the child permissions on supported hosts.
    try:
        shutil.rmtree(path)
    except PermissionError:
        for entry in sorted(path.rglob("*"), key=lambda p: len(p.parts), reverse=True):
            if not entry.is_symlink():
                try: os.chmod(entry, 0o700)
                except OSError: pass
        try: os.chmod(path, 0o700)
        except OSError: pass
        shutil.rmtree(path, ignore_errors=True)
