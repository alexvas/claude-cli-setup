"""Immutable, minimal BuildKit named-context snapshots for build artifacts."""
from __future__ import annotations

import errno
import hashlib
import json
import os
import shutil
import stat
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from .build_cache import prepare_build_cache, validate_host_owner_traversal
from .build_materialization import SelectedBuildArtifact
from .project_state import ProjectState

_LOGICAL_NAMES = {
    "rustup": "rustup-init",
    "uv": "uv.tar.gz",
    "rtk": "rtk.deb",
    "fd": "fd.deb",
}

# Read-only, no-follow open for descriptor-based payload validation.
_NOFOLLOW_RDONLY = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)

# Read-only, no-follow directory open for descriptor-relative staging.
_NOFOLLOW_DIR = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)

# Hard-link failure modes that mean hard linking is unavailable, not unsafe.
# Only these fall back to descriptor-based copying.  EPERM/EACCES (protected
# hard links), ELOOP (a replaced symlink), a vanished source, or any other
# error fails closed instead of silently copying an unverified payload.
_HARD_LINK_UNAVAILABLE = frozenset({
    errno.EXDEV,
    errno.EOPNOTSUPP,
    getattr(errno, "ENOTSUP", errno.EOPNOTSUPP),
})


class SnapshotError(RuntimeError):
    """A snapshot cannot safely be created or imported."""


@dataclass(frozen=True)
class MaterializedSnapshot:
    path: Path
    manifest: Path


def _hash_descriptor(fd: int) -> str:
    digest = hashlib.sha256()
    while True:
        chunk = os.read(fd, 1024 * 1024)
        if not chunk:
            return digest.hexdigest()
        digest.update(chunk)


def _open_validated_source(blob: Path, expected: str) -> int:
    """Open and validate a source blob, returning its retained descriptor.

    The source must be a regular file owned by the invoking user with mode
    exactly 0444 and the expected digest.  Missing, symlinked, foreign-owned,
    writable, non-regular, or digest-mismatched sources raise ``SnapshotError``
    and are never chmodded, chowned, deleted, or repaired.  The descriptor is
    kept open so the validated bytes are reused for hard-link publication or
    descriptor-based copying without reopening an untrusted pathname.
    """
    try:
        fd = os.open(blob, _NOFOLLOW_RDONLY)
    except OSError as exc:
        raise SnapshotError(f"cannot open snapshot source blob {blob}: {exc}") from exc
    try:
        st = os.fstat(fd)
        if not stat.S_ISREG(st.st_mode):
            raise SnapshotError(f"snapshot source blob {blob} is not a regular file")
        if st.st_uid != os.geteuid():
            raise SnapshotError(f"snapshot source blob {blob} is not owned by the invoking user")
        if stat.S_IMODE(st.st_mode) != 0o444:
            raise SnapshotError(f"snapshot source blob {blob} must be mode 0444")
        if _hash_descriptor(fd) != expected:
            raise SnapshotError(f"snapshot source blob {blob} failed digest verification")
        return fd
    except BaseException:
        os.close(fd)
        raise


def _copy_source_fd_to_destination(
    source_fd: int, destination_name: str, dir_fd: int, expected: str,
) -> None:
    """Copy a validated source descriptor to a descriptor-relative destination.

    The destination is created with ``O_WRONLY | O_CREAT | O_EXCL |
    O_NOFOLLOW``, its bytes are copied from the retained validated descriptor
    (never a reopened pathname) and hashed as they stream, the copied digest
    must match, and only the independent destination inode is finalized to
    0444 before being flushed.
    """
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(destination_name, flags, 0o444, dir_fd=dir_fd)
    except OSError as exc:
        raise SnapshotError(f"cannot create snapshot payload {destination_name!r}: {exc}") from exc
    try:
        os.lseek(source_fd, 0, os.SEEK_SET)
        digest = hashlib.sha256()
        while True:
            chunk = os.read(source_fd, 1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
            view = memoryview(chunk)
            while view:
                written = os.write(fd, view)
                view = view[written:]
        if digest.hexdigest() != expected:
            raise SnapshotError(f"snapshot payload {destination_name!r} failed digest verification")
        os.fchmod(fd, 0o444)
        os.fsync(fd)
    except BaseException:
        os.close(fd)
        try:
            os.unlink(destination_name, dir_fd=dir_fd)
        except OSError:
            pass
        raise
    os.close(fd)


def _validate_hard_link_destination(
    destination_name: str, dir_fd: int, source_stat: os.stat_result, expected: str,
) -> None:
    """Open and revalidate a hard-linked destination descriptor-relatively.

    The destination must reference the same inode (``st_dev``/``st_ino``) as
    the validated source and itself be a regular, invoking-user-owned 0444
    file with the expected digest.  On any failure the descriptor is closed
    and the original ``SnapshotError`` propagates; the caller removes the
    unsafe destination name without mutating the source inode.
    """
    try:
        fd = os.open(destination_name, _NOFOLLOW_RDONLY, dir_fd=dir_fd)
    except OSError as exc:
        raise SnapshotError(
            f"cannot open hard-linked snapshot payload {destination_name!r}: {exc}"
        ) from exc
    try:
        st = os.fstat(fd)
        if st.st_dev != source_stat.st_dev or st.st_ino != source_stat.st_ino:
            raise SnapshotError(
                f"hard-linked snapshot payload {destination_name!r} does not "
                "reference the validated source inode"
            )
        if not stat.S_ISREG(st.st_mode):
            raise SnapshotError(f"hard-linked snapshot payload {destination_name!r} is not a regular file")
        if st.st_uid != os.geteuid():
            raise SnapshotError(f"hard-linked snapshot payload {destination_name!r} is not owned by the invoking user")
        if stat.S_IMODE(st.st_mode) != 0o444:
            raise SnapshotError(f"hard-linked snapshot payload {destination_name!r} must be mode 0444")
        if _hash_descriptor(fd) != expected:
            raise SnapshotError(f"hard-linked snapshot payload {destination_name!r} failed digest verification")
    finally:
        os.close(fd)


def _readonly_tree(root: Path, hard_linked: set[Path]) -> None:
    # Files first: directory permissions must not prevent traversal during
    # finalisation.  Hard-linked payloads already share the cache blob's
    # required 0444 inode and must never be chmodded (that would mutate the
    # cached blob).  Copy-fallback payloads and snapshot-owned files such as
    # ``manifest.json`` have independent inodes and are finalized to 0444 here.
    # Membership is compared by root-relative path so a nested snapshot-owned
    # file sharing a hard-linked payload's basename is still finalized.
    for path in root.rglob("*"):
        if path.is_symlink():
            raise SnapshotError("selected prebuilt-artifact snapshot contains a symlink")
        if path.is_file() and path.relative_to(root) not in hard_linked:
            os.chmod(path, 0o444)
    for path in sorted((p for p in root.rglob("*") if p.is_dir()), key=lambda p: len(p.parts), reverse=True):
        os.chmod(path, 0o555)
    os.chmod(root, 0o555)


def create_artifact_snapshot(
    selected: Iterable[SelectedBuildArtifact], blobs: Iterable[Path], *, checkout_root: str | Path,
    cache_root: str | Path | None = None, project_state: ProjectState | None = None,
) -> MaterializedSnapshot:
    """Create a narrow immutable snapshot, preferring hard links to blobs.

    The manifest is canonical JSON and contains no cache paths or URLs.  Each
    source blob is opened and validated through a no-follow descriptor before
    publication; a copied fallback streams from that retained descriptor.  A
    hard link is accepted only after the linked destination is opened
    descriptor-relatively and its identity (``st_dev``/``st_ino``) is compared
    against the validated source inode, closing the pathname-replacement
    window between linking and publication.
    """
    entries = tuple(zip(selected, blobs, strict=True))
    if {entry.name for entry, _ in entries} != set(_LOGICAL_NAMES):
        raise SnapshotError("snapshot requires exactly the selected reviewed artifacts")
    paths = prepare_build_cache(checkout_root, cache_root=cache_root, project_state=project_state)
    staging = Path(tempfile.mkdtemp(prefix="transaction-", dir=paths.generated_root))
    try:
        staging_fd = os.open(staging, _NOFOLLOW_DIR)
    except OSError as exc:
        try:
            cleanup_artifact_snapshot(staging)
        except BaseException:
            pass
        raise SnapshotError(f"cannot open snapshot staging directory {staging}: {exc}") from exc
    try:
        manifest_entries: list[dict[str, str]] = []
        hard_linked: set[Path] = set()
        for item, blob in sorted(entries, key=lambda pair: _LOGICAL_NAMES[pair[0].name]):
            destination_name = _LOGICAL_NAMES[item.name]
            expected = item.identity.hex_digest()
            source_fd = _open_validated_source(blob, expected)
            try:
                source_stat = os.fstat(source_fd)
                try:
                    os.link(blob, destination_name, follow_symlinks=False, dst_dir_fd=staging_fd)
                except OSError as exc:
                    if exc.errno not in _HARD_LINK_UNAVAILABLE:
                        raise SnapshotError(
                            f"cannot hard link snapshot payload {destination_name!r} "
                            f"from source blob {blob}: {exc}"
                        ) from exc
                    _copy_source_fd_to_destination(source_fd, destination_name, staging_fd, expected)
                else:
                    try:
                        _validate_hard_link_destination(
                            destination_name, staging_fd, source_stat, expected)
                    except BaseException:
                        try:
                            os.unlink(destination_name, dir_fd=staging_fd)
                        except OSError:
                            pass
                        raise
                    hard_linked.add(Path(destination_name))
            finally:
                os.close(source_fd)
            manifest_entries.append({"name": item.name, "filename": destination_name,
                                     "sha256": item.identity.hex_digest()})
        manifest = staging / "manifest.json"
        manifest.write_bytes((json.dumps({"artifacts": manifest_entries}, sort_keys=True,
                                         separators=(",", ":")) + "\n").encode())
        _readonly_tree(staging, hard_linked)
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
    finally:
        os.close(staging_fd)


def cleanup_artifact_snapshot(snapshot: MaterializedSnapshot | Path | None) -> None:
    if snapshot is None:
        return
    path = snapshot.path if isinstance(snapshot, MaterializedSnapshot) else snapshot
    # A readonly tree is removable only after its parent control directory
    # unlinks it; shutil handles the child permissions on supported hosts.
    try:
        shutil.rmtree(path)
    except PermissionError:
        # Unlinking a file requires write permission on its parent directory,
        # not on the file itself. Snapshot payloads may be hard links to
        # immutable cache blobs, so chmodding files here would also corrupt the
        # cached blob mode and make the next build reject an otherwise valid
        # hit. Restore write/traverse permission only on snapshot directories.
        for entry in sorted(path.rglob("*"), key=lambda p: len(p.parts), reverse=True):
            if entry.is_dir() and not entry.is_symlink():
                try: os.chmod(entry, 0o700)
                except OSError: pass
        try: os.chmod(path, 0o700)
        except OSError: pass
        shutil.rmtree(path, ignore_errors=True)
