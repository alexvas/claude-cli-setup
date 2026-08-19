"""Content-addressed cache contracts for selected runtime artifacts.

The host resolver already knows the exact reviewed URL and SRI integrity
for every selected runtime artifact before ``docker run``.  This module
provides the typed DTOs, protocol boundaries, and deterministic cache-key
derivation so the launcher can materialize, verify, and atomically publish
each selected blob on the host — without importing facade, parser,
presentation, Docker execution, or container-installer modules.
"""
from __future__ import annotations

import base64
import dataclasses
import os
import re
import stat as stat_module
import urllib.request
from typing import Iterator, Protocol


# ═══════════════════════════════════════════════════════════════════════
# Error hierarchy
# ═══════════════════════════════════════════════════════════════════════


@dataclasses.dataclass(frozen=True)
class ArtifactMaterializationError(Exception):
    """Structured failure during artifact materialization.

    Every failure mode carries a machine-readable *reason* so callers
    can distinguish transient transport errors from integrity or
    publication failures without parsing message strings.
    """

    reason: str
    """Machine-readable reason code (e.g. ``"cache_miss"``,
    ``"transport"``, ``"integrity"``, ``"publication"``,
    ``"corruption"``, ``"cancellation"``, ``"interruption"``)."""

    detail: str
    """Human-readable detail suitable for diagnostics."""

    def __str__(self) -> str:
        return self.detail


# ── typed materialization DTOs ────────────────────────────────────────


@dataclasses.dataclass(frozen=True)
class SelectedArtifact:
    """Minimal host-side materialization input for one selected artifact.

    The *url* and *integrity* come from the reviewed
    ``docker-constructor.toml`` artifact catalog entry.  No package
    name, version, source metadata, update policy, or override config
    is carried — those belong in the effective runtime projection, not
    the cache layer.
    """

    url: str
    """Exact reviewed download URL."""

    integrity: str
    """SRI integrity string (e.g.
    ``"sha512-VO9pV15P..."``)."""


@dataclasses.dataclass(frozen=True)
class VerifiedCacheBlob:
    """Immutable result after successful materialization and verification.

    *host_path* is the absolute path to the verified, atomically
    published regular file in the content-addressed cache.  The path
    is derivable solely from the validated algorithm and digest.
    """

    algorithm: str
    """Lower-case hash algorithm (e.g. ``"sha512"``)."""

    digest: str
    """Filesystem-safe digest string suitable as a path component."""

    integrity: str
    """Full SRI integrity string (``<algorithm>-<digest-base64>``)."""

    host_path: str
    """Absolute path to the verified blob in the cache."""


# ═══════════════════════════════════════════════════════════════════════
# Filesystem status DTO
# ═══════════════════════════════════════════════════════════════════════


@dataclasses.dataclass(frozen=True)
class CacheBlobStat:
    """Result of a filesystem inspection through the boundary.

    All fields mirror what the real filesystem reports without
    requiring the implementation to call ``os`` directly.
    """

    exists: bool
    """True when ``lstat`` succeeds (symlinks included)."""

    is_symlink: bool
    """True when the entry is a symbolic link."""

    is_regular_file: bool
    """True when the entry is a regular file (follows symlinks)."""

    mode_bits: int
    """Full ``st_mode`` integer (e.g. ``0o100400``)."""

    size: int
    """File size in bytes.  Undefined for non-regular entries."""


@dataclasses.dataclass(frozen=True)
class CacheBlobInspection:
    """Metadata and digest obtained from one opened cache descriptor."""

    stat: CacheBlobStat
    digest: str | None


# ── deterministic cache-key derivation ─────────────────────────────────

# The cache root is a module-level constant owned by the constructor,
# not exposed on RunRequest.  Every non-dry-run launch MUST materialize
# selected artifacts under this root before publishing the projection
# or invoking Docker.


# Only these algorithms may appear in a cache path.  An algorithm
# outside this set is rejected before path construction.
_SUPPORTED_ALGORITHMS = frozenset({"sha256", "sha384", "sha512"})

# A safe digest component contains only URL-safe base64 characters
# (RFC 4648 § 5), preserves padding, and MUST NOT be empty or carry
# traversal segments (``..``).  Path separators (``/``, ``\``) and
# null bytes are explicitly forbidden.
#
# Allowed: ``[A-Za-z0-9._-]`` with at most two trailing ``=`` pad
# chars.  Longer runs of ``=`` or ``=`` in the middle would indicate
# a malformed or malicious digest.
_DIGEST_RE = re.compile(r"^[A-Za-z0-9._-]+={0,2}$")


def _sri_to_algorithm_digest(integrity: str) -> tuple[str, str, str]:
    """Split a validated SRI integrity string into ``(algorithm,
    raw_base64, filesystem_safe_digest)``.

    *integrity* MUST have already passed the SRI regex
    (``sha(256|384|512)-[A-Za-z0-9+/]+=*``).

    The filesystem-safe digest replaces ``+`` with ``-`` and ``/``
    with ``_`` while preserving any ``=`` padding.  It does NOT
    include the algorithm prefix or the ``.tgz`` suffix.
    """
    algo, raw = integrity.split("-", 1)
    safe = raw.replace("+", "-").replace("/", "_")
    return algo, raw, safe


def derive_cache_path(
    algorithm: str,
    digest: str,
    *,
    root: str,
) -> str:
    """Return the deterministic content-addressed cache path for a
    validated *algorithm* and *digest*.

    The path is derived **solely** from *algorithm* and *digest*.
    Package names, URLs, versions, and caller-provided paths do NOT
    participate.

    Parameters
    ----------
    algorithm:
        Lower-case hash algorithm (``"sha256"``, ``"sha384"``, or
        ``"sha512"``).  Unsupported algorithms raise
        ``ValueError``.
    digest:
        Filesystem-safe digest string consisting only of URL-safe
        base64 characters (``[A-Za-z0-9._-]`` with at most two
        trailing ``=``).  Traversal segments, path separators,
        null bytes, and empty strings are rejected with
        ``ValueError``.
    root:
        Cache root directory.  When ``None`` the constructor-owned
        An explicit resolved cache root is required.

    Returns
    -------
    Absolute or relative path in the form
    ``<root>/<algorithm>/<digest>.tgz``.
    """
    if algorithm not in _SUPPORTED_ALGORITHMS:
        raise ValueError(
            f"unsupported algorithm {algorithm!r}; "
            f"must be one of {sorted(_SUPPORTED_ALGORITHMS)}"
        )
    if not digest:
        raise ValueError("digest must not be empty")
    if os.sep in digest or (os.sep != "/" and "/" in digest):
        raise ValueError(
            f"digest must not contain path separators: {digest!r}"
        )
    if "\x00" in digest:
        raise ValueError("digest must not contain null bytes")
    if digest in (".", ".."):
        raise ValueError(
            f"digest must not be a traversal component: {digest!r}"
        )
    if not _DIGEST_RE.match(digest):
        raise ValueError(
            f"digest contains unsafe characters: {digest!r}"
        )
    return os.path.join(root, algorithm, f"{digest}.tgz")


def derive_cache_path_from_integrity(
    integrity: str,
    *,
    root: str,
) -> tuple[str, str]:
    """Convenience that combines SRI parsing and cache-path derivation.

    Returns ``(host_path, algorithm)`` where *host_path* is the
    deterministic cache blob path and *algorithm* is the lower-case
    hash algorithm.

    The *integrity* string MUST have already been validated against
    ``sha(256|384|512)-[A-Za-z0-9+/]+=*`` by the caller.  The
    algorithm portion is re-checked against the supported set.
    """
    if "-" not in integrity:
        raise ValueError(f"invalid integrity format: {integrity!r}")
    algo, _raw, safe = _sri_to_algorithm_digest(integrity)
    return derive_cache_path(algo, safe, root=root), algo


# ── protocol boundaries ────────────────────────────────────────────────


class CacheFilesystem(Protocol):
    """Filesystem boundary beneath the cache root.

    Every operation that touches the disk goes through this protocol
    so the materialization pipeline never imports ``os``, ``shutil``,
    or ``stat`` directly for cache-side effects.
    """

    # ── existence / type inspection ──────────────────────────────

    def blob_exists(self, path: str) -> bool: ...

    def is_regular_file(self, path: str) -> bool: ...

    def is_symlink(self, path: str) -> bool: ...

    def stat_blob(self, path: str) -> CacheBlobStat: ...

    # ── reading ──────────────────────────────────────────────────

    def read_bytes(self, path: str) -> bytes: ...

    def digest_file(self, path: str, algorithm: str) -> str: ...

    def inspect_and_digest(
        self, path: str, algorithm: str,
    ) -> CacheBlobInspection: ...

    # ── secure directory creation ────────────────────────────────

    def ensure_secure_dir(self, path: str) -> None: ...

    # ── temporary state ────────────────────────────────────────

    def create_temp(self, path: str) -> None: ...

    def append_temp(self, path: str, chunk: bytes) -> None: ...

    def finalize_temp(self, path: str, mode: int) -> None: ...

    def cleanup_temp(self, root: str) -> None: ...

    # ── corrupt-entry removal ────────────────────────────────────

    def quarantine_or_remove(self, path: str) -> None: ...

    # ── permission inspection and changes ────────────────────────

    def get_permissions(self, path: str) -> int: ...

    def set_permissions(self, path: str, mode: int) -> None: ...

    # ── atomic publication ───────────────────────────────────────

    def atomic_publish(self, temp_path: str, final_path: str) -> None: ...


class StreamingTransport(Protocol):
    """Streaming download boundary.

    Yields chunks of raw bytes for the given URL.  Implementations
    yield one or more ``bytes`` objects.  The caller must hash chunks
    as they arrive and write them incrementally so the full artifact
    is never held in memory.
    """

    def fetch_chunks(self, url: str) -> Iterator[bytes]: ...


class IdentityLock(Protocol):
    """Per-integrity-identity coordination primitive.

    A lock is acquired for the duration of a cache-miss publication.
    ``acquire()`` returns ``True`` when the lock was successfully
    obtained.  The caller MUST track whether acquisition succeeded
    and only call ``release()`` when it did.

    Concurrent contenders MUST recheck the cache after acquiring the
    lock.  On success the lock is released; on failure, cancellation,
    or interruption temporary state is cleaned and the lock released.

    A **Factory** is a callable ``(identity: str) -> IdentityLock``
    that creates a new lock instance for the given integrity identity.
    """

    def acquire(self, identity: str) -> bool: ...

    def release(self, identity: str) -> None: ...


    class Factory(Protocol):
        """Callable that returns an :class:`IdentityLock` for a
        given integrity identity string."""

        def __call__(self, identity: str) -> IdentityLock: ...


class TemporaryDirectory(Protocol):
    """Injectable temporary-directory factory.

    All temporary download state lives on the same filesystem as the
    cache so that atomic rename is always same-device.
    """

    def mkdtemp(self, prefix: str, parent: str) -> str: ...
    """Create a temporary directory beneath *parent* and return its
    absolute path.

    Parameters
    ----------
    prefix:
        Name prefix for the temporary directory.
    parent:
        Parent directory under which to create the directory.
        For cache-materialization this should be the algorithm
        subdirectory of the cache root.
    """


# ── digest computation ─────────────────────────────────────────────────


def _compute_digest(data: bytes, algorithm: str) -> str:
    """Return the standard-base64 digest of *data* for *algorithm*.

    The result uses the standard base64 alphabet (RFC 4648 § 4),
    not the URL-safe variant."""
    import hashlib

    h = hashlib.new(algorithm, data)
    return base64.b64encode(h.digest()).decode("ascii")


def inspect_verified_blob_readonly(
    integrity: str,
    *,
    cache_root: str,
) -> bool:
    """Read-only, no-follow, descriptor-relative cache inspection.

    Verifies that a content-addressed blob for *integrity* exists
    under *cache_root*, is a regular file reached without following
    any symlink component (root, algorithm directory, or leaf), has
    has no group/world write bits, and its bytes match the declared SRI
    digest.

    **No mutation** — the function never creates, removes, renames,
    ``chmod``, locks, quarantines, or repairs anything on disk.
    Every file descriptor is closed before returning.

    Returns ``True`` for a valid cache hit.  Returns ``False`` for
    missing, corrupt, symlinked, non-regular, overly-permissive, or
    otherwise unsafe entries.  No exception escapes.
    """
    import hashlib
    import stat as _stat

    try:
        algo, raw_expected, safe_digest = \
            _sri_to_algorithm_digest(integrity)
    except (AttributeError, ValueError):
        return False

    if algo not in _SUPPORTED_ALGORITHMS:
        return False

    blob_name = f"{safe_digest}.tgz"

    # ── open cache root (O_NOFOLLOW: reject symlinked root) ──
    root_rdonly = os.O_RDONLY | os.O_DIRECTORY | getattr(os, "O_NOFOLLOW", 0)
    try:
        root_fd = os.open(cache_root, root_rdonly)
    except OSError:
        return False

    try:
        # ── open algorithm subdirectory ──
        try:
            algo_fd = os.open(algo, root_rdonly, dir_fd=root_fd)
        except OSError:
            return False
        try:
            # Verify algorithm component is really a directory.
            try:
                algo_st = os.fstat(algo_fd)
            except OSError:
                return False
            if not _stat.S_ISDIR(algo_st.st_mode):
                return False

            # ── open blob leaf (O_NOFOLLOW + O_NOATIME) ──
            # O_NOATIME is required to keep dry-run genuinely
            # non-mutating.  When the flag is unavailable at the
            # OS level or denied (PermissionError — caller does
            # not own the file), treat the blob as unreachable.
            blob_flags: int = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
            _noatime: int = getattr(os, "O_NOATIME", 0)
            if not _noatime:
                return False
            try:
                blob_fd = os.open(
                    blob_name, blob_flags | _noatime, dir_fd=algo_fd,
                )
            except PermissionError:
                return False
            except OSError:
                return False
            try:
                try:
                    blob_st = os.fstat(blob_fd)
                except OSError:
                    return False

                # ── regular file only ──
                if not _stat.S_ISREG(blob_st.st_mode):
                    return False

                # ── no group/world write ──
                if blob_st.st_mode & 0o022:
                    return False

                # ── hash and compare ──
                hasher = hashlib.new(algo)
                while True:
                    chunk = os.read(blob_fd, 64 * 1024)
                    if not chunk:
                        break
                    hasher.update(chunk)
                actual_raw = base64.b64encode(
                    hasher.digest(),
                ).decode("ascii")
                return actual_raw == raw_expected
            finally:
                os.close(blob_fd)
        finally:
            os.close(algo_fd)
    finally:
        os.close(root_fd)


# ── cache safety validation ───────────────────────────────────────────


def validate_cache_blob(
    host_path: str,
    *,
    cache_root: str,
) -> None:
    """Validate that *host_path* is a regular file, not a symlink,
    contained within *cache_root*, and has no group/world write bits.

    Raises :class:`ArtifactMaterializationError` on any violation.
    """
    root = os.path.realpath(cache_root)
    real_path = os.path.realpath(host_path)

    # ── containment ──────────────────────────────────────────────
    if not (
        real_path == root
        or real_path.startswith(root + os.sep)
    ):
        raise ArtifactMaterializationError(
            reason="containment",
            detail=(
                f"resolved path {real_path!r} is outside "
                f"cache root {root!r}"
            ),
        )

    # ── existence ────────────────────────────────────────────────
    if not os.path.lexists(host_path):
        raise ArtifactMaterializationError(
            reason="missing",
            detail=f"blob path {host_path!r} does not exist",
        )

    # ── no symlink ───────────────────────────────────────────────
    if os.path.islink(host_path):
        raise ArtifactMaterializationError(
            reason="symlink",
            detail=f"blob path {host_path!r} must not be a symlink",
        )

    # ── regular file only ────────────────────────────────────────
    if not os.path.isfile(host_path):
        raise ArtifactMaterializationError(
            reason="not_regular_file",
            detail=f"blob path {host_path!r} is not a regular file",
        )

    # ── no group/world write ───────────────────────────────────
    st = os.stat(host_path)
    if st.st_mode & 0o022:
        raise ArtifactMaterializationError(
            reason="permissions",
            detail=(
                f"blob at {host_path!r} has group/other write bits "
                f"(mode {oct(st.st_mode)})"
            ),
        )


# ── cache-directory permission enforcement ────────────────────────────




# ── materialization pipeline ──────────────────────────────────────────


def materialize_selected_artifacts(
    selected: list[SelectedArtifact],
    *,
    transport: StreamingTransport,
    filesystem: CacheFilesystem,
    lock_factory: IdentityLock.Factory,
    temp_dir: TemporaryDirectory,
    cache_root: str,
    temp_root: str | None = None,
) -> dict[str, VerifiedCacheBlob]:
    """Materialize and verify every *selected* artifact in the
    content-addressed host cache.

    Each artifact is validated, downloaded (cache-miss), verified,
    and atomically published under per-identity coordination.
    Cache hits skip network access.  Every blob is revalidated
    after publication before returning.

    Returns a mapping from SRI integrity string to
    :class:`VerifiedCacheBlob`.

    Raises :class:`ArtifactMaterializationError` on transport
    failure, integrity mismatch, publication error, or
    cancellation.
    """
    root = cache_root
    if temp_root is None:
        temp_root = os.path.join(os.path.dirname(root), "tmp")

    # ── 0. validate and deduplicate ──────────────────────────────
    _validate_selected(selected)

    unique: dict[str, SelectedArtifact] = {}
    for art in selected:
        if art.integrity not in unique:
            unique[art.integrity] = art

    # ── 1. materialize each unique integrity ─────────────────────
    results: dict[str, VerifiedCacheBlob] = {}
    for integrity, artifact in unique.items():
        blob = _materialize_one(
            integrity=integrity,
            artifact=artifact,
            transport=transport,
            filesystem=filesystem,
            lock_factory=lock_factory,
            temp_dir=temp_dir,
            temp_root=temp_root,
            root=root,
        )
        results[integrity] = blob

    return results


def _validate_selected(selected: list[SelectedArtifact]) -> None:
    """Reject any selected artifact with an unsupported algorithm
    or malformed integrity before any IO."""
    for art in selected:
        if "-" not in art.integrity:
            raise ArtifactMaterializationError(
                reason="integrity",
                detail=f"malformed integrity: {art.integrity!r}",
            )
        algo = art.integrity.split("-", 1)[0]
        if algo not in _SUPPORTED_ALGORITHMS:
            raise ArtifactMaterializationError(
                reason="integrity",
                detail=(
                    f"unsupported algorithm {algo!r} "
                    f"in {art.integrity!r}"
                ),
            )
        # Also validate via the SRI regex from the model layer.
        if not _get_integrity_re().match(art.integrity):
            raise ArtifactMaterializationError(
                reason="integrity",
                detail=f"integrity does not match SRI format: {art.integrity!r}",
            )


def _try_cache_hit(
    integrity: str,
    algorithm: str,
    path: str,
    filesystem: CacheFilesystem,
    root: str,
) -> VerifiedCacheBlob | None:
    """Return a :class:`VerifiedCacheBlob` when *path* is safe and
    its digest matches *integrity*.  Return ``None`` otherwise."""
    try:
        inspection = filesystem.inspect_and_digest(path, algorithm)
        status = inspection.stat
        if (
            not status.exists
            or status.is_symlink
            or not status.is_regular_file
            or status.mode_bits & 0o022
            or inspection.digest is None
        ):
            return None
        if os.path.commonpath((os.path.abspath(root), os.path.abspath(path))) != os.path.abspath(root):
            return None
    except (ArtifactMaterializationError, FileNotFoundError, OSError):
        return None

    expected_raw = _sri_to_algorithm_digest(integrity)[1]
    actual_raw = inspection.digest
    if actual_raw != expected_raw:
        return None

    safe_digest = _sri_to_algorithm_digest(integrity)[2]
    return VerifiedCacheBlob(
        algorithm=algorithm,
        digest=safe_digest,
        integrity=integrity,
        host_path=path,
    )


def _materialize_one(
    integrity: str,
    artifact: SelectedArtifact,
    *,
    transport: StreamingTransport,
    filesystem: CacheFilesystem,
    lock_factory: IdentityLock.Factory,
    temp_dir: TemporaryDirectory,
    temp_root: str,
    root: str,
) -> VerifiedCacheBlob:
    """Materialize a single integrity identity.

    The pipeline:

    1. Fast path — cache hit with no lock.
    2. Lock acquisition.
    3. Post-lock recheck.
    4. Corrupt-entry quarantining.
    5. Streaming download + hash.
    6. Atomic publication.
    7. Post-publication revalidation.
    8. Unconditional cleanup and lock release (with exception
       chaining — the primary error is always preserved).
    """
    path, algorithm = derive_cache_path_from_integrity(
        integrity, root=root,
    )

    # ── 0. harden private subtrees before any access ───────────
    cache_root = os.path.dirname(os.path.dirname(path))
    algorithm_dir = os.path.dirname(path)
    _ensure_dir_private(algorithm_dir)

    # ── 1. fast path: valid cache hit ────────────────────────────
    hit = _try_cache_hit(integrity, algorithm, path, filesystem, root)
    if hit is not None:
        return hit

    # ── 2. coordinated download ──────────────────────────────────
    lock = lock_factory(integrity)
    tmp_root: str | None = None
    acquired: bool = False
    primary_exc: BaseException | None = None

    try:
        acquired = lock.acquire(integrity)

        # ── 3. post-lock recheck ─────────────────────────────────
        hit = _try_cache_hit(integrity, algorithm, path, filesystem, root)
        if hit is not None:
            return hit

        # ── 4. quarantine any corrupt entry ──────────────────────
        filesystem.quarantine_or_remove(path)

        # ── 5. streaming download + hash ─────────────────────────
        filesystem.ensure_secure_dir(algorithm_dir)
        expected_raw = _sri_to_algorithm_digest(integrity)[1]

        tmp_root = temp_dir.mkdtemp(
            prefix="materialize-", parent=temp_root,
        )
        filesystem.ensure_secure_dir(tmp_root)

        tmp_blob = os.path.join(tmp_root, "blob.tgz")

        # Stream chunks: hash on-the-fly, write incrementally
        # through the filesystem boundary.
        import hashlib

        h = hashlib.new(algorithm)
        filesystem.create_temp(tmp_blob)
        try:
            for chunk in transport.fetch_chunks(artifact.url):
                if not isinstance(chunk, bytes):
                    raise TypeError(
                        f"transport yielded {type(chunk).__name__}, not bytes"
                    )
                h.update(chunk)
                filesystem.append_temp(tmp_blob, chunk)
        except ArtifactMaterializationError:
            raise
        except Exception as exc:
            raise ArtifactMaterializationError(
                reason="transport",
                detail=f"download of {artifact.url!r} failed: {exc}",
            ) from exc
        filesystem.finalize_temp(tmp_blob, 0o444)

        actual_raw = base64.b64encode(h.digest()).decode("ascii")
        if actual_raw != expected_raw:
            raise ArtifactMaterializationError(
                reason="integrity",
                detail=(
                    f"digest mismatch for {artifact.url!r}: "
                    f"expected {integrity}, got "
                    f"{algorithm}-{actual_raw}"
                ),
            )

        # ── 6. atomic publication ────────────────────────────────
        filesystem.ensure_secure_dir(os.path.dirname(path))
        filesystem.atomic_publish(tmp_blob, path)
        tmp_blob = None  # owned by the cache now; don't delete
        filesystem.set_permissions(path, 0o444)

        # ── 7. post-publication revalidation ─────────────────────
        try:
            _validate_published_blob(
                path, integrity, algorithm, root, filesystem,
            )
        except BaseException as validation_exc:
            try:
                filesystem.quarantine_or_remove(path)
            except BaseException as cleanup_exc:
                try:
                    validation_exc.add_note(
                        "additionally, invalid published entry cleanup failed: "
                        f"{cleanup_exc}"
                    )
                except AttributeError:
                    pass
            raise

        safe_digest = _sri_to_algorithm_digest(integrity)[2]
        return VerifiedCacheBlob(
            algorithm=algorithm,
            digest=safe_digest,
            integrity=integrity,
            host_path=path,
        )

    except BaseException as exc:
        primary_exc = exc
        raise
    finally:
        # ── 8. unconditional cleanup ─────────────────────────────
        # Collect cleanup errors so BOTH temp cleanup and lock
        # release are attempted, even if one fails.
        cleanup_errors: list[BaseException] = []

        if tmp_root is not None:
            try:
                filesystem.cleanup_temp(tmp_root)
            except BaseException as exc:
                cleanup_errors.append(exc)

        if acquired:
            try:
                lock.release(integrity)
            except BaseException as exc:
                cleanup_errors.append(exc)

        # Surface cleanup errors.
        if cleanup_errors:
            if primary_exc is not None:
                # Attach cleanup failures as notes on the primary.
                for exc in cleanup_errors:
                    try:
                        primary_exc.add_note(
                            f"additionally, cleanup failed: {exc}"
                        )
                    except AttributeError:
                        pass
            else:
                # No primary — the first cleanup error becomes primary.
                first = cleanup_errors[0]
                raise ArtifactMaterializationError(
                    reason="publication",
                    detail=f"cleanup or release failed: {first}",
                ) from first


def _validate_published_blob(
    path: str,
    integrity: str,
    algorithm: str,
    root: str,
    filesystem: CacheFilesystem,
) -> None:
    """Revalidate a published blob through the filesystem boundary.

    Rechecks containment, no-symlink, regular-file, permissions,
    and digest.  Raises :class:`ArtifactMaterializationError` on any
    failure.
    """
    # Metadata and digest come from the same no-follow file descriptor.
    inspection = filesystem.inspect_and_digest(path, algorithm)
    stat = inspection.stat

    if not stat.exists:
        raise ArtifactMaterializationError(
            reason="publication",
            detail=f"published blob {path!r} does not exist",
        )
    if stat.is_symlink:
        raise ArtifactMaterializationError(
            reason="publication",
            detail=f"published blob {path!r} is a symlink",
        )
    if not stat.is_regular_file:
        raise ArtifactMaterializationError(
            reason="publication",
            detail=f"published blob {path!r} is not a regular file",
        )

    mode = stat.mode_bits
    if mode & 0o022:
        raise ArtifactMaterializationError(
            reason="publication",
            detail=(
                f"published blob {path!r} has group/other write bits "
                f"(mode {oct(mode)})"
            ),
        )

    # Re-check lexical containment; component safety was established by the
    # descriptor-relative stat and permission operations above.
    if os.path.commonpath((os.path.abspath(root), os.path.abspath(path))) != os.path.abspath(root):
        raise ArtifactMaterializationError(
            reason="containment", detail=f"published blob {path!r} escaped cache root",
        )

    # ── digest re-check ──────────────────────────────────────────
    expected_raw = _sri_to_algorithm_digest(integrity)[1]
    actual_raw = inspection.digest
    if actual_raw is None:
        raise ArtifactMaterializationError(
            reason="publication", detail=f"published blob {path!r} was not readable",
        )
    if actual_raw != expected_raw:
        raise ArtifactMaterializationError(
            reason="integrity",
            detail=(
                f"post-publication digest mismatch for {path!r}: "
                f"expected {integrity}, got {algorithm}-{actual_raw}"
            ),
        )



class HttpStreamingTransport:
    """Production HTTP transport that never buffers the response body."""

    def __init__(self, *, chunk_size: int = 64 * 1024, timeout: float = 30.0):
        self._chunk_size = chunk_size
        self._timeout = timeout

    def fetch_chunks(self, url: str) -> Iterator[bytes]:
        request = urllib.request.Request(url, headers={"User-Agent": "pi-cli/1"})
        with urllib.request.urlopen(request, timeout=self._timeout) as response:
            while True:
                chunk = response.read(self._chunk_size)
                if not chunk:
                    return
                yield chunk


def _ensure_dir_private(path: str) -> None:
    """Fix permissions on *path* to ``0o700`` using descriptor-relative,
    no-follow operations.

    *path* must be a known-private cache subtree — ``blobs/``,
    ``locks/``, an algorithm directory, or a temporary directory.
    Shared parent containers (``.docker-generated/``,
    ``runtime-artifacts/``) are intentionally **not** passed here.

    Opens the parent and target without following symlinks, validates
    the target is a directory via ``fstat``, and corrects the mode with
    ``fchmod`` — all on the same descriptor.

    Silently returns when the directory or its lead-up does not exist.
    Raises :class:`ArtifactMaterializationError` with reason
    ``"permissions"`` when the process cannot access a parent
    component, open the target, or ``fchmod`` an existing entry.
    Raises with reason ``"containment"`` for symlinks and
    non-directory entries.
    """
    import stat as _stat
    try:
        parent_fd, name = _open_parent(path)
    except FileNotFoundError:
        return
    except (PermissionError, OSError) as exc:
        raise ArtifactMaterializationError(
            "permissions",
            f"cannot access parent of cache root {path!r}: {exc}",
        ) from exc
    try:
        flags = os.O_RDONLY | os.O_DIRECTORY | getattr(os, "O_NOFOLLOW", 0)
        # FileNotFoundError is the only benign outcome — the entry
        # simply does not exist yet.  All other failures must be
        # surfaced as structured errors.
        try:
            fd = os.open(name, flags, dir_fd=parent_fd)
        except FileNotFoundError:
            return
        except PermissionError as exc:
            raise ArtifactMaterializationError(
                "permissions",
                f"cannot open cache root entry at {path!r}: {exc}",
            ) from exc
        except (NotADirectoryError, OSError) as exc:
            raise ArtifactMaterializationError(
                "containment",
                f"unsafe cache root entry at {path!r}: {exc}",
            ) from exc
        try:
            current_mode = os.fstat(fd).st_mode
            if not _stat.S_ISDIR(current_mode):
                raise ArtifactMaterializationError(
                    "containment",
                    f"expected directory at {path!r}, found non-directory entry",
                )
            if current_mode & 0o077:
                try:
                    os.fchmod(fd, _stat.S_IRWXU)
                except PermissionError as exc:
                    raise ArtifactMaterializationError(
                        "permissions",
                        f"cannot secure cache root {path!r}: {exc}",
                    ) from exc
        finally:
            os.close(fd)
    finally:
        os.close(parent_fd)


def _open_directory_chain(path: str, *, create: bool) -> int:
    """Open an absolute directory without following any symlink component.

    Missing components are created descriptor-relatively when *create* is
    true.  Newly created directories use ``0o777`` (subject to umask)
    so that parent containers like ``.docker-generated/`` and
    ``runtime-artifacts/`` retain the calling process's default
    permission bits.  Private subtrees (``blobs/``, ``locks/``,
    algorithm dirs, temp dirs) are hardened separately by their
    callers.

    The returned descriptor owns the final directory and must be
    closed by the caller.
    """
    absolute = os.path.abspath(path)
    flags = os.O_RDONLY | os.O_DIRECTORY | getattr(os, "O_NOFOLLOW", 0)
    current_fd = os.open(os.sep, flags)
    try:
        for component in (part for part in absolute.split(os.sep) if part):
            try:
                value = os.stat(component, dir_fd=current_fd, follow_symlinks=False)
            except FileNotFoundError:
                if not create:
                    raise
                # Let umask dictate the default mode for parent
                # directories; private subtrees are hardened later.
                os.mkdir(component, 0o777, dir_fd=current_fd)
                value = os.stat(component, dir_fd=current_fd, follow_symlinks=False)
            if stat_module.S_ISLNK(value.st_mode) or not stat_module.S_ISDIR(value.st_mode):
                raise ArtifactMaterializationError(
                    "containment",
                    f"unsafe cache path component {component!r} in {absolute!r}",
                )
            next_fd = os.open(component, flags, dir_fd=current_fd)
            os.close(current_fd)
            current_fd = next_fd
        return current_fd
    except BaseException:
        os.close(current_fd)
        raise


def _open_parent(path: str, *, create: bool = False) -> tuple[int, str]:
    absolute = os.path.abspath(path)
    name = os.path.basename(absolute)
    if not name or name in {".", ".."}:
        raise ArtifactMaterializationError("containment", f"unsafe cache path {path!r}")
    return _open_directory_chain(os.path.dirname(absolute), create=create), name


def _remove_tree_at(parent_fd: int, name: str) -> None:
    """Remove one directory tree without resolving path components."""
    flags = os.O_RDONLY | os.O_DIRECTORY | getattr(os, "O_NOFOLLOW", 0)
    directory_fd = os.open(name, flags, dir_fd=parent_fd)
    try:
        for child in os.listdir(directory_fd):
            value = os.stat(child, dir_fd=directory_fd, follow_symlinks=False)
            if stat_module.S_ISDIR(value.st_mode) and not stat_module.S_ISLNK(value.st_mode):
                _remove_tree_at(directory_fd, child)
            else:
                os.unlink(child, dir_fd=directory_fd)
    finally:
        os.close(directory_fd)
    os.rmdir(name, dir_fd=parent_fd)


class LocalCacheFilesystem:
    """Production cache filesystem using descriptor-relative operations."""

    def blob_exists(self, path: str) -> bool:
        return self.stat_blob(path).exists

    def is_regular_file(self, path: str) -> bool:
        return self.stat_blob(path).is_regular_file

    def is_symlink(self, path: str) -> bool:
        return self.stat_blob(path).is_symlink

    def stat_blob(self, path: str) -> CacheBlobStat:
        try:
            parent_fd, name = _open_parent(path)
        except FileNotFoundError:
            return CacheBlobStat(False, False, False, 0, 0)
        try:
            try:
                value = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
            except FileNotFoundError:
                return CacheBlobStat(False, False, False, 0, 0)
        finally:
            os.close(parent_fd)
        return CacheBlobStat(
            True,
            stat_module.S_ISLNK(value.st_mode),
            stat_module.S_ISREG(value.st_mode),
            value.st_mode,
            value.st_size,
        )

    def read_bytes(self, path: str) -> bytes:
        parent_fd, name = _open_parent(path)
        try:
            flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
            fd = os.open(name, flags, dir_fd=parent_fd)
            try:
                with os.fdopen(fd, "rb", closefd=False) as stream:
                    return stream.read()
            finally:
                os.close(fd)
        finally:
            os.close(parent_fd)

    def digest_file(self, path: str, algorithm: str) -> str:
        inspection = self.inspect_and_digest(path, algorithm)
        if inspection.digest is None:
            raise ArtifactMaterializationError("containment", "cache blob is not regular")
        return inspection.digest

    def inspect_and_digest(
        self, path: str, algorithm: str,
    ) -> CacheBlobInspection:
        import hashlib
        parent_fd, name = _open_parent(path)
        try:
            flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
            try:
                fd = os.open(name, flags, dir_fd=parent_fd)
            except FileNotFoundError:
                return CacheBlobInspection(
                    CacheBlobStat(False, False, False, 0, 0), None,
                )
            except OSError:
                value = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
                return CacheBlobInspection(
                    CacheBlobStat(
                        True,
                        stat_module.S_ISLNK(value.st_mode),
                        stat_module.S_ISREG(value.st_mode),
                        value.st_mode,
                        value.st_size,
                    ),
                    None,
                )
            try:
                value = os.fstat(fd)
                status = CacheBlobStat(
                    True,
                    False,
                    stat_module.S_ISREG(value.st_mode),
                    value.st_mode,
                    value.st_size,
                )
                if not status.is_regular_file:
                    return CacheBlobInspection(status, None)
                digest = hashlib.new(algorithm)
                with os.fdopen(fd, "rb", closefd=False) as stream:
                    for chunk in iter(lambda: stream.read(64 * 1024), b""):
                        digest.update(chunk)
                return CacheBlobInspection(
                    status,
                    base64.b64encode(digest.digest()).decode("ascii"),
                )
            finally:
                os.close(fd)
        finally:
            os.close(parent_fd)

    def ensure_secure_dir(self, path: str) -> None:
        fd = _open_directory_chain(path, create=True)
        try:
            os.fchmod(fd, 0o700)
        finally:
            os.close(fd)

    def create_temp(self, path: str) -> None:
        parent_fd, name = _open_parent(path)
        try:
            flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
            fd = os.open(name, flags, 0o600, dir_fd=parent_fd)
            os.close(fd)
        finally:
            os.close(parent_fd)

    def append_temp(self, path: str, chunk: bytes) -> None:
        parent_fd, name = _open_parent(path)
        try:
            flags = os.O_WRONLY | os.O_APPEND | getattr(os, "O_NOFOLLOW", 0)
            fd = os.open(name, flags, dir_fd=parent_fd)
            try:
                if not stat_module.S_ISREG(os.fstat(fd).st_mode):
                    raise ArtifactMaterializationError("containment", "temporary blob is not regular")
                view = memoryview(chunk)
                while view:
                    view = view[os.write(fd, view):]
            finally:
                os.close(fd)
        finally:
            os.close(parent_fd)

    def finalize_temp(self, path: str, mode: int) -> None:
        parent_fd, name = _open_parent(path)
        try:
            fd = os.open(name, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0), dir_fd=parent_fd)
            try:
                os.fchmod(fd, mode)
            finally:
                os.close(fd)
        finally:
            os.close(parent_fd)

    def cleanup_temp(self, root: str) -> None:
        parent_fd, name = _open_parent(root)
        try:
            value = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
            if not stat_module.S_ISDIR(value.st_mode) or stat_module.S_ISLNK(value.st_mode):
                raise ArtifactMaterializationError("containment", "temporary root is unsafe")
            _remove_tree_at(parent_fd, name)
        finally:
            os.close(parent_fd)

    def quarantine_or_remove(self, path: str) -> None:
        try:
            parent_fd, name = _open_parent(path)
        except FileNotFoundError:
            return
        try:
            try:
                value = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
            except FileNotFoundError:
                return
            if stat_module.S_ISDIR(value.st_mode) and not stat_module.S_ISLNK(value.st_mode):
                _remove_tree_at(parent_fd, name)
            else:
                os.unlink(name, dir_fd=parent_fd)
        finally:
            os.close(parent_fd)

    def get_permissions(self, path: str) -> int:
        parent_fd, name = _open_parent(path)
        try:
            return stat_module.S_IMODE(
                os.stat(name, dir_fd=parent_fd, follow_symlinks=False).st_mode
            )
        finally:
            os.close(parent_fd)

    def set_permissions(self, path: str, mode: int) -> None:
        parent_fd, name = _open_parent(path)
        try:
            fd = os.open(name, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0), dir_fd=parent_fd)
            try:
                if not stat_module.S_ISREG(os.fstat(fd).st_mode):
                    raise ArtifactMaterializationError("containment", "cache blob is not regular")
                os.fchmod(fd, mode)
            finally:
                os.close(fd)
        finally:
            os.close(parent_fd)

    def atomic_publish(self, temp_path: str, final_path: str) -> None:
        source_fd, source_name = _open_parent(temp_path)
        target_fd, target_name = _open_parent(final_path)
        try:
            source = os.stat(source_name, dir_fd=source_fd, follow_symlinks=False)
            target_dir = os.fstat(target_fd)
            if not stat_module.S_ISREG(source.st_mode):
                raise ArtifactMaterializationError("publication", "temporary blob is not regular")
            if source.st_dev != target_dir.st_dev:
                raise ArtifactMaterializationError(
                    "publication", "temporary and final paths are on different filesystems"
                )
            os.replace(
                source_name, target_name,
                src_dir_fd=source_fd, dst_dir_fd=target_fd,
            )
        finally:
            os.close(source_fd)
            os.close(target_fd)


class LocalTemporaryDirectory:
    def mkdtemp(self, prefix: str, parent: str) -> str:
        import secrets
        parent_fd = _open_directory_chain(parent, create=False)
        try:
            for _ in range(100):
                name = prefix + secrets.token_hex(8)
                try:
                    os.mkdir(name, 0o700, dir_fd=parent_fd)
                except FileExistsError:
                    continue
                return os.path.join(os.path.abspath(parent), name)
        finally:
            os.close(parent_fd)
        raise FileExistsError("could not allocate unique temporary directory")


class FileIdentityLock:
    """Advisory per-integrity lock held by an open private lock file."""

    def __init__(self, lock_root: str):
        self._lock_root = lock_root
        self._fd: int | None = None

    def acquire(self, identity: str) -> bool:
        import fcntl
        lock_dir_fd = _open_directory_chain(self._lock_root, create=True)
        try:
            os.fchmod(lock_dir_fd, 0o700)
            safe = base64.urlsafe_b64encode(identity.encode()).decode().rstrip("=")
            name = safe + ".lock"
            flags = os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0)
            try:
                self._fd = os.open(name, flags, 0o600, dir_fd=lock_dir_fd)
            except OSError as exc:
                raise ArtifactMaterializationError(
                    "containment", "identity lock path is unsafe",
                ) from exc
            value = os.fstat(self._fd)
            if not stat_module.S_ISREG(value.st_mode) or value.st_nlink != 1:
                os.close(self._fd)
                self._fd = None
                raise ArtifactMaterializationError(
                    "containment", "identity lock is not a private regular file",
                )
            os.fchmod(self._fd, 0o600)
            fcntl.flock(self._fd, fcntl.LOCK_EX)
            return True
        finally:
            os.close(lock_dir_fd)

    def release(self, identity: str) -> None:
        if self._fd is None:
            return
        import fcntl
        try:
            fcntl.flock(self._fd, fcntl.LOCK_UN)
        finally:
            os.close(self._fd)
            self._fd = None


class FileIdentityLockFactory:
    def __init__(self, cache_root: str, *, lock_root: str | None = None):
        self._lock_root = lock_root or os.path.join(
            os.path.dirname(cache_root), "locks",
        )

    def __call__(self, identity: str) -> IdentityLock:
        return FileIdentityLock(self._lock_root)


# Import the integrity regex from the model layer for validation.
# (Lazy import to avoid circular dependency at module level.)
_INTEGRITY_RE: re.Pattern[str] | None = None


def _get_integrity_re() -> re.Pattern[str]:
    global _INTEGRITY_RE
    if _INTEGRITY_RE is None:
        from docker.versioning.inventory import _INTEGRITY_RE as _re

        _INTEGRITY_RE = _re
    return _INTEGRITY_RE
