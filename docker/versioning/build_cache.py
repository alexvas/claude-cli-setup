"""External constructor-project build-cache boundary.

Persistent build artifact state and transaction snapshots live beneath the
invoking user's private external namespace, keyed by the canonical selected
constructor-project path.  Constructor state is never created in a checkout
or workspace.

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
import stat as _stat
import sys
import time
from dataclasses import dataclass
from pathlib import Path

from docker.versioning.cache_storage import resolve_default_root
from docker.versioning.digest_identity import DigestIdentity
from docker.versioning.project_state import ProjectState, ProjectStateError, resolve_project_state

BLOB_EXTENSION = ".blob"
"""Content-addressed build-blob filename extension."""

UNCOMMITTED_TTL_SECONDS = 2_592_000
"""Fixed retention period for verified blobs not in the live build set."""


class BuildCacheError(ValueError):
    """Invalid or unsafe checkout-local build-cache configuration."""


@dataclass(frozen=True)
class BuildCachePaths:
    """Resolved project identity and prepared external project-state roots."""

    checkout_root: Path
    """Normalized selected constructor-project path; never a cache path."""

    namespace_root: Path
    """Verified external namespace for descriptor-relative cache operations."""

    persistent_root: Path
    """``<namespace>/build-artifacts``."""

    blobs_root: Path
    """``<namespace>/build-artifacts/blobs``."""

    tmp_root: Path
    """``<namespace>/build-artifacts/tmp``."""

    generated_root: Path
    """``<namespace>/transactions``."""

    markers_root: Path
    """Owner-private markers for uncommitted verified blobs."""


_DIR_FLAGS = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)


# ═══════════════════════════════════════════════════════════════════════
# Lexical path resolution (no filesystem access)
# ═══════════════════════════════════════════════════════════════════════


def _normalize_checkout(checkout_root: str | Path) -> Path:
    return Path(os.path.abspath(os.fspath(checkout_root)))


def _resolve_cache_root(cache_root: str | Path | None) -> Path:
    """Return the cache root exactly as ``resolve_project_state`` derives it."""
    if cache_root is not None:
        return Path(cache_root)
    return resolve_default_root(os.environ.get("XDG_CACHE_HOME"), home=Path.home())


def resolve_build_cache_root(checkout_root: str | Path, *, cache_root: str | Path | None = None) -> Path:
    """Return the selected project's external persistent artifact root."""
    try:
        return resolve_project_state(checkout_root, cache_root=cache_root, create=False).build_artifacts_root
    except ProjectStateError as exc:
        raise BuildCacheError(str(exc)) from exc


def resolve_build_blobs_root(checkout_root: str | Path, *, cache_root: str | Path | None = None) -> Path:
    return resolve_build_cache_root(checkout_root, cache_root=cache_root) / "blobs"


def resolve_build_tmp_root(checkout_root: str | Path, *, cache_root: str | Path | None = None) -> Path:
    return resolve_build_cache_root(checkout_root, cache_root=cache_root) / "tmp"


def resolve_build_generated_root(checkout_root: str | Path, *, cache_root: str | Path | None = None) -> Path:
    """Return the selected project's external transaction root."""
    try:
        return resolve_project_state(checkout_root, cache_root=cache_root, create=False).transactions_root
    except ProjectStateError as exc:
        raise BuildCacheError(str(exc)) from exc


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


def _require_algorithm_dir(algorithm_fd: int, algorithm: str) -> None:
    """Require an opened blob algorithm directory to be a private ``0700`` dir.

    Rejects a non-directory, foreign-owned, or otherwise incorrect (including
    permissive) mode without repairing it; the caller must already hold the
    descriptor opened no-follow.
    """
    st = os.fstat(algorithm_fd)
    if not _stat.S_ISDIR(st.st_mode):
        raise BuildCacheError(
            f"build blob algorithm {algorithm!r} entry is not a directory")
    if st.st_uid != os.geteuid():
        raise BuildCacheError(
            f"build blob algorithm {algorithm!r} directory is not owned by the invoking user")
    if _stat.S_IMODE(st.st_mode) != 0o700:
        raise BuildCacheError(
            f"build blob algorithm {algorithm!r} directory has mode "
            f"{oct(_stat.S_IMODE(st.st_mode))}, expected 0o700")


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


# Relative component paths within the verified external namespace.
_BUILD_ARTIFACTS_NAME = "build-artifacts"
_BLOBS_NAME = "blobs"
_TMP_NAME = "tmp"
_MARKERS_NAME = "uncommitted"
_TRANSACTIONS_NAME = "transactions"

_CACHE_PARTS = (_BUILD_ARTIFACTS_NAME,)
_PERSISTENT_PARTS = _CACHE_PARTS
_BLOBS_PARTS = (_BUILD_ARTIFACTS_NAME, _BLOBS_NAME)
_TMP_PARTS = (_BUILD_ARTIFACTS_NAME, _TMP_NAME)
_GENERATED_PARENT_PARTS = (_TRANSACTIONS_NAME,)
_GENERATED_PARTS = _GENERATED_PARENT_PARTS
_MARKERS_PARTS = (_BUILD_ARTIFACTS_NAME, _MARKERS_NAME)


def prepare_build_cache(checkout_root: str | Path, *, cache_root: str | Path | None = None,
                        project_state: ProjectState | None = None) -> BuildCachePaths:
    """Prepare private external state for the selected constructor project.

    The source project is read/traversed only; every created component is
    relative to the verified external namespace. Existing unsafe state fails
    closed before any child is created.
    """
    project = _normalize_checkout(checkout_root)
    validate_host_owner_traversal(project)
    try:
        state = project_state or resolve_project_state(project, cache_root=cache_root, create=True)
        if state.project_path != project.resolve(strict=True):
            raise ProjectStateError("project state belongs to a different constructor project")
    except ProjectStateError as exc:
        raise BuildCacheError(str(exc)) from exc
    namespace = state.namespace
    checkout_fd = _open_checkout_fd(namespace)
    try:
        for parts in (_CACHE_PARTS, _BLOBS_PARTS, _TMP_PARTS,
                      _GENERATED_PARENT_PARTS, _MARKERS_PARTS):
            _validate_relative_dir(checkout_fd, parts, label=str(namespace.joinpath(*parts)), check_owner=True)
        for parts in (_CACHE_PARTS, _BLOBS_PARTS, _TMP_PARTS,
                      _GENERATED_PARENT_PARTS, _MARKERS_PARTS):
            _ensure_relative_dir(checkout_fd, parts, label=str(namespace.joinpath(*parts)), check_owner=True)
    finally:
        os.close(checkout_fd)
    return BuildCachePaths(
        checkout_root=project,
        namespace_root=namespace,
        persistent_root=state.build_artifacts_root,
        blobs_root=state.build_artifacts_root / "blobs",
        tmp_root=state.build_artifacts_root / "tmp",
        generated_root=state.transactions_root,
        markers_root=state.build_artifacts_root / "uncommitted",
    )


@dataclass
class BuildCacheState:
    """Verified descriptors retained for descriptor-relative operations.

    The descriptors are opened no-follow from the verified namespace after
    ``prepare_build_cache`` has validated and created every child.  Mutable
    control state is always addressed through these retained descriptors,
    never by reconstructing a ``Path`` from a previously validated path.
    """

    paths: BuildCachePaths
    persistent_fd: int
    blobs_fd: int
    tmp_fd: int
    markers_fd: int
    transactions_fd: int

    def close(self) -> None:
        for fd in (self.transactions_fd, self.markers_fd, self.tmp_fd,
                   self.blobs_fd, self.persistent_fd):
            os.close(fd)


def _open_validated_child(parent_fd: int, name: str, *, label: str) -> int:
    """Open *name* beneath *parent_fd* no-follow and require a private dir."""
    try:
        fd = os.open(name, _DIR_FLAGS, dir_fd=parent_fd)
    except OSError as exc:
        raise BuildCacheError(f"unsafe build-cache {label} directory: {exc}") from exc
    try:
        st = os.fstat(fd)
        if (not _stat.S_ISDIR(st.st_mode)
                or st.st_uid != os.geteuid()
                or _stat.S_IMODE(st.st_mode) != 0o700):
            raise BuildCacheError(f"unsafe build-cache {label} directory")
        return fd
    except BaseException:
        os.close(fd)
        raise


def open_build_cache_state(
    checkout_root: str | Path,
    *,
    cache_root: str | Path | None = None,
    project_state: ProjectState | None = None,
) -> BuildCacheState:
    """Prepare the namespace and retain verified no-follow child descriptors."""
    paths = prepare_build_cache(checkout_root, cache_root=cache_root, project_state=project_state)
    namespace_fd = _open_checkout_fd(paths.namespace_root)
    opened: list[int] = []
    try:
        persistent_fd = _open_validated_child(
            namespace_fd, _BUILD_ARTIFACTS_NAME, label=_BUILD_ARTIFACTS_NAME)
        opened.append(persistent_fd)
        blobs_fd = _open_validated_child(
            persistent_fd, _BLOBS_NAME, label=_BLOBS_NAME)
        opened.append(blobs_fd)
        tmp_fd = _open_validated_child(
            persistent_fd, _TMP_NAME, label=_TMP_NAME)
        opened.append(tmp_fd)
        markers_fd = _open_validated_child(
            persistent_fd, _MARKERS_NAME, label=_MARKERS_NAME)
        opened.append(markers_fd)
        transactions_fd = _open_validated_child(
            namespace_fd, _TRANSACTIONS_NAME, label=_TRANSACTIONS_NAME)
        opened.append(transactions_fd)
    except BaseException:
        for fd in reversed(opened):
            os.close(fd)
        raise
    finally:
        os.close(namespace_fd)
    return BuildCacheState(
        paths=paths,
        persistent_fd=persistent_fd,
        blobs_fd=blobs_fd,
        tmp_fd=tmp_fd,
        markers_fd=markers_fd,
        transactions_fd=transactions_fd,
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
    cache_root: str | Path | None = None,
    project_state: ProjectState | None = None,
) -> Path:
    """Verify *data* and atomically publish it as an immutable ``0444`` blob.

    The payload digest is verified **before** any filesystem work, so a
    mismatch leaves the checkout-local cache completely untouched.  After
    atomic publication the blob is re-verified for containment, type,
    permissions, and digest before its path is returned.
    """
    _validate_publication_inputs(identity, data)

    paths = prepare_build_cache(checkout_root, cache_root=cache_root, project_state=project_state)
    blob_path = build_blob_path(paths.blobs_root, identity)
    checkout_fd = _open_checkout_fd(paths.namespace_root)
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
            # Pin the freshly created algorithm directory to exactly 0700
            # before opening; os.mkdir's mode is masked by the ambient umask.
            os.chmod(identity.algorithm, 0o700, dir_fd=blobs_fd, follow_symlinks=False)
            try:
                algorithm_fd = os.open(identity.algorithm, _DIR_FLAGS, dir_fd=blobs_fd)
            except OSError as exc:
                raise BuildCacheError(
                    f"build blob algorithm directory {identity.algorithm!r} is unsafe: {exc}"
                ) from exc
        except OSError as exc:
            raise BuildCacheError(
                f"build blob algorithm directory {identity.algorithm!r} is unsafe: {exc}"
            ) from exc
        _require_algorithm_dir(algorithm_fd, identity.algorithm)
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


def _validate_blob_descriptor(alg_fd: int, filename: str, identity: DigestIdentity) -> None:
    """Validate one immutable blob descriptor-relatively without following links.

    Requires a regular file owned by the invoking user with mode exactly
    ``0444`` whose content digest matches *identity*.  *alg_fd* must be the
    verified algorithm directory descriptor; the blob is opened no-follow by
    name beneath it.
    """
    try:
        blob_fd = os.open(
            filename,
            os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0),
            dir_fd=alg_fd,
        )
    except OSError as exc:
        raise BuildCacheError(
            f"published blob {identity.algorithm}/{filename} is unsafe or missing: {exc}"
        ) from exc
    try:
        blob_stat = os.fstat(blob_fd)
        if not _stat.S_ISREG(blob_stat.st_mode):
            raise BuildCacheError(f"published blob {identity.algorithm}/{filename} is not a regular file")
        if _stat.S_IMODE(blob_stat.st_mode) != 0o444:
            raise BuildCacheError(
                f"published blob {identity.algorithm}/{filename} has mode "
                f"{oct(_stat.S_IMODE(blob_stat.st_mode))}, expected 0o444"
            )
        if blob_stat.st_uid != os.geteuid():
            raise BuildCacheError("published blob is not owned by the invoking user")
        digest = hashlib.new(identity.algorithm)
        while chunk := os.read(blob_fd, 64 * 1024):
            digest.update(chunk)
        if digest.digest() != identity.digest_bytes:
            raise BuildCacheError(f"published blob {identity.algorithm}/{filename} digest mismatch")
    finally:
        os.close(blob_fd)


def _verify_published_blob(identity: DigestIdentity, paths: BuildCachePaths) -> None:
    """Re-verify one published blob through stable no-follow descriptors.

    Every component is derived from *identity* and opened relative to the
    checkout descriptor.  The verification therefore cannot be redirected by
    a replacement of a pathname between a preliminary check and file read.
    """
    checkout_fd = blobs_fd = algorithm_fd = None
    algorithm = identity.algorithm
    filename = identity.hex_digest() + BLOB_EXTENSION
    try:
        checkout_fd = _open_checkout_fd(paths.namespace_root)
        blobs_fd = _open_relative_dir(checkout_fd, _BLOBS_PARTS, create=False)
        if blobs_fd is None:
            raise BuildCacheError("published blob directory disappeared")
        try:
            algorithm_fd = os.open(algorithm, _DIR_FLAGS, dir_fd=blobs_fd)
        except OSError as exc:
            raise BuildCacheError(
                f"published blob algorithm directory {algorithm!r} is unsafe or missing: {exc}"
            ) from exc
        _require_algorithm_dir(algorithm_fd, algorithm)
        _validate_blob_descriptor(algorithm_fd, filename, identity)
    finally:
        for fd in (algorithm_fd, blobs_fd, checkout_fd):
            if fd is not None:
                os.close(fd)


class BuildTransactionError(BuildCacheError):
    """A checkout-local build transaction cannot safely proceed."""


class CheckoutBuildLock:
    """The exclusive owner token for one checkout build transaction.

    Ownership is bound to the canonical constructor-project identity and the
    selected external cache namespace.  The lock cannot be reused for another
    project or another cache root.
    """

    def __init__(self, fd: int, checkout_root: Path, cache_root: Path,
                 namespace: Path, project_state: ProjectState) -> None:
        self._fd: int | None = fd
        self._checkout_root = checkout_root
        self._cache_root = cache_root
        self._namespace = namespace
        self._project_state = project_state

    @property
    def checkout_root(self) -> Path:
        return self._checkout_root

    @property
    def cache_root(self) -> Path:
        return self._cache_root

    @property
    def namespace(self) -> Path:
        return self._namespace

    @property
    def project_state(self) -> ProjectState:
        return self._project_state

    def assert_held_for(self, checkout_root: str | Path, *,
                        cache_root: str | Path | None = None) -> None:
        if self._fd is None:
            raise BuildTransactionError("a live checkout build lock is required")
        try:
            canonical = Path(checkout_root).resolve(strict=True)
        except OSError as exc:
            raise BuildTransactionError(
                "the checkout build lock belongs to a different constructor project"
            ) from exc
        if canonical != self._checkout_root:
            raise BuildTransactionError(
                "the checkout build lock belongs to a different constructor project"
            )
        if _resolve_cache_root(cache_root) != self._cache_root:
            raise BuildTransactionError(
                "the checkout build lock belongs to a different cache namespace"
            )

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


def _bootstrap_lock_parent(checkout_root: str | Path, *, cache_root: str | Path | None = None) -> tuple[ProjectState, int]:
    """Open the lock parent, creating only missing private path components.

    Existing cache entries are deliberately not chmodded or otherwise
    repaired here.  Contenders must be rejected by the lock before cache
    validation/mutation is attempted; the owner validates them afterwards.
    """
    checkout = _normalize_checkout(checkout_root)
    validate_host_owner_traversal(checkout)
    try:
        state = resolve_project_state(checkout, cache_root=cache_root, create=True, validate_children=False)
    except ProjectStateError as exc:
        raise BuildTransactionError(str(exc)) from exc
    checkout_fd = _open_checkout_fd(state.namespace)
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
        return state, current_fd
    except BaseException:
        if current_fd != checkout_fd:
            os.close(current_fd)
        raise
    finally:
        os.close(checkout_fd)


def acquire_checkout_build_lock(checkout_root: str | Path, *, cache_root: str | Path | None = None) -> CheckoutBuildLock:
    """Acquire the single non-blocking checkout transaction lock first.

    The lock file lives under the selected project's external namespace and
    is never created inside the checkout.  The returned token is bound to the
    canonical project identity and the selected cache namespace.
    """
    import fcntl
    state, parent_fd = _bootstrap_lock_parent(checkout_root, cache_root=cache_root)
    checkout = state.project_path
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
        prepare_build_cache(checkout, cache_root=cache_root, project_state=state)
        return CheckoutBuildLock(fd, checkout, state.cache_root, state.namespace, state)
    except BaseException:
        if fd is not None:
            os.close(fd)
        raise
    finally:
        os.close(parent_fd)


def _key(identity: DigestIdentity) -> str:
    return f"{identity.algorithm}:{identity.hex_digest()}"


_MANIFEST_NAME = "committed-build.json"


def _marker_name(identity: DigestIdentity) -> str:
    return _key(identity) + ".json"


def _require_control_name(name: object) -> str:
    """Require a single, non-empty, non-special basename for a control file."""
    if (
        not isinstance(name, str)
        or not name
        or name in (".", "..")
        or os.path.isabs(name)
        or "/" in name
        or (os.sep != "/" and os.sep in name)
        or Path(name).name != name
    ):
        raise BuildTransactionError(f"unsafe transaction state file name: {name!r}")
    return name


def _atomic_json_at(dir_fd: int, name: str, value: object) -> None:
    """Durably publish deterministic JSON bytes as *name* beneath *dir_fd*.

    *name* must be a single basename.  The bytes are written to a private
    temporary file created descriptor-relatively beneath the same directory,
    fsynced, and atomically renamed into place before the directory itself
    is fsynced.  On failure only the temporary entry is removed; an existing
    destination is left untouched.
    """
    _require_control_name(name)
    payload = json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    tmp_name = f".transaction-{os.urandom(16).hex()}"
    tmp_fd = -1
    try:
        tmp_fd = os.open(
            tmp_name,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
            0o600,
            dir_fd=dir_fd,
        )
        try:
            os.fchmod(tmp_fd, 0o600)
            info = os.fstat(tmp_fd)
            if (not _stat.S_ISREG(info.st_mode)
                    or info.st_uid != os.geteuid()
                    or info.st_nlink != 1
                    or _stat.S_IMODE(info.st_mode) != 0o600):
                raise BuildTransactionError("unsafe temporary transaction state file")
            view = memoryview(payload)
            while view:
                written = os.write(tmp_fd, view)
                if written <= 0:
                    raise OSError("short write while publishing transaction state")
                view = view[written:]
            os.fsync(tmp_fd)
        except BaseException:
            os.close(tmp_fd)
            tmp_fd = -1
            raise
        os.close(tmp_fd)
        tmp_fd = -1
        _validate_control_destination(dir_fd, name)
        os.replace(tmp_name, name, src_dir_fd=dir_fd, dst_dir_fd=dir_fd)
        os.fsync(dir_fd)
    except BaseException:
        try:
            os.unlink(tmp_name, dir_fd=dir_fd)
        except FileNotFoundError:
            pass
        raise
    finally:
        if tmp_fd >= 0:
            os.close(tmp_fd)


def _validate_control_destination(dir_fd: int, name: str) -> None:
    """Reject an unsafe existing destination before it is replaced.

    ``os.replace`` itself never follows a symlink, but a caller must not
    silently overwrite an entry that has been swapped for a link, a foreign
    file, or a multiply linked file since the transaction validated it.
    """
    try:
        fd = os.open(name, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0), dir_fd=dir_fd)
    except FileNotFoundError:
        return
    except OSError as exc:
        raise BuildTransactionError(f"unsafe transaction state file: {name}") from exc
    try:
        info = os.fstat(fd)
        if (not _stat.S_ISREG(info.st_mode)
                or info.st_uid != os.geteuid()
                or info.st_nlink != 1
                or _stat.S_IMODE(info.st_mode) != 0o600):
            raise BuildTransactionError(f"unsafe transaction state file: {name}")
    finally:
        os.close(fd)


def publish_uncommitted_blob(
    identity: DigestIdentity,
    data: bytes,
    *,
    checkout_root: str | Path,
    lock: CheckoutBuildLock,
    verified_at: float | None = None,
    cache_root: str | Path | None = None,
    project_state: ProjectState | None = None,
) -> Path:
    """Atomically mark then publish a verified uncommitted blob under one lock.

    The marker is deliberately durable before publication: an interruption
    cannot strand a verified blob without retention state.  Every failure
    retains the marker: maintenance later removes it when no safe blob exists.
    """
    lock.assert_held_for(checkout_root, cache_root=cache_root)
    _validate_publication_inputs(identity, data)
    mark_uncommitted_blob(identity, checkout_root, lock=lock, verified_at=verified_at,
                          cache_root=cache_root, project_state=project_state)
    return publish_verified_blob(identity, data, checkout_root=checkout_root,
                                 cache_root=cache_root, project_state=project_state)


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
    cache_root: str | Path | None = None,
    project_state: ProjectState | None = None,
) -> None:
    """Atomically record the publication time of a verified uncommitted blob."""
    lock.assert_held_for(checkout_root, cache_root=cache_root)
    timestamp = _validate_marker_timestamp(
        time.time() if verified_at is None else verified_at, label="verified_at",
    )
    state = open_build_cache_state(checkout_root, cache_root=cache_root, project_state=project_state)
    try:
        _atomic_json_at(state.markers_fd, _marker_name(identity), {"verified_at": timestamp})
    finally:
        state.close()


def _read_json_no_follow_at(dir_fd: int, name: str, *, label: str) -> object:
    """Read a private regular JSON file relative to a verified descriptor.

    The entry is opened ``O_NOFOLLOW`` beneath *dir_fd* and validated for
    regular-file type, invoking-user ownership, single link count, and
    ``0600`` mode before any byte is read.
    """
    _require_control_name(name)
    fd = os.open(name, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0), dir_fd=dir_fd)
    try:
        info = os.fstat(fd)
        if (not _stat.S_ISREG(info.st_mode)
                or info.st_uid != os.geteuid()
                or info.st_nlink != 1
                or _stat.S_IMODE(info.st_mode) != 0o600):
            raise BuildTransactionError(f"unsafe transaction state file: {label}")
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


def _read_live_set(state: BuildCacheState) -> set[DigestIdentity]:
    try:
        value = _read_json_no_follow_at(
            state.persistent_fd, _MANIFEST_NAME, label=_MANIFEST_NAME)
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


def _unlink_entry(dir_fd: int, name: str) -> None:
    """Unlink *name* beneath *dir_fd* without following a replacement link."""
    _require_control_name(name)
    try:
        os.unlink(name, dir_fd=dir_fd)
    except FileNotFoundError:
        pass


def _remove_marker(state: BuildCacheState, identity: DigestIdentity) -> None:
    _unlink_entry(state.markers_fd, _marker_name(identity))


def _remove_blob_and_marker(state: BuildCacheState, identity: DigestIdentity) -> None:
    """Delete only entries derived from a validated canonical identity.

    The algorithm directory is validated before any deletion so a permissive
    or otherwise incorrect directory fails closed with the blob and its
    retention marker both left untouched.  A missing algorithm directory
    still drops the marker without error.
    """
    algorithm = identity.algorithm
    filename = identity.hex_digest() + BLOB_EXTENSION
    try:
        algorithm_fd = os.open(algorithm, _DIR_FLAGS, dir_fd=state.blobs_fd)
    except FileNotFoundError:
        _remove_marker(state, identity)
        return
    except OSError as exc:
        raise BuildCacheError(f"unsafe blob algorithm directory {algorithm!r}: {exc}") from exc
    try:
        _require_algorithm_dir(algorithm_fd, algorithm)
        _unlink_entry(algorithm_fd, filename)
    finally:
        os.close(algorithm_fd)
    _remove_marker(state, identity)


def commit_build_set(
    checkout_root: str | Path,
    identities: set[DigestIdentity],
    *,
    lock: CheckoutBuildLock,
    cache_root: str | Path | None = None,
    project_state: ProjectState | None = None,
) -> None:
    """Atomically replace the sole live set before deleting superseded blobs."""
    lock.assert_held_for(checkout_root, cache_root=cache_root)
    state = open_build_cache_state(checkout_root, cache_root=cache_root, project_state=project_state)
    try:
        old = _read_live_set(state)
        live = set(identities)
        try:
            for identity in live:
                _verify_published_blob(identity, state.paths)
        except BuildCacheError as exc:
            raise BuildTransactionError("cannot commit an unsafe or invalid build blob") from exc
        superseded = old - live
        # fsync + rename in _atomic_json_at is the commit point; no deletion
        # precedes it.
        _atomic_json_at(
            state.persistent_fd, _MANIFEST_NAME,
            {"blobs": sorted(_key(item) for item in live)},
        )
        for identity in live:
            _remove_marker(state, identity)
        for identity in superseded:
            _remove_blob_and_marker(state, identity)
    finally:
        state.close()


def maintain_uncommitted_blobs(
    checkout_root: str | Path,
    *,
    lock: CheckoutBuildLock,
    now: float | None = None,
    cache_root: str | Path | None = None,
    project_state: ProjectState | None = None,
) -> None:
    """Remove corrupt/partial and expired uncommitted state under the lock."""
    lock.assert_held_for(checkout_root, cache_root=cache_root)
    state = open_build_cache_state(checkout_root, cache_root=cache_root, project_state=project_state)
    try:
        current_time = _validate_marker_timestamp(
            time.time() if now is None else now, label="now",
        )
        live = _read_live_set(state)
        for name in sorted(os.listdir(state.markers_fd)):
            if not name.endswith(".json"):
                continue
            stem = name[: -len(".json")]
            try:
                identity = _identity_from_key(stem)
            except (ValueError, TypeError):
                # A malformed marker cannot safely name a blob; remove only it.
                _unlink_entry(state.markers_fd, name)
                continue
            if identity in live:
                # Committed blobs are TTL-immune; stale marker contents cannot
                # authorize deleting their sole live-set payload.
                _remove_marker(state, identity)
                continue
            try:
                value = _read_json_no_follow_at(state.markers_fd, name, label=name)
                if not isinstance(value, dict):
                    raise ValueError("marker is not an object")
                verified_at = _validate_marker_timestamp(value["verified_at"], label="verified_at")
            except (OSError, ValueError, KeyError, TypeError):
                _remove_blob_and_marker(state, identity)
                continue
            try:
                _verify_published_blob(identity, state.paths)
            except BuildCacheError:
                _remove_blob_and_marker(state, identity)
                continue
            if identity not in live and current_time - verified_at >= UNCOMMITTED_TTL_SECONDS:
                _remove_blob_and_marker(state, identity)
    finally:
        state.close()


_MAX_SNAPSHOT_DEPTH = 64


def _remove_snapshot_tree(parent_fd: int, name: str, *, depth: int) -> None:
    """Remove one abandoned snapshot entry without chmodding payload files.

    Symlinks and regular files are unlinked directly: unlinking requires
    write permission on the parent directory, never on the payload itself, so
    hard-linked snapshot payloads are never chmodded or otherwise mutated.
    Directories are reopened no-follow, their write permission is restored
    (directories only), and their children are removed recursively before the
    now-empty directory is removed.
    """
    _require_control_name(name)
    if depth <= 0:
        raise BuildTransactionError("abandoned snapshot tree is too deep")
    try:
        st = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
    except FileNotFoundError:
        return
    if _stat.S_ISLNK(st.st_mode) or not _stat.S_ISDIR(st.st_mode):
        try:
            os.unlink(name, dir_fd=parent_fd)
        except FileNotFoundError:
            pass
        return
    fd = os.open(name, _DIR_FLAGS, dir_fd=parent_fd)
    try:
        os.fchmod(fd, 0o700)
        for child in sorted(os.listdir(fd)):
            _remove_snapshot_tree(fd, child, depth=depth - 1)
    finally:
        os.close(fd)
    try:
        os.rmdir(name, dir_fd=parent_fd)
    except FileNotFoundError:
        pass


def recover_abandoned_snapshots(
    checkout_root: str | Path, *, lock: CheckoutBuildLock,
    cache_root: str | Path | None = None,
    project_state: ProjectState | None = None,
) -> None:
    """Remove snapshots found after exclusive ownership has been acquired."""
    lock.assert_held_for(checkout_root, cache_root=cache_root)
    state = open_build_cache_state(checkout_root, cache_root=cache_root, project_state=project_state)
    try:
        for name in sorted(os.listdir(state.transactions_fd)):
            _remove_snapshot_tree(state.transactions_fd, name, depth=_MAX_SNAPSHOT_DEPTH)
    finally:
        state.close()
