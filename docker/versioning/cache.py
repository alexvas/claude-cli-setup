"""Read-through cache for HTTP responses with optional disk persistence.

Wraps an :class:`HttpTransport` and caches responses to both an
in-memory (fast) and an on-disk (persistent across invocations) store.

**Security**: Authenticated responses are keyed by a non-secret hash of
the ``Authorization`` header so that cached private data is never served
to unauthenticated callers (or callers with a different token).  Disk
files and directories are created with owner-only permissions (``0600`` /
``0700``).
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import stat
import time
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .providers.base import HttpResponse

from .providers.base import HttpTransport


# ---------------------------------------------------------------------------
# Default cache directory
# ---------------------------------------------------------------------------

_CACHE_DIR = (
    os.environ.get("XDG_CACHE_HOME", os.path.expanduser("~/.cache"))
)
_DEFAULT_CACHE_SUBDIR = "pi-cli/versioning"


def _default_cache_dir() -> Path:
    return Path(_CACHE_DIR) / _DEFAULT_CACHE_SUBDIR


# ---------------------------------------------------------------------------
# Auth-scope derivation
# ---------------------------------------------------------------------------


def _derive_scope(headers: object) -> str:
    """Return a stable, non-secret scope string from request headers.

    When an ``Authorization`` header is present its SHA-256 (first 16 hex
    chars) is used so that different tokens produce different scopes.
    Without any auth the scope is the literal ``"public"``.

    Header name matching is **case-insensitive** (RFC 7230 § 3.2).
    """
    auth = _extract_authorization(headers)
    if auth:
        return "auth:" + hashlib.sha256(auth.encode()).hexdigest()[:16]
    return "public"


def _casefold_get(headers: object, name: str) -> str:
    """Case-insensitive header lookup for a Mapping or iterable-of-pairs.

    Uses ``casefold()`` to match RFC 7230 § 3.2 (header field names are
    case-insensitive).  Returns ``""`` when the header is absent.
    """
    if headers is None:
        return ""
    key = name.casefold()
    if hasattr(headers, "items"):
        for k, v in headers.items():  # type: ignore[union-attr]
            if str(k).casefold() == key:
                return str(v) if v else ""
        return ""
    if isinstance(headers, (list, tuple)):
        for k, v in headers:
            if str(k).casefold() == key:
                return str(v)
    return ""


def _extract_authorization(headers: object) -> str:
    """Extract the ``Authorization`` header value (case-insensitive),
    or ``""`` when the header is absent."""
    return _casefold_get(headers, "authorization")


def _extract_accept(headers: object) -> str:
    """Extract the ``Accept`` header value (case-insensitive), or ``""``."""
    return _casefold_get(headers, "accept")


def _derive_representation(headers: object) -> str:
    """Return a cache-key component derived from representation-affecting
    headers (``Accept``).  An absent or ``*/*`` Accept header yields the
    neutral token ``"wildcard"``."""
    accept = _extract_accept(headers).strip()
    if not accept or accept == "*/*":
        return "wildcard"
    # Normalise: sort comma-separated media ranges for stable keys
    parts = sorted(v.strip() for v in accept.split(","))
    norm = ", ".join(parts)
    return "accept:" + hashlib.sha256(norm.encode()).hexdigest()[:16]


# ---------------------------------------------------------------------------
# Disk cache
# ---------------------------------------------------------------------------


class DiskCache:
    """On-disk cache for HTTP responses keyed by ``(method, url, scope)``.

    Each entry is stored as a JSON file whose name is the SHA-256 of the
    cache key.  Files and directories are created with owner-only
    permissions (``0600`` / ``0700``).

    Entries older than *ttl* seconds are treated as expired.
    """

    __slots__ = ("_dir", "_ttl", "_read_only")

    def __init__(self, directory: Path, ttl: int | None = None, *, read_only: bool = False) -> None:
        self._dir = directory
        self._ttl = ttl
        self._read_only = read_only

    # -- public API ---------------------------------------------------------

    def get(self, method: str, url: str, *, scope: str = "public", representation: str = "wildcard") -> object | None:
        """Return a cached ``HttpResponse``-compatible object or ``None``."""
        path = self._path_for(method, url, scope, representation)
        try:
            with open(path, encoding="utf-8") as fh:
                data = json.load(fh)
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            return None

        # Reject structurally corrupt entries (missing required keys)
        try:
            status = data["status"]
            stored_headers = dict(data.get("headers", {}))
            body_b64 = data["body_b64"]
        except (KeyError, TypeError):
            return None

        if self._ttl is not None:
            age = time.time() - data.get("ts", 0)
            if age > self._ttl:
                return None

        try:
            body = base64.b64decode(body_b64)
        except Exception:
            return None

        return _cached_response(status, stored_headers, body)

    def set(
        self, method: str, url: str, response: object, *, scope: str = "public", representation: str = "wildcard",
    ) -> None:
        """Persist *response* to disk.  No-op when the cache is read-only."""
        if self._read_only:
            return
        _ensure_dir(self._dir)
        path = self._path_for(method, url, scope, representation)
        body = getattr(response, "body", b"")
        if not isinstance(body, bytes):
            body = b""
        stored_headers = dict(getattr(response, "headers", {}))
        # Strip Authorization from the stored response so it cannot leak
        stored_headers.pop("Authorization", None)
        stored_headers.pop("authorization", None)
        payload = {
            "ts": time.time(),
            "status": getattr(response, "status", 200),
            "headers": stored_headers,
            "body_b64": base64.b64encode(body).decode("ascii"),
        }
        tmp = path.with_suffix(path.suffix + ".tmp")
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(payload, fh)
        os.chmod(tmp, stat.S_IRUSR | stat.S_IWUSR)  # 0600
        os.replace(tmp, path)  # atomic on POSIX

    def clear(self) -> None:
        """Remove all cached entries from disk."""
        if not self._dir.exists():
            return
        for child in self._dir.iterdir():
            try:
                child.unlink()
            except OSError:
                pass

    # -- helpers ------------------------------------------------------------

    def _path_for(self, method: str, url: str, scope: str = "public", representation: str = "wildcard") -> Path:
        key = f"{method}:{url}:{scope}:{representation}"
        digest = hashlib.sha256(key.encode()).hexdigest()
        return self._dir / digest


def _ensure_dir(directory: Path) -> None:
    """Create *directory* with ``0700`` permissions, including missing
    parents.  Pre-existing parent directories are **never** chmod-ed —
    only the target directory itself and any missing ancestors are
    clamped to ``0700``."""
    # Collect ancestors that do not exist yet so we only fix
    # permissions on directories we actually created.  The target
    # directory itself is always clamped regardless of whether it
    # pre-existed.
    missing: list[Path] = []
    p = directory
    while not p.exists():
        missing.append(p)
        p = p.parent

    directory.mkdir(parents=True, exist_ok=True)
    for created in missing:
        try:
            created.chmod(stat.S_IRUSR | stat.S_IWUSR | stat.S_IXUSR)
        except (OSError, PermissionError):
            pass

    # Always clamp the target directory even if it existed before we
    # were called — it may have been created with permissive
    # permissions by another process or an earlier bug.
    if not missing or missing[-1] != directory:
        # Directory existed before; clamp it.
        try:
            directory.chmod(stat.S_IRUSR | stat.S_IWUSR | stat.S_IXUSR)
        except (OSError, PermissionError):
            pass


def _cached_response(status: int, headers: dict[str, str], body: bytes) -> object:
    """Reconstruct an ``HttpResponse``-compatible object."""
    return type("_CachedResponse", (), {
        "status": status,
        "headers": headers,
        "body": body,
    })()


# ---------------------------------------------------------------------------
# Two-tier transport (memory + disk)
# ---------------------------------------------------------------------------


# Sentinel for "no disk cache argument was passed" — distinct from
# ``None`` (which means "caller explicitly wants no disk cache").
_DISK_CACHE_UNSET: object = object()


class CachingHttpTransport(HttpTransport):
    """Read-through HTTP cache with in-memory and on-disk tiers.

    On a cache miss the delegate transport is called and the response
    is stored in both tiers.  On a hit the in-memory tier is checked
    first; the disk tier provides persistence across CLI invocations.

    **Auth isolation**: The in-memory and disk caches derive a
    non-secret *scope* from the ``Authorization`` header.  Responses
    fetched with one token are never served to a caller with a
    different token (or no token).

    Parameters:
        delegate: The underlying transport to call on cache miss.
        ttl: Cache TTL in seconds.  ``None`` means entries never expire.
        disk_cache: Optional :class:`DiskCache` for persistence.
            When omitted **and** *ttl* is a non-``None`` int, a disk
            cache is created automatically at the default location.
            Pass ``None`` explicitly to disable disk persistence
            regardless of *ttl* (useful in tests).
    """

    __slots__ = ("_delegate", "_ttl", "_mem", "_disk")

    def __init__(
        self,
        delegate: HttpTransport,
        ttl: int | None = None,
        disk_cache: DiskCache | None = _DISK_CACHE_UNSET,  # type: ignore[assignment]
    ) -> None:
        self._delegate = delegate
        self._ttl = ttl
        # Key: (method, url, scope, representation)
        self._mem: dict[tuple[str, str, str, str], tuple[float, object]] = {}
        if disk_cache is _DISK_CACHE_UNSET:
            if ttl is not None:
                disk_cache = DiskCache(_default_cache_dir(), ttl=ttl)
            else:
                disk_cache = None
        self._disk = disk_cache

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def request(
        self,
        method: str,
        url: str,
        *,
        headers: object = (),
        nocache: bool = False,
    ) -> object:
        # For credential-bearing requests (e.g. Docker bearer-token
        # endpoints), skip caching entirely to avoid persisting secrets
        # in the disk cache.
        if nocache:
            headers_dict: dict[str, str] = {}
            if headers is not None:
                if hasattr(headers, "items"):
                    headers_dict = dict(headers)  # type: ignore[arg-type]
                elif isinstance(headers, (list, tuple)):
                    headers_dict = dict(headers)
            return self._delegate.request(method, url, headers=headers_dict)

        scope = _derive_scope(headers)
        representation = _derive_representation(headers)
        key = (method, url, scope, representation)
        now = time.monotonic()

        # 1. In-memory (fastest)
        entry = self._mem.get(key)
        if entry is not None:
            ts, resp = entry
            if self._ttl is None or (now - ts) < self._ttl:
                return resp

        # 2. Disk (persistent across invocations)
        if self._disk is not None:
            cached = self._disk.get(method, url, scope=scope, representation=representation)
            if cached is not None:
                self._mem[key] = (now, cached)
                return cached

        # 3. Delegate
        headers_dict: dict[str, str] = {}
        if headers is not None:
            if hasattr(headers, "items"):
                headers_dict = dict(headers)  # type: ignore[arg-type]
            elif isinstance(headers, (list, tuple)):
                headers_dict = dict(headers)

        resp = self._delegate.request(method, url, headers=headers_dict)
        self._mem[key] = (now, resp)
        if self._disk is not None:
            self._disk.set(method, url, resp, scope=scope, representation=representation)
        return resp

    def clear(self) -> None:
        """Remove all cached entries (memory + disk)."""
        self._mem.clear()
        if self._disk is not None:
            self._disk.clear()

    @property
    def size(self) -> int:
        """Number of entries in the in-memory cache."""
        return len(self._mem)

    @property
    def ttl(self) -> int | None:
        """Current TTL (seconds) or ``None`` for infinite."""
        return self._ttl

    @property
    def disk(self) -> DiskCache | None:
        """The underlying disk cache, if any."""
        return self._disk
