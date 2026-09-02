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
import json
import math
import os
import shutil
import stat as _stat
import sys
import tempfile
import time
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

UNCOMMITTED_TTL_SECONDS = 2_592_000
"""Fixed retention period for verified blobs not in the live build set."""


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

    markers_root: Path
    """Owner-private markers for uncommitted verified blobs."""


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
_MARKERS_PARTS = (BUILD_CACHE_DIR_NAME, BUILD_ARTIFACTS_DIR_NAME, "uncommitted")


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
        _validate_relative_dir(checkout_fd, _MARKERS_PARTS, label=str(checkout / BUILD_CACHE_DIR_NAME / BUILD_ARTIFACTS_DIR_NAME / "uncommitted"), check_owner=True)

        # ── then create/secure the validated set ──
        _ensure_relative_dir(checkout_fd, _CACHE_PARTS, label=str(checkout / BUILD_CACHE_DIR_NAME), check_owner=True)
        _ensure_relative_dir(checkout_fd, _PERSISTENT_PARTS, label=str(checkout / BUILD_CACHE_DIR_NAME / BUILD_ARTIFACTS_DIR_NAME), check_owner=True)
        _ensure_relative_dir(checkout_fd, _BLOBS_PARTS, label=str(checkout / BUILD_CACHE_DIR_NAME / BUILD_ARTIFACTS_DIR_NAME / "blobs"), check_owner=True)
        _ensure_relative_dir(checkout_fd, _TMP_PARTS, label=str(checkout / BUILD_CACHE_DIR_NAME / BUILD_ARTIFACTS_DIR_NAME / "tmp"), check_owner=True)
        _ensure_relative_dir(checkout_fd, _GENERATED_PARENT_PARTS, label=str(checkout / GENERATED_DIR_NAME), check_owner=False, chmod_existing=False)
        _ensure_relative_dir(checkout_fd, _GENERATED_PARTS, label=str(checkout / GENERATED_DIR_NAME / BUILD_ARTIFACTS_DIR_NAME), check_owner=True)
        _ensure_relative_dir(checkout_fd, _MARKERS_PARTS, label=str(checkout / BUILD_CACHE_DIR_NAME / BUILD_ARTIFACTS_DIR_NAME / "uncommitted"), check_owner=True)
    finally:
        os.close(checkout_fd)

    return BuildCachePaths(
        checkout_root=checkout,
        persistent_root=resolve_build_cache_root(checkout),
        blobs_root=resolve_build_blobs_root(checkout),
        tmp_root=resolve_build_tmp_root(checkout),
        generated_root=resolve_build_generated_root(checkout),
        markers_root=resolve_build_cache_root(checkout) / "uncommitted",
    )


# ═══════════════════════════════════════════════════════════════════════
# Verified-blob publication
# ═══════════════════════════════════════════════════════════════════════


def _validate_publication_inputs(identity: DigestIdentity, data: bytes) -> None:
    """Reject invalid publication inputs before any cache state is changed."""
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
    _validate_publication_inputs(identity, data)

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


class BuildTransactionError(BuildCacheError):
    """A checkout-local build transaction cannot safely proceed."""


class CheckoutBuildLock:
    """The exclusive owner token for one checkout build transaction."""

    def __init__(self, fd: int, checkout_root: Path) -> None:
        self._fd: int | None = fd
        self._checkout_root = checkout_root

    def assert_held_for(self, checkout_root: str | Path) -> None:
        if self._fd is None or _normalize_checkout(checkout_root) != self._checkout_root:
            raise BuildTransactionError("a live checkout build lock is required")

    def release(self) -> None:
        if self._fd is not None:
            import fcntl
            fcntl.flock(self._fd, fcntl.LOCK_UN)
            os.close(self._fd)
            self._fd = None

    def __enter__(self) -> "CheckoutBuildLock":
        return self

    def __exit__(self, *_: object) -> None:
        self.release()


def _bootstrap_lock_parent(checkout_root: str | Path) -> tuple[Path, int]:
    """Open the lock parent, creating only missing private path components.

    Existing cache entries are deliberately not chmodded or otherwise
    repaired here.  Contenders must be rejected by the lock before cache
    validation/mutation is attempted; the owner validates them afterwards.
    """
    checkout = _normalize_checkout(checkout_root)
    validate_host_owner_traversal(checkout)
    checkout_fd = _open_checkout_fd(checkout)
    current_fd = checkout_fd
    try:
        for part in _PERSISTENT_PARTS:
            try:
                child_fd = os.open(part, _DIR_FLAGS, dir_fd=current_fd)
            except FileNotFoundError:
                try:
                    os.mkdir(part, 0o700, dir_fd=current_fd)
                except FileExistsError:
                    # Another first build won component creation; reopen it
                    # no-follow and validate it exactly like an existing one.
                    pass
                child_fd = os.open(part, _DIR_FLAGS, dir_fd=current_fd)
            info = os.fstat(child_fd)
            if not _stat.S_ISDIR(info.st_mode) or info.st_uid != os.geteuid():
                os.close(child_fd)
                raise BuildTransactionError(f"unsafe lock parent component: {part}")
            if current_fd != checkout_fd:
                os.close(current_fd)
            current_fd = child_fd
        return checkout, current_fd
    except BaseException:
        if current_fd != checkout_fd:
            os.close(current_fd)
        raise
    finally:
        os.close(checkout_fd)


def acquire_checkout_build_lock(checkout_root: str | Path) -> CheckoutBuildLock:
    """Acquire the single non-blocking checkout transaction lock first."""
    import fcntl
    checkout, parent_fd = _bootstrap_lock_parent(checkout_root)
    fd = None
    try:
        fd = os.open(
            "build.lock",
            os.O_CREAT | os.O_RDWR | getattr(os, "O_NOFOLLOW", 0),
            0o600,
            dir_fd=parent_fd,
        )
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            os.close(fd)
            fd = None
            raise BuildTransactionError("checkout already has an active build") from exc
        info = os.fstat(fd)
        if (
            not _stat.S_ISREG(info.st_mode)
            or info.st_uid != os.geteuid()
            or info.st_nlink != 1
        ):
            raise BuildTransactionError("unsafe checkout build lock")
        # Only the exclusive owner may repair the lock-file mode.
        os.fchmod(fd, 0o600)
        # The lock now serializes all validation and permitted cache repair.
        prepare_build_cache(checkout)
        return CheckoutBuildLock(fd, checkout)
    except BaseException:
        if fd is not None:
            os.close(fd)
        raise
    finally:
        os.close(parent_fd)


def _key(identity: DigestIdentity) -> str:
    return f"{identity.algorithm}:{identity.hex_digest()}"


def _manifest_path(paths: BuildCachePaths) -> Path:
    return paths.persistent_root / "committed-build.json"


def _cleanup_journal_path(paths: BuildCachePaths) -> Path:
    return paths.persistent_root / "pending-build-cleanup.json"


def _atomic_json(path: Path, value: object) -> None:
    fd, tmp = tempfile.mkstemp(prefix=".transaction-", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(value, stream, sort_keys=True, separators=(",", ":"))
            stream.flush(); os.fsync(stream.fileno())
        os.chmod(tmp, 0o600); os.replace(tmp, path)
        directory_fd = os.open(path.parent, _DIR_FLAGS); os.fsync(directory_fd); os.close(directory_fd)
    except BaseException:
        try: os.unlink(tmp)
        except FileNotFoundError: pass
        raise


def publish_uncommitted_blob(
    identity: DigestIdentity,
    data: bytes,
    *,
    checkout_root: str | Path,
    lock: CheckoutBuildLock,
    verified_at: float | None = None,
) -> Path:
    """Atomically mark then publish a verified uncommitted blob under one lock.

    The marker is deliberately durable before publication: an interruption
    cannot strand a verified blob without retention state.  Every failure
    retains the marker: maintenance later removes it when no safe blob exists.
    """
    lock.assert_held_for(checkout_root)
    _validate_publication_inputs(identity, data)
    mark_uncommitted_blob(identity, checkout_root, lock=lock, verified_at=verified_at)
    return publish_verified_blob(identity, data, checkout_root=checkout_root)


def _validate_marker_timestamp(value: object, *, label: str) -> float | int:
    """Require finite numeric marker and fake-clock timestamps."""
    if isinstance(value, bool):
        raise BuildCacheError(f"{label} must be a finite int or float")
    if isinstance(value, int):
        # Do not pass arbitrary JSON integers to math.isfinite(): conversion
        # to float raises OverflowError beyond the finite float range.
        if value.bit_length() > sys.float_info.max_exp:
            raise BuildCacheError(f"{label} is outside the finite timestamp range")
        return value
    if not isinstance(value, float) or not math.isfinite(value):
        raise BuildCacheError(f"{label} must be a finite int or float")
    return value


def mark_uncommitted_blob(
    identity: DigestIdentity,
    checkout_root: str | Path,
    *,
    lock: CheckoutBuildLock,
    verified_at: float | None = None,
) -> None:
    """Atomically record the publication time of a verified uncommitted blob."""
    lock.assert_held_for(checkout_root)
    timestamp = _validate_marker_timestamp(
        time.time() if verified_at is None else verified_at, label="verified_at",
    )
    paths = prepare_build_cache(checkout_root)
    _atomic_json(
        paths.markers_root / (_key(identity) + ".json"), {"verified_at": timestamp},
    )


def _read_json_no_follow(path: Path) -> object:
    """Read a private regular JSON file without following a replacement link."""
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    try:
        info = os.fstat(fd)
        if not _stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid():
            raise BuildTransactionError(f"unsafe transaction state file: {path.name}")
        chunks: list[bytes] = []
        while chunk := os.read(fd, 64 * 1024):
            chunks.append(chunk)
        return json.loads(b"".join(chunks))
    finally:
        os.close(fd)


def _identity_from_key(key: object) -> DigestIdentity:
    """Parse one manifest key and reject every noncanonical path-like form."""
    if not isinstance(key, str) or key.count(":") != 1:
        raise ValueError("blob key must be one canonical algorithm:digest string")
    algorithm, digest = key.split(":")
    if not algorithm or not digest or any(token in key for token in ("/", "\\", "..")):
        raise ValueError("blob key contains a path component")
    identity = DigestIdentity.from_hex(algorithm, digest)
    if key != _key(identity):
        raise ValueError("blob key is not canonical")
    return identity


def _read_live_set(manifest: Path) -> set[DigestIdentity]:
    try:
        value = _read_json_no_follow(manifest)
        if not isinstance(value, dict) or not isinstance(value.get("blobs"), list):
            raise ValueError("manifest is not an object with a blobs list")
        identities = [_identity_from_key(key) for key in value["blobs"]]
        if len(set(identities)) != len(identities):
            raise ValueError("manifest contains duplicate blob identities")
        return set(identities)
    except FileNotFoundError:
        return set()
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise BuildTransactionError("committed build manifest is corrupt") from exc


def _remove_blob_and_marker(paths: BuildCachePaths, identity: DigestIdentity) -> None:
    """Delete only paths derived from a validated canonical identity."""
    build_blob_path(paths.blobs_root, identity).unlink(missing_ok=True)
    (paths.markers_root / (_key(identity) + ".json")).unlink(missing_ok=True)


def _read_cleanup_journal(paths: BuildCachePaths) -> set[DigestIdentity]:
    try:
        value = _read_json_no_follow(_cleanup_journal_path(paths))
        if not isinstance(value, dict) or not isinstance(value.get("blobs"), list):
            raise ValueError("cleanup journal is not an object with a blobs list")
        identities = [_identity_from_key(key) for key in value["blobs"]]
        if len(set(identities)) != len(identities):
            raise ValueError("cleanup journal contains duplicate identities")
        return set(identities)
    except FileNotFoundError:
        return set()
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise BuildTransactionError("pending build cleanup journal is corrupt") from exc


def _remove_journal_durably(path: Path) -> None:
    path.unlink(missing_ok=True)
    directory_fd = os.open(path.parent, _DIR_FLAGS)
    try:
        os.fsync(directory_fd)
    finally:
        os.close(directory_fd)


def _recover_pending_cleanup(paths: BuildCachePaths) -> None:
    """Finish only journaled cleanup that is absent from the live set."""
    pending = _read_cleanup_journal(paths)
    if not pending:
        return
    live = _read_live_set(_manifest_path(paths))
    if pending & live:
        raise BuildTransactionError("cleanup journal includes a committed build blob")
    for identity in pending:
        _remove_blob_and_marker(paths, identity)
    _remove_journal_durably(_cleanup_journal_path(paths))


def commit_build_set(
    checkout_root: str | Path,
    identities: set[DigestIdentity],
    *,
    lock: CheckoutBuildLock,
) -> None:
    """Durably replace the sole live set before deleting superseded blobs."""
    lock.assert_held_for(checkout_root)
    paths = prepare_build_cache(checkout_root)
    old = _read_live_set(_manifest_path(paths))
    live = set(identities)
    try:
        for identity in live:
            _verify_published_blob(identity, paths)
    except BuildCacheError as exc:
        raise BuildTransactionError("cannot commit an unsafe or invalid build blob") from exc
    superseded = old - live
    if superseded:
        _atomic_json(
            _cleanup_journal_path(paths), {"blobs": sorted(_key(item) for item in superseded)},
        )
    # fsync + rename in _atomic_json is the commit point.  No deletion may
    # precede it: an interruption always leaves the previous durable live set.
    _atomic_json(_manifest_path(paths), {"blobs": sorted(_key(item) for item in live)})
    for identity in live:
        (paths.markers_root / (_key(identity) + ".json")).unlink(missing_ok=True)
    _recover_pending_cleanup(paths)


def maintain_uncommitted_blobs(
    checkout_root: str | Path,
    *,
    lock: CheckoutBuildLock,
    now: float | None = None,
) -> None:
    """Remove corrupt/partial and expired uncommitted state under the lock."""
    lock.assert_held_for(checkout_root)
    paths = prepare_build_cache(checkout_root)
    current_time = _validate_marker_timestamp(
        time.time() if now is None else now, label="now",
    )
    live = _read_live_set(_manifest_path(paths))
    for marker in paths.markers_root.glob("*.json"):
        try:
            identity = _identity_from_key(marker.stem)
        except (ValueError, TypeError):
            # A malformed marker cannot safely name a blob; remove only it.
            marker.unlink(missing_ok=True)
            continue
        if identity in live:
            # Committed blobs are TTL-immune; stale marker contents cannot
            # authorize deleting their sole live-set payload.
            marker.unlink(missing_ok=True)
            continue
        try:
            value = _read_json_no_follow(marker)
            if not isinstance(value, dict):
                raise ValueError("marker is not an object")
            verified_at = _validate_marker_timestamp(value["verified_at"], label="verified_at")
        except (OSError, ValueError, KeyError, TypeError):
            _remove_blob_and_marker(paths, identity)
            continue
        try:
            _verify_published_blob(identity, paths)
        except BuildCacheError:
            _remove_blob_and_marker(paths, identity)
            continue
        if identity not in live and current_time - verified_at >= UNCOMMITTED_TTL_SECONDS:
            _remove_blob_and_marker(paths, identity)


def recover_abandoned_snapshots(
    checkout_root: str | Path, *, lock: CheckoutBuildLock,
) -> None:
    """Remove snapshots found after exclusive ownership has been acquired."""
    lock.assert_held_for(checkout_root)
    paths = prepare_build_cache(checkout_root)
    for entry in paths.generated_root.iterdir():
        if entry.is_symlink() or entry.is_file():
            entry.unlink()
        elif entry.is_dir():
            shutil.rmtree(entry)


class CheckoutBuildTransaction:
    """One explicit locked state machine for build-cache maintenance/commit."""

    def __init__(self, checkout_root: str | Path, *, now: float | None = None) -> None:
        self.checkout_root = _normalize_checkout(checkout_root)
        self.now = now
        self.lock: CheckoutBuildLock | None = None

    def __enter__(self) -> "CheckoutBuildTransaction":
        self.lock = acquire_checkout_build_lock(self.checkout_root)
        try:
            recover_abandoned_snapshots(self.checkout_root, lock=self.lock)
            _recover_pending_cleanup(prepare_build_cache(self.checkout_root))
            maintain_uncommitted_blobs(self.checkout_root, lock=self.lock, now=self.now)
        except BaseException:
            self.lock.release()
            self.lock = None
            raise
        return self

    def publish_verified_blob(
        self, identity: DigestIdentity, data: bytes, *, verified_at: float | None = None,
    ) -> Path:
        if self.lock is None:
            raise BuildTransactionError("transaction is not active")
        return publish_uncommitted_blob(
            identity, data, checkout_root=self.checkout_root,
            lock=self.lock, verified_at=verified_at,
        )

    def commit(self, identities: set[DigestIdentity]) -> None:
        if self.lock is None:
            raise BuildTransactionError("transaction is not active")
        commit_build_set(self.checkout_root, identities, lock=self.lock)

    def __exit__(self, *_: object) -> None:
        if self.lock is not None:
            self.lock.release()
            self.lock = None
