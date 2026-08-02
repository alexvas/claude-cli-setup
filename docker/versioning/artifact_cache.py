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
from typing import Protocol


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


# ── deterministic cache-key derivation ─────────────────────────────────

# The cache root is a module-level constant owned by the constructor,
# not exposed on RunRequest.  Every non-dry-run launch MUST materialize
# selected artifacts under this root before publishing the projection
# or invoking Docker.

DEFAULT_RUNTIME_ARTIFACT_CACHE_ROOT = ".docker-generated/runtime-artifacts/blobs"

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

# Cache layout:
#   <root> / <algorithm> / <filesystem-safe-digest>.tgz
#
# SRI base64 uses the URL-safe alphabet (RFC 4648 § 5):
#   -  ->  +   (reverse: _  ->  /)
#   _  ->  /   (reverse: -  ->  +)
# Padding (=) is preserved — it is legal in POSIX filenames.
#
# The suffix (.tgz) is stable because all reviewed runtime artifacts
# are currently npm tarballs.  If a future change introduces a
# different packaging format the suffix becomes a property of the
# cache key contract, not a caller choice.


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
    root: str | None = None,
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
        ``DEFAULT_RUNTIME_ARTIFACT_CACHE_ROOT`` is used.

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
    if root is None:
        root = DEFAULT_RUNTIME_ARTIFACT_CACHE_ROOT
    return os.path.join(root, algorithm, f"{digest}.tgz")


def derive_cache_path_from_integrity(
    integrity: str,
    *,
    root: str | None = None,
) -> tuple[str, str]:
    """Convenience that combines SRI parsing and cache-path derivation.

    Returns ``(host_path, algorithm)`` where *host_path* is the
    deterministic cache blob path and *algorithm* is the lower-case
    hash algorithm.

    The *integrity* string MUST have already been validated against
    ``sha(256|384|512)-[A-Za-z0-9+/]+=*`` by the caller.  The
    algorithm portion is re-checked against the supported set.
    """
    # Defensive split: the caller guarantees a valid SRI, but we
    # still guard against missing/duplicate separators.
    if "-" not in integrity:
        raise ValueError(f"invalid integrity format: {integrity!r}")
    algo, _raw, safe = _sri_to_algorithm_digest(integrity)
    return derive_cache_path(algo, safe, root=root), algo


# ── protocol boundaries ────────────────────────────────────────────────


class CacheFilesystem(Protocol):
    """Filesystem boundary beneath the cache root."""

    def blob_exists(self, path: str) -> bool: ...

    def is_regular_file(self, path: str) -> bool: ...

    def is_symlink(self, path: str) -> bool: ...

    def read_bytes(self, path: str) -> bytes: ...

    def mkdir_p(self, path: str) -> None: ...

    def write_temp(self, path: str, data: bytes) -> None: ...

    def publish(self, temp_path: str, final_path: str) -> None: ...

    def remove(self, path: str) -> None: ...


class StreamingTransport(Protocol):
    """Streaming download boundary.

    Returns raw bytes for the given URL.  Implementations may stream
    through a hasher before returning so integrity is verified during
    download rather than in a separate pass.
    """

    def fetch(self, url: str) -> bytes: ...


class IdentityLock(Protocol):
    """Per-integrity-identity coordination primitive.

    A lock is acquired for the duration of a cache-miss publication.
    Concurrent contenders MUST recheck the cache after acquiring the
    lock.  On success the lock is released; on failure, cancellation,
    or interruption temporary state is cleaned and the lock released.
    """

    def acquire(self, identity: str) -> None: ...

    def release(self, identity: str) -> None: ...


class Clock(Protocol):
    """Injectable clock for test-controlled timing."""

    def now(self) -> float: ...


class TemporaryDirectory(Protocol):
    """Injectable temporary-directory factory.

    All temporary download state lives on the same filesystem as the
    cache so that atomic rename (and any future hard-link publishing)
    is always same-device.
    """

    def mkdtemp(self, prefix: str) -> str: ...


# ── cache safety validation (placeholder — RED until implemented) ────


def validate_cache_blob(host_path: str) -> None:
    """Validate that *host_path* is a regular file, not a symlink,
    contained within the cache root, and has owner-only permissions.

    Raises :class:`ArtifactMaterializationError` on any violation.

    **Not yet implemented** — raises ``NotImplementedError`` to keep
    the safety tests RED until section 3 materialization."""
    raise NotImplementedError("validate_cache_blob — implement in section 3")
