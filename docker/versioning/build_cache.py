"""Checkout-local build-cache boundary.

Persistent build artifact state lives beneath a fixed ignored checkout path
(``.docker-cache/build-artifacts``); per-build transaction snapshots live
beneath checkout-local generated state (``.docker-generated/build-artifacts``).
Neither path is configurable and neither uses the shared XDG constructor
cache.

The module provides:

* lexical, deterministic path resolution (no filesystem reads);
* host-owner traversal validation for the checkout path (no repair);
* no-follow preparation of constructor-owned private ``0700`` subtrees that
  rejects symlinked, non-directory, or foreign-owned entries *before* any
  mutation;
* atomic publication of a verified blob at its canonical content-addressed
  path with mode ``0444``, re-verified before it is returned.

The constructor never chmods or chowns the checkout root, any ancestor, the
user's home directory, or unrelated cache paths.
"""

from __future__ import annotations

import hashlib
import os
import stat as _stat
from dataclasses import dataclass
from pathlib import Path

from docker.versioning.digest_identity import DigestIdentity

BUILD_CACHE_DIR_NAME = ".docker-cache"
"""Fixed ignored checkout-local persistent build-cache directory name."""

BUILD_ARTIFACTS_DIR_NAME = "build-artifacts"
"""Child directory holding build blobs, tmp state, and transaction snapshots."""

GENERATED_DIR_NAME = ".docker-generated"
"""Checkout-local generated-state directory shared with runtime projections."""

BLOB_EXTENSION = ".blob"
"""Content-addressed build-blob filename extension."""


class BuildCacheError(ValueError):
    """Invalid or unsafe checkout-local build-cache configuration."""


@dataclass(frozen=True)
class BuildCachePaths:
    """Resolved and prepared checkout-local build-cache roots."""

    checkout_root: Path
    """Resolved checkout root."""

    persistent_root: Path
    """``<checkout>/.docker-cache/build-artifacts``."""

    blobs_root: Path
    """``<checkout>/.docker-cache/build-artifacts/blobs``."""

    tmp_root: Path
    """``<checkout>/.docker-cache/build-artifacts/tmp``."""

    generated_root: Path
    """``<checkout>/.docker-generated/build-artifacts``."""


_DIR_FLAGS = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)


# ═══════════════════════════════════════════════════════════════════════
# Lexical path resolution (no filesystem access)
# ═══════════════════════════════════════════════════════════════════════


def _normalize_checkout(checkout_root: str | Path) -> Path:
    return Path(os.path.abspath(os.fspath(checkout_root)))


def resolve_build_cache_root(checkout_root: str | Path) -> Path:
    """Return the fixed persistent build-cache root beneath *checkout_root*."""
    return _normalize_checkout(checkout_root) / BUILD_CACHE_DIR_NAME / BUILD_ARTIFACTS_DIR_NAME


def resolve_build_blobs_root(checkout_root: str | Path) -> Path:
    """Return the verified-blob child beneath the persistent build root."""
    return resolve_build_cache_root(checkout_root) / "blobs"


def resolve_build_tmp_root(checkout_root: str | Path) -> Path:
    """Return the temporary-publication child beneath the persistent root."""
    return resolve_build_cache_root(checkout_root) / "tmp"


def resolve_build_generated_root(checkout_root: str | Path) -> Path:
    """Return the checkout-local generated transaction-snapshot root."""
    return _normalize_checkout(checkout_root) / GENERATED_DIR_NAME / BUILD_ARTIFACTS_DIR_NAME


def build_blob_path(blobs_root: str | Path, identity: DigestIdentity) -> Path:
    """Return the canonical content-addressed blob path for *identity*."""
    return Path(identity.cache_path(os.fspath(blobs_root), extension=BLOB_EXTENSION))


# ═══════════════════════════════════════════════════════════════════════
# Host-owner traversal validation (strict no-repair)
# ═══════════════════════════════════════════════════════════════════════


def validate_host_owner_traversal(path: str | Path) -> None:
    """Require the invoking host user to traverse every ancestor of *path*.

    Walks from the filesystem root to *path* (following symlinked ancestors
    as the OS would) and requires each component to be a directory with
    search permission for the invoking user.  It never chmods or chowns
    anything: an inaccessible ancestor is reported with its path and left
    untouched.
    """
    absolute = os.path.abspath(os.fspath(path))
    current = os.sep
    for part in (component for component in absolute.split(os.sep) if component):
        current = os.path.join(current, part)
        try:
            st = os.stat(current)
        except OSError as exc:
            raise BuildCacheError(
                f"cannot access checkout traversal component {current}: {exc}"
            ) from exc
        if not _stat.S_ISDIR(st.st_mode):
            raise BuildCacheError(
                f"checkout traversal component {current} is not a directory"
            )
        if not os.access(current, os.X_OK):
            raise BuildCacheError(
                f"cannot traverse {current}; the invoking user lacks search "
                "permission and the constructor will not repair it"
            )


# ═══════════════════════════════════════════════════════════════════════
# Descriptor-relative, no-follow directory helpers
# ═══════════════════════════════════════════════════════════════════════


def _open_checkout_fd(checkout: Path) -> int:
    """Open the checkout root no-follow and require directory + writability."""
    try:
        fd = os.open(os.fspath(checkout), _DIR_FLAGS)
    except FileNotFoundError as exc:
        raise BuildCacheError(f"checkout root {checkout} does not exist") from exc
    except PermissionError as exc:
        raise BuildCacheError(f"cannot access checkout root {checkout}: {exc}") from exc
    except OSError as exc:
        raise BuildCacheError(
            f"checkout root {checkout} is a symlink or not a directory: {exc}"
        ) from exc
    try:
        st = os.fstat(fd)
        if not _stat.S_ISDIR(st.st_mode):
            raise BuildCacheError(f"checkout root {checkout} is not a directory")
        if not os.access(checkout, os.W_OK | os.X_OK):
            raise BuildCacheError(
                f"checkout root {checkout} is not writable by the invoking user"
            )
        return fd
    except BaseException:
        os.close(fd)
        raise


def _open_relative_dir(
    checkout_fd: int,
    parts: tuple[str, ...],
    *,
    create: bool,
) -> int | None:
    """Open ``parts`` relative to *checkout_fd* without following symlinks.

    Returns the opened descriptor of the final component, or ``None`` when a
    component is missing and *create* is false.  Missing components are
    created descriptor-relatively with ``0700`` when *create* is true.
    Symlinked or non-directory components raise :class:`BuildCacheError`.
    """
    current_fd = os.dup(checkout_fd)
    try:
        for component in parts:
            created = False
            try:
                value = os.stat(
                    component, dir_fd=current_fd, follow_symlinks=False,
                )
            except FileNotFoundError:
                if not create:
                    os.close(current_fd)
                    return None
                try:
                    os.mkdir(component, 0o700, dir_fd=current_fd)
                except OSError as exc:
                    raise BuildCacheError(
                        f"cannot create build-cache component {component!r}: {exc}"
                    ) from exc
                created = True
                # Set the exact owner-only mode before opening; os.mkdir's
                # mode is subject to the ambient umask, which could otherwise
                # strip the owner bits and make the new entry unopenable.
                os.chmod(component, 0o700, dir_fd=current_fd, follow_symlinks=False)
                value = os.stat(
                    component, dir_fd=current_fd, follow_symlinks=False,
                )
            except OSError as exc:
                raise BuildCacheError(
                    f"cannot access build-cache component {component!r}: {exc}"
                ) from exc
            if _stat.S_ISLNK(value.st_mode) or not _stat.S_ISDIR(value.st_mode):
                raise BuildCacheError(
                    f"unsafe build-cache component {component!r}; remove the "
                    "entry or restore it as a directory"
                )
            try:
                next_fd = os.open(component, _DIR_FLAGS, dir_fd=current_fd)
            except OSError as exc:
                raise BuildCacheError(
                    f"cannot open build-cache component {component!r}: {exc}"
                ) from exc
            if created:
                # Explicit mode, independent of the process umask.
                os.fchmod(next_fd, 0o700)
            os.close(current_fd)
            current_fd = next_fd
        return current_fd
    except BaseException:
        os.close(current_fd)
        raise


def _require_private_dir(
    fd: int,
    label: str,
    *,
    check_owner: bool,
) -> None:
    """Require an opened directory to be a directory (and optionally owned).

    Never creates, chmods, or chowns anything; this is a read-only check.
    """
    st = os.fstat(fd)
    if not _stat.S_ISDIR(st.st_mode):
        raise BuildCacheError(f"{label} is not a directory")
    if check_owner and st.st_uid != os.geteuid():
        raise BuildCacheError(
            f"{label} is not owned by the invoking user; restore ownership "
            "or remove the stale entry"
        )


def _validate_relative_dir(
    checkout_fd: int,
    parts: tuple[str, ...],
    *,
    label: str,
    check_owner: bool,
) -> None:
    """Validate an existing build-cache component without mutating it."""
    fd = _open_relative_dir(checkout_fd, parts, create=False)
    if fd is None:
        return
    try:
        _require_private_dir(fd, label, check_owner=check_owner)
    finally:
        os.close(fd)


def _ensure_relative_dir(
    checkout_fd: int,
    parts: tuple[str, ...],
    *,
    label: str,
    check_owner: bool,
    chmod_existing: bool = True,
) -> None:
    """Create (if missing) and secure a build-cache component."""
    fd = _open_relative_dir(checkout_fd, parts, create=True)
    if fd is None:
        raise BuildCacheError(f"cannot open build-cache component {label}")
    try:
        st = os.fstat(fd)
        if not _stat.S_ISDIR(st.st_mode):
            raise BuildCacheError(f"{label} is not a directory")
        if check_owner and st.st_uid != os.geteuid():
            raise BuildCacheError(
                f"{label} is not owned by the invoking user; restore ownership "
                "or remove the stale entry"
            )
        if chmod_existing and _stat.S_IMODE(st.st_mode) != 0o700:
            os.fchmod(fd, 0o700)
    finally:
        os.close(fd)


# Relative component paths for each constructor-owned (or constructor-managed)
# subtree.  ``.docker-generated`` itself is a pre-existing checkout ancestor:
# it is created ``0700`` only when missing and never chmod-ed when it exists.
_CACHE_PARTS = (BUILD_CACHE_DIR_NAME,)
_PERSISTENT_PARTS = (BUILD_CACHE_DIR_NAME, BUILD_ARTIFACTS_DIR_NAME)
_BLOBS_PARTS = (BUILD_CACHE_DIR_NAME, BUILD_ARTIFACTS_DIR_NAME, "blobs")
_TMP_PARTS = (BUILD_CACHE_DIR_NAME, BUILD_ARTIFACTS_DIR_NAME, "tmp")
_GENERATED_PARENT_PARTS = (GENERATED_DIR_NAME,)
_GENERATED_PARTS = (GENERATED_DIR_NAME, BUILD_ARTIFACTS_DIR_NAME)


def prepare_build_cache(checkout_root: str | Path) -> BuildCachePaths:
    """Validate and prepare checkout-local build-cache roots.

    All existing constructor-owned entries are validated (no-follow, no
    symlink escape, correct type, invoking-user ownership) **before** any
    directory is created or chmod-ed, so an unsafe entry fails without
    mutating anything.  The checkout root, its ancestors, the home
    directory, and unrelated cache paths are never chmod-ed or chown-ed.
    """
    checkout = _normalize_checkout(checkout_root)
    validate_host_owner_traversal(checkout)
    checkout_fd = _open_checkout_fd(checkout)
    try:
        # ── validate every existing entry before any mutation ──
        _validate_relative_dir(checkout_fd, _CACHE_PARTS, label=str(checkout / BUILD_CACHE_DIR_NAME), check_owner=True)
        _validate_relative_dir(checkout_fd, _PERSISTENT_PARTS, label=str(checkout / BUILD_CACHE_DIR_NAME / BUILD_ARTIFACTS_DIR_NAME), check_owner=True)
        _validate_relative_dir(checkout_fd, _BLOBS_PARTS, label=str(checkout / BUILD_CACHE_DIR_NAME / BUILD_ARTIFACTS_DIR_NAME / "blobs"), check_owner=True)
        _validate_relative_dir(checkout_fd, _TMP_PARTS, label=str(checkout / BUILD_CACHE_DIR_NAME / BUILD_ARTIFACTS_DIR_NAME / "tmp"), check_owner=True)
        _validate_relative_dir(checkout_fd, _GENERATED_PARENT_PARTS, label=str(checkout / GENERATED_DIR_NAME), check_owner=False)
        _validate_relative_dir(checkout_fd, _GENERATED_PARTS, label=str(checkout / GENERATED_DIR_NAME / BUILD_ARTIFACTS_DIR_NAME), check_owner=True)

        # ── then create/secure the validated set ──
        _ensure_relative_dir(checkout_fd, _CACHE_PARTS, label=str(checkout / BUILD_CACHE_DIR_NAME), check_owner=True)
        _ensure_relative_dir(checkout_fd, _PERSISTENT_PARTS, label=str(checkout / BUILD_CACHE_DIR_NAME / BUILD_ARTIFACTS_DIR_NAME), check_owner=True)
        _ensure_relative_dir(checkout_fd, _BLOBS_PARTS, label=str(checkout / BUILD_CACHE_DIR_NAME / BUILD_ARTIFACTS_DIR_NAME / "blobs"), check_owner=True)
        _ensure_relative_dir(checkout_fd, _TMP_PARTS, label=str(checkout / BUILD_CACHE_DIR_NAME / BUILD_ARTIFACTS_DIR_NAME / "tmp"), check_owner=True)
        _ensure_relative_dir(checkout_fd, _GENERATED_PARENT_PARTS, label=str(checkout / GENERATED_DIR_NAME), check_owner=False, chmod_existing=False)
        _ensure_relative_dir(checkout_fd, _GENERATED_PARTS, label=str(checkout / GENERATED_DIR_NAME / BUILD_ARTIFACTS_DIR_NAME), check_owner=True)
    finally:
        os.close(checkout_fd)

    return BuildCachePaths(
        checkout_root=checkout,
        persistent_root=resolve_build_cache_root(checkout),
        blobs_root=resolve_build_blobs_root(checkout),
        tmp_root=resolve_build_tmp_root(checkout),
        generated_root=resolve_build_generated_root(checkout),
    )


# ═══════════════════════════════════════════════════════════════════════
# Verified-blob publication
# ═══════════════════════════════════════════════════════════════════════


def publish_verified_blob(
    identity: DigestIdentity,
    data: bytes,
    *,
    checkout_root: str | Path,
) -> Path:
    """Verify *data* and atomically publish it as an immutable ``0444`` blob.

    The payload digest is verified **before** any filesystem work, so a
    mismatch leaves the checkout-local cache completely untouched.  After
    atomic publication the blob is re-verified for containment, type,
    permissions, and digest before its path is returned.
    """
    if not isinstance(identity, DigestIdentity):
        raise BuildCacheError("identity must be a DigestIdentity")
    if not isinstance(data, bytes):
        raise BuildCacheError("data must be bytes")

    actual = hashlib.new(identity.algorithm, data).digest()
    if actual != identity.digest_bytes:
        raise BuildCacheError(
            f"digest mismatch: expected {identity.sri()}, got "
            f"{identity.algorithm}-{actual.hex()}"
        )

    paths = prepare_build_cache(checkout_root)
    blob_path = build_blob_path(paths.blobs_root, identity)
    checkout_fd = _open_checkout_fd(paths.checkout_root)
    blobs_fd = tmp_fd = algorithm_fd = fd = None
    temp_name = f".publish-{os.urandom(16).hex()}"
    try:
        blobs_fd = _open_relative_dir(checkout_fd, _BLOBS_PARTS, create=False)
        tmp_fd = _open_relative_dir(checkout_fd, _TMP_PARTS, create=False)
        if blobs_fd is None or tmp_fd is None:
            raise BuildCacheError("prepared build-cache directories disappeared")
        try:
            algorithm_fd = os.open(identity.algorithm, _DIR_FLAGS, dir_fd=blobs_fd)
        except FileNotFoundError:
            os.mkdir(identity.algorithm, 0o700, dir_fd=blobs_fd)
            os.chmod(identity.algorithm, 0o700, dir_fd=blobs_fd, follow_symlinks=False)
            algorithm_fd = os.open(identity.algorithm, _DIR_FLAGS, dir_fd=blobs_fd)
        st = os.fstat(algorithm_fd)
        if not _stat.S_ISDIR(st.st_mode) or st.st_uid != os.geteuid():
            raise BuildCacheError("unsafe algorithm directory")
        fd = os.open(temp_name, os.O_CREAT | os.O_EXCL | os.O_RDWR | getattr(os, "O_NOFOLLOW", 0), 0o600, dir_fd=tmp_fd)
        with os.fdopen(fd, "wb", closefd=False) as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.fchmod(fd, 0o444)
        os.lseek(fd, 0, os.SEEK_SET)
        check = hashlib.new(identity.algorithm)
        while True:
            chunk = os.read(fd, 1024 * 1024)
            if not chunk:
                break
            check.update(chunk)
        st = os.fstat(fd)
        if not _stat.S_ISREG(st.st_mode) or (st.st_mode & 0o777) != 0o444:
            raise BuildCacheError("temporary published blob has unsafe type or mode")
        if check.digest() != identity.digest_bytes:
            raise BuildCacheError("temporary published blob digest mismatch")
        os.replace(temp_name, blob_path.name, src_dir_fd=tmp_fd, dst_dir_fd=algorithm_fd)
    except BaseException:
        if fd is not None:
            os.close(fd)
            fd = None
        try:
            if tmp_fd is not None: os.unlink(temp_name, dir_fd=tmp_fd)
        except OSError: pass
        raise
    finally:
        for value in (fd, algorithm_fd, blobs_fd, tmp_fd, checkout_fd):
            if value is not None:
                os.close(value)
    _verify_published_blob(identity, paths)
    return blob_path


def _verify_published_blob(identity: DigestIdentity, paths: BuildCachePaths) -> None:
    """Re-verify one published blob through stable no-follow descriptors.

    Every component is derived from *identity* and opened relative to the
    checkout descriptor.  The verification therefore cannot be redirected by
    a replacement of a pathname between a preliminary check and file read.
    """
    checkout_fd = blobs_fd = algorithm_fd = blob_fd = None
    algorithm = identity.algorithm
    filename = identity.hex_digest() + BLOB_EXTENSION
    try:
        checkout_fd = _open_checkout_fd(paths.checkout_root)
        blobs_fd = _open_relative_dir(checkout_fd, _BLOBS_PARTS, create=False)
        if blobs_fd is None:
            raise BuildCacheError("published blob directory disappeared")
        try:
            algorithm_fd = os.open(algorithm, _DIR_FLAGS, dir_fd=blobs_fd)
        except OSError as exc:
            raise BuildCacheError(
                f"published blob algorithm directory {algorithm!r} is unsafe or missing: {exc}"
            ) from exc
        algorithm_stat = os.fstat(algorithm_fd)
        if not _stat.S_ISDIR(algorithm_stat.st_mode):
            raise BuildCacheError("published blob algorithm entry is not a directory")
        if algorithm_stat.st_uid != os.geteuid():
            raise BuildCacheError("published blob algorithm directory is not owned by the invoking user")

        try:
            blob_fd = os.open(
                filename,
                os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0),
                dir_fd=algorithm_fd,
            )
        except OSError as exc:
            raise BuildCacheError(
                f"published blob {algorithm}/{filename} is unsafe or missing: {exc}"
            ) from exc
        blob_stat = os.fstat(blob_fd)
        if not _stat.S_ISREG(blob_stat.st_mode):
            raise BuildCacheError(f"published blob {algorithm}/{filename} is not a regular file")
        if _stat.S_IMODE(blob_stat.st_mode) != 0o444:
            raise BuildCacheError(
                f"published blob {algorithm}/{filename} has mode "
                f"{oct(_stat.S_IMODE(blob_stat.st_mode))}, expected 0o444"
            )
        if blob_stat.st_uid != os.geteuid():
            raise BuildCacheError("published blob is not owned by the invoking user")

        digest = hashlib.new(identity.algorithm)
        while chunk := os.read(blob_fd, 64 * 1024):
            digest.update(chunk)
        if digest.digest() != identity.digest_bytes:
            raise BuildCacheError(f"published blob {algorithm}/{filename} digest mismatch")
    finally:
        for fd in (blob_fd, algorithm_fd, blobs_fd, checkout_fd):
            if fd is not None:
                os.close(fd)
