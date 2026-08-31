"""Canonical hashed tree manifest and no-follow verification.

``build_tree_manifest`` deterministically describes every file, directory,
and contained symlink beneath a tree root in canonical path order, hashing
each regular file with SHA-256.  ``verify_tree`` re-validates a stored
manifest against the live filesystem without ever following a symlink and
detects every corruption class: extra, missing, ordering, type, hash,
permission, ownership, and escaping symlink.  The canonical tree digest
covers only content-bearing fields (path, kind, file hash, symlink target),
so it is independent of ownership and permission metadata.

Neither primitive assumes a published output identity or an
assembler-evidence digest; those remain Phase 5 contracts.
"""

from __future__ import annotations

import hashlib
import json
import os
import posixpath
import stat as _stat
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Iterator

from .errors import LockedNpmError

_DIR_FLAGS = (
    os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
)
_NOFOLLOW_RDONLY = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)

_KIND_FILE = "file"
_KIND_DIRECTORY = "directory"
_KIND_SYMLINK = "symlink"
_KIND_SPECIAL = "special"


def _sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _canonical_json(obj: object) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"))


def _contained_target(rel_path: str, target: str) -> bool:
    """Return True when a symlink target resolves inside the tree root."""
    if not target or os.path.isabs(target) or "\\" in target:
        return False
    resolved = posixpath.normpath(
        posixpath.join(posixpath.dirname(rel_path), target)
    )
    return not (resolved == ".." or resolved.startswith("../"))


@dataclass(frozen=True, order=True)
class TreeEntry:
    """One canonical entry in a tree manifest."""

    path: str
    """POSIX relative path beneath the tree root."""

    kind: str
    """``"file"``, ``"directory"``, or ``"symlink"``."""

    digest: str
    """SHA-256 hex for files, empty otherwise."""

    target: str
    """Raw symlink target for symlinks, empty otherwise."""

    mode: int
    """Permission bits (``stat.S_IMODE``)."""

    uid: int
    """Owner UID."""

    gid: int
    """Owner GID."""


@dataclass(frozen=True)
class TreeManifest:
    """Immutable canonical tree manifest and its content digest."""

    entries: tuple[TreeEntry, ...]
    """Entries in canonical path order."""

    digest: str
    """Canonical SHA-256 over content fields only (no mode/ownership)."""


@dataclass(frozen=True)
class _Found:
    path: str
    kind: str
    digest: str
    target: str
    mode: int
    uid: int
    gid: int


def canonical_tree_digest(entries: Iterable[TreeEntry]) -> str:
    """Return the canonical SHA-256 digest over sorted content fields."""
    ordered = sorted(entries)
    payload = _canonical_json(
        [
            {
                "path": e.path,
                "kind": e.kind,
                "digest": e.digest,
                "target": e.target,
            }
            for e in ordered
        ]
    ).encode("utf-8")
    return _sha256_hex(payload)


def _iter_entries(dir_fd: int, prefix: str) -> Iterator[_Found]:
    """Yield canonical entries beneath *dir_fd* without following symlinks.

    Children are processed in sorted name order; directories are reopened
    descriptor-relatively with ``O_DIRECTORY | O_NOFOLLOW``; files are
    opened once with ``O_NOFOLLOW`` and hashed from that same descriptor.
    Special files (FIFOs, sockets, devices) are reported as ``"special"`` so
    the caller can reject them with the right reason.
    """
    for name in sorted(os.listdir(dir_fd)):
        rel = f"{prefix}/{name}" if prefix else name
        st = os.stat(name, dir_fd=dir_fd, follow_symlinks=False)
        mode = _stat.S_IMODE(st.st_mode)
        uid = st.st_uid
        gid = st.st_gid
        if _stat.S_ISLNK(st.st_mode):
            target = os.readlink(name, dir_fd=dir_fd)
            yield _Found(rel, _KIND_SYMLINK, "", target, mode, uid, gid)
        elif _stat.S_ISDIR(st.st_mode):
            yield _Found(rel, _KIND_DIRECTORY, "", "", mode, uid, gid)
            try:
                sub_fd = os.open(name, _DIR_FLAGS, dir_fd=dir_fd)
            except OSError as exc:
                raise LockedNpmError(
                    "tree_type_mismatch",
                    f"cannot open directory entry {rel!r}: {exc}",
                ) from exc
            try:
                yield from _iter_entries(sub_fd, rel)
            finally:
                os.close(sub_fd)
        elif _stat.S_ISREG(st.st_mode):
            try:
                fd = os.open(name, _NOFOLLOW_RDONLY, dir_fd=dir_fd)
            except OSError as exc:
                raise LockedNpmError(
                    "tree_type_mismatch",
                    f"cannot open file entry {rel!r}: {exc}",
                ) from exc
            try:
                fst = os.fstat(fd)
                if not _stat.S_ISREG(fst.st_mode):
                    raise LockedNpmError(
                        "tree_type_mismatch",
                        f"file entry {rel!r} changed type while being read",
                    )
                hasher = hashlib.sha256()
                while True:
                    chunk = os.read(fd, 64 * 1024)
                    if not chunk:
                        break
                    hasher.update(chunk)
                yield _Found(
                    rel,
                    _KIND_FILE,
                    hasher.hexdigest(),
                    "",
                    _stat.S_IMODE(fst.st_mode),
                    fst.st_uid,
                    fst.st_gid,
                )
            finally:
                os.close(fd)
        else:
            yield _Found(rel, _KIND_SPECIAL, "", "", mode, uid, gid)


def _open_tree_root(root: Path) -> int:
    """Open *root* as a directory no-follow and return its descriptor."""
    try:
        fd = os.open(str(root), _DIR_FLAGS)
    except OSError as exc:
        raise LockedNpmError(
            "unsafe_cache_path", f"unsafe tree root {root}: {exc}"
        ) from exc
    try:
        st = os.fstat(fd)
        if not _stat.S_ISDIR(st.st_mode):
            raise LockedNpmError(
                "unsafe_cache_path", f"tree root {root} is not a directory"
            )
    except BaseException:
        os.close(fd)
        raise
    return fd


def build_tree_manifest(root: str | Path) -> TreeManifest:
    """Build a canonical tree manifest for the directory tree at *root*.

    Rejects a symlinked root, special files, and symlinks whose target is
    absolute, contains a backslash, or resolves outside the tree root.
    """
    root_path = Path(root)
    root_fd = _open_tree_root(root_path)
    try:
        found = list(_iter_entries(root_fd, ""))
    finally:
        os.close(root_fd)

    for entry in found:
        if entry.kind == _KIND_SPECIAL:
            raise LockedNpmError(
                "unsupported_entry_type",
                f"unsupported special filesystem entry at {entry.path!r}",
            )
        if entry.kind == _KIND_SYMLINK and not _contained_target(
            entry.path, entry.target
        ):
            raise LockedNpmError(
                "unsafe_symlink_target",
                f"symlink {entry.path!r} targets outside the tree: "
                f"{entry.target!r}",
            )

    entries = tuple(
        sorted(
            TreeEntry(
                path=e.path,
                kind=e.kind,
                digest=e.digest,
                target=e.target,
                mode=e.mode,
                uid=e.uid,
                gid=e.gid,
            )
            for e in found
        )
    )
    return TreeManifest(entries=entries, digest=canonical_tree_digest(entries))


def _compare(found: _Found, expected: TreeEntry) -> None:
    if found.kind == _KIND_SYMLINK and not _contained_target(
        found.path, found.target
    ):
        raise LockedNpmError(
            "tree_symlink_escape",
            f"symlink {found.path!r} targets outside the tree: "
            f"{found.target!r}",
        )
    if found.kind != expected.kind:
        raise LockedNpmError(
            "tree_type_mismatch",
            f"{found.path!r}: expected {expected.kind}, found {found.kind}",
        )
    if found.kind == _KIND_FILE and found.digest != expected.digest:
        raise LockedNpmError(
            "tree_hash_mismatch",
            f"{found.path!r}: file hash does not match the manifest",
        )
    if found.kind == _KIND_SYMLINK and found.target != expected.target:
        raise LockedNpmError(
            "tree_symlink_target_mismatch",
            f"{found.path!r}: symlink target {found.target!r} does not match "
            f"manifest target {expected.target!r}",
        )
    if found.mode != expected.mode:
        raise LockedNpmError(
            "tree_permission_mismatch",
            f"{found.path!r}: mode {found.mode:04o} does not match manifest "
            f"mode {expected.mode:04o}",
        )
    if found.uid != expected.uid or found.gid != expected.gid:
        raise LockedNpmError(
            "tree_ownership_mismatch",
            f"{found.path!r}: ownership ({found.uid}:{found.gid}) does not "
            f"match the manifest ({expected.uid}:{expected.gid})",
        )


def verify_tree(root: str | Path, manifest: TreeManifest) -> None:
    """Re-validate *root* against *manifest* without following symlinks.

    First the manifest itself is checked for canonical ordering, unique
    paths, and digest consistency; then every live entry is compared for
    type, hash, target, permission, and ownership.  Extra and missing
    entries are rejected.  Raises :class:`LockedNpmError` on any corruption.
    """
    ordered = tuple(sorted(manifest.entries))
    if manifest.entries != ordered:
        raise LockedNpmError(
            "tree_order_mismatch",
            "tree manifest entries are not in canonical path order",
        )
    if len(ordered) != len({e.path for e in ordered}):
        raise LockedNpmError(
            "tree_order_mismatch", "tree manifest contains duplicate paths"
        )
    if canonical_tree_digest(manifest.entries) != manifest.digest:
        raise LockedNpmError(
            "tree_manifest_digest_mismatch",
            "tree manifest digest does not match its entries",
        )

    by_path = {e.path: e for e in manifest.entries}
    seen: set[str] = set()
    root_fd = _open_tree_root(Path(root))
    try:
        for found in _iter_entries(root_fd, ""):
            expected = by_path.get(found.path)
            if expected is None:
                raise LockedNpmError(
                    "tree_extra_entry",
                    f"unexpected tree entry {found.path!r}",
                )
            seen.add(found.path)
            _compare(found, expected)
    finally:
        os.close(root_fd)

    missing = [path for path in by_path if path not in seen]
    if missing:
        raise LockedNpmError(
            "tree_missing_entry",
            f"tree entry {missing[0]!r} is missing from the filesystem",
        )
