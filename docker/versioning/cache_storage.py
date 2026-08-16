"""Pure cache-root resolution and named child derivation.

Phase 1 owns path selection only.  Every function in this module is
lexical and deterministic: it performs no filesystem reads or mutations
and has no implicit current-working-directory dependence.  The module
deliberately imports no CLI, launcher, transport, HTTP response-cache,
artifact-verification, or provider module so it remains an acyclic leaf
that those consumers can depend on safely.
"""
from __future__ import annotations

import os
from pathlib import Path

_CACHE_ROOT_NAME = "docker-constructor"
_VERSIONING_CHILD = Path("versioning")
_RUNTIME_ARTIFACTS_BLOBS_CHILD = Path("runtime-artifacts") / "blobs"


class CacheStorageError(ValueError):
    """Invalid or unsafe cache-root configuration."""


def _normalize(path: str | Path) -> Path:
    """Lexically normalize *path* without touching the filesystem.

    ``os.path.normpath`` preserves an exact two-leading-slash prefix even
    though Linux resolves ``//x`` identically to ``/x``.  Collapse that
    prefix so unsafe-root comparison cannot be bypassed through ``//``,
    ``//xdg/cache``, or ``//xdg``.
    """
    value = os.path.normpath(str(path))
    if value.startswith("//") and not value.startswith("///"):
        value = "/" + value.lstrip("/")
    return Path(value)


def resolve_default_root(xdg_cache_home: str | None, *, home: Path) -> Path:
    """Return the default constructor cache root.

    Uses ``${XDG_CACHE_HOME}/docker-constructor`` only when
    ``XDG_CACHE_HOME`` is non-empty and absolute; otherwise falls back to
    ``~/.cache/docker-constructor`` under *home*.
    """
    if xdg_cache_home and os.path.isabs(xdg_cache_home):
        return _normalize(xdg_cache_home) / _CACHE_ROOT_NAME
    return _normalize(home) / ".cache" / _CACHE_ROOT_NAME


def resolve_local_root(
    value: str | None,
    *,
    xdg_cache_home: str | None,
    home: Path,
) -> Path | None:
    """Validate a local ``[cache].dir`` override and return its root.

    Returns ``None`` when no override is configured.  Rejects empty,
    relative, or ``~``-prefixed values, and rejects an absolute value that
    lexically normalizes to ``XDG_CACHE_HOME``, the invoking user's home
    directory, the filesystem root, or an ancestor of ``XDG_CACHE_HOME``.
    """
    if value is None:
        return None

    if not value or not os.path.isabs(value):
        raise CacheStorageError(
            "local.cache.dir must be an absolute path; set [cache].dir to a "
            "dedicated absolute directory"
        )

    root = _normalize(value)
    home_root = _normalize(home)
    filesystem_root = _normalize("/")

    xdg_root: Path | None = None
    if xdg_cache_home and os.path.isabs(xdg_cache_home):
        xdg_root = _normalize(xdg_cache_home)

    if xdg_root is not None and root == xdg_root:
        raise CacheStorageError(
            "local.cache.dir equals XDG_CACHE_HOME; choose a dedicated child "
            f"directory such as {xdg_root / 'docker-constructor-custom'}"
        )

    if root == home_root:
        raise CacheStorageError(
            "local.cache.dir equals the invoking user's home directory; "
            "choose a dedicated owned directory"
        )

    if root == filesystem_root:
        raise CacheStorageError(
            "local.cache.dir is the filesystem root; choose a dedicated owned "
            "directory"
        )

    if xdg_root is not None and xdg_root.is_relative_to(root):
        raise CacheStorageError(
            "local.cache.dir is an ancestor of XDG_CACHE_HOME; choose a "
            "dedicated owned directory"
        )

    return root


def versioning_child(root: Path) -> Path:
    """Return the HTTP cache child beneath *root*."""
    return Path(root) / _VERSIONING_CHILD


def runtime_artifacts_blobs_child(root: Path) -> Path:
    """Return the verified artifact blob child beneath *root*."""
    return Path(root) / _RUNTIME_ARTIFACTS_BLOBS_CHILD
