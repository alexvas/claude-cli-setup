"""TOML inventory loader and validator.

No Docker, network, or subprocess.  Uses only tomllib (stdlib 3.11+),
dataclasses, re, pathlib, and types.
"""
from __future__ import annotations

import re
import tomllib
from pathlib import Path
from types import MappingProxyType
from typing import Any, Mapping, Optional, Union

from .errors import ConstraintSyntaxError, InventoryError, VersionConfigError, VersionSyntaxError
from .constraints import (
    parse_numeric_version,
    parse_constraint,
    validate_constraint_consistency,
    NumericVersion,
)
from .model import (
    ArtifactEntry,
    BaseStage,
    CacheConfig,
    DockerRegistrySource,
    DockerRegistryUpdate,
    FdPrebuiltStage,
    GitHubReleaseSource,
    GitHubReleaseUpdate,
    GitRefUpdate,
    GitSource,
    Inventory,
    NodeEntry,
    NpmSource,
    NpmToolEntry,
    NpmUpdate,
    OhMyZshEntry,
    OpenSpecToolsStage,
    OverridePolicy,
    PiExtensionEntry,
    PiToolsStage,
    PrebuiltToolEntry,
    PyPiSource,
    PyPiUpdate,
    PythonEntry,
    RtkPrebuiltStage,
    RuntimeStage,
    RustChannelSource,
    RustChannelUpdate,
    RustEntry,
    Stages,
    ToolchainStage,
    TyEntry,
    UvEntry,
    UvPythonSource,
    UvPythonUpdate,
)


# ---------------------------------------------------------------------------
# Regex constants
# ---------------------------------------------------------------------------

SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
NODE_DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
GIT_REVISION_RE = re.compile(r"^[0-9a-f]{40}$")
_MOVING_VERSION_TAGS = frozenset({"latest", "stable", "next", "dev", "canary", "nightly"})

# Semver pattern for extensions: X.Y.Z with optional prerelease/build.
# Must match https://semver.org — rejects malformed suffixes like "-!!!" or "-01".
_SEMVER_RE = re.compile(
    r"""
    ^
    (0|[1-9]\d*)               # major
    \.
    (0|[1-9]\d*)               # minor
    \.
    (0|[1-9]\d*)               # patch
    (?:
        -                      # prerelease hyphen
        (                      # prerelease identifiers
            (?:0|[1-9]\d*|\d*[a-zA-Z-][0-9a-zA-Z-]*)
            (?:\.(?:0|[1-9]\d*|\d*[a-zA-Z-][0-9a-zA-Z-]*))*
        )
    )?
    (?:
        \+                     # build plus sign
        (                      # build identifiers
            [0-9a-zA-Z-]+
            (?:\.[0-9a-zA-Z-]+)*
        )
    )?
    $
    """,
    re.VERBOSE,
)

VERSION_STRICT_RE = re.compile(r"^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$")
PREBUILT_VERSION_RE = re.compile(r"^v(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$")

# Moving version tags forbidden everywhere (Rust selectors, npm tags, etc.)
_MOVING_RUST_SELECTORS = frozenset({"stable", "beta", "nightly"})
_MOVING_VERSION_TAGS = frozenset({"latest", "stable", "next", "dev", "canary", "nightly"})


# ---------------------------------------------------------------------------
# Helpers for TOML access with dot-path error reporting
# ---------------------------------------------------------------------------

def _dot(path: tuple[str, ...]) -> str:
    return ".".join(path)


def require_table(
    data: Mapping[str, object],
    path: tuple[str, ...],
) -> Mapping[str, object]:
    current: Any = data
    for key in path:
        if not isinstance(current, dict):
            raise InventoryError(
                f"{_dot(path[:path.index(key)])}: expected table, got {type(current).__name__}"
            )
        if key not in current:
            raise InventoryError(f"{_dot(path)}: missing required key")
        current = current[key]
    if not isinstance(current, dict):
        raise InventoryError(
            f"{_dot(path)}: expected table, got {type(current).__name__}"
        )
    return current


def require_string(
    data: Mapping[str, object],
    path: tuple[str, ...],
) -> str:
    *parent_path, key = path
    current = require_table(data, tuple(parent_path)) if parent_path else data
    if key not in current:
        raise InventoryError(f"{_dot(path)}: missing required key")
    value = current[key]
    if not isinstance(value, str):
        raise InventoryError(
            f"{_dot(path)}: expected string, got {type(value).__name__}"
        )
    return value


def require_bool(
    data: Mapping[str, object],
    path: tuple[str, ...],
) -> bool:
    *parent_path, key = path
    current = require_table(data, tuple(parent_path)) if parent_path else data
    if key not in current:
        raise InventoryError(f"{_dot(path)}: missing required key")
    value = current[key]
    if not isinstance(value, bool):
        raise InventoryError(
            f"{_dot(path)}: expected boolean, got {type(value).__name__}"
        )
    return value


def require_int(
    data: Mapping[str, object],
    path: tuple[str, ...],
) -> int:
    *parent_path, key = path
    current = require_table(data, tuple(parent_path)) if parent_path else data
    if key not in current:
        raise InventoryError(f"{_dot(path)}: missing required key")
    value = current[key]
    if not isinstance(value, int) or isinstance(value, bool):
        raise InventoryError(
            f"{_dot(path)}: expected integer, got {type(value).__name__}"
        )
    return value


def require_nonempty_string(
    data: Mapping[str, object],
    path: tuple[str, ...],
) -> str:
    value = require_string(data, path)
    if not value.strip():
        raise InventoryError(f"{_dot(path)}: must not be empty")
    return value


# ---------------------------------------------------------------------------
# PathReader
# ---------------------------------------------------------------------------

class _PathReader:
    """Wraps a raw TOML dict for dot-path-aware validation."""

    def __init__(self, root: Mapping[str, object]):
        self._root = root

    def tbl(self, path: tuple[str, ...]) -> Mapping[str, object]:
        return require_table(self._root, path)

    def str(self, path: tuple[str, ...]) -> str:
        return require_string(self._root, path)

    def nonempty_str(self, path: tuple[str, ...]) -> str:
        return require_nonempty_string(self._root, path)

    def bool(self, path: tuple[str, ...]) -> bool:
        return require_bool(self._root, path)

    def int(self, path: tuple[str, ...]) -> int:
        return require_int(self._root, path)

    @property
    def root(self) -> Mapping[str, object]:
        return self._root


# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------

def _validate_sha256(hex_str: str, path: str) -> None:
    if not SHA256_RE.match(hex_str):
        raise InventoryError(
            f"{path}: expected 64 hexadecimal characters, got {hex_str!r}"
        )


def _validate_node_digest(raw: str, path: str) -> None:
    if ":" not in raw:
        raise InventoryError(
            f"{path}: expected 'sha256:<hex>', missing colon in {raw!r}"
        )
    if not NODE_DIGEST_RE.match(raw):
        raise InventoryError(
            f"{path}: expected 'sha256:<64 lowercase hex>', got {raw!r}"
        )
    hex_part = raw.removeprefix("sha256:")
    if len(set(hex_part)) == 1:
        raise InventoryError(
            f"{path}: checksum looks like a placeholder"
        )


def _validate_url_contains_version(url: str, version: str, path: str) -> None:
    if version not in url:
        raise InventoryError(
            f"{path}: URL must contain the declared version {version!r}"
        )


def _validate_linux_amd64_artifact(
    artifacts: Mapping[str, object], parent_path: str
) -> None:
    if "linux-amd64" not in artifacts:
        raise InventoryError(
            f"{parent_path}.artifacts: missing required 'linux-amd64' platform artifact"
        )


def _reject_placeholder_sha256(sha256: str, path: str) -> None:
    if len(set(sha256)) == 1:
        raise InventoryError(
            f"{path}: checksum looks like a placeholder"
        )


def _reject_moving_rust_version(version: str, path: str) -> None:
    base = version.split("-")[0].lower()
    if base in _MOVING_RUST_SELECTORS:
        raise InventoryError(
            f"{path}: moving selector {version!r} is not allowed, use explicit X.Y.Z"
        )


def _validate_rust_version(version: str, path: str) -> None:
    """Rust version must be exact X.Y.Z — rejects arbitrary strings and moving
    selectors such as stable/beta/nightly.
    """
    _reject_moving_rust_version(version, path)
    if not VERSION_STRICT_RE.match(version):
        raise InventoryError(
            f"{path}: expected exact X.Y.Z version, got {version!r}"
        )


def _validate_npm_version(version: str, path: str) -> None:
    """npm tool version must be exact X.Y.Z — rejects ranges and tags like 'latest'."""
    if not VERSION_STRICT_RE.match(version):
        raise InventoryError(
            f"{path}: expected exact X.Y.Z version, got {version!r}"
        )


def _validate_uv_version(version: str, path: str) -> None:
    """UV version must be exact X.Y.Z — rejects ranges, tags, and v-prefix."""
    if not VERSION_STRICT_RE.match(version):
        raise InventoryError(
            f"{path}: expected exact X.Y.Z version, got {version!r}"
        )


def _validate_prebuilt_version(version: str, path: str) -> None:
    """Prebuilt-tool version must be vX.Y.Z — rejects bare X.Y.Z, ranges, tags."""
    if not PREBUILT_VERSION_RE.match(version):
        raise InventoryError(
            f"{path}: expected vX.Y.Z version, got {version!r}"
        )


def _validate_extension_version(version: str, path: str) -> None:
    """Extension version must be a valid semver (https://semver.org), not a moving tag.

    Accepts X.Y.Z and semver prerelease/build forms (e.g., 0.2.0-beta.1).
    Rejects moving tags like 'latest', 'stable', 'next', 'dev', 'canary', 'nightly',
    and malformed suffixes like '-!!!' or '-01'.
    """
    lower = version.lower()
    if lower in _MOVING_VERSION_TAGS:
        raise InventoryError(
            f"{path}: moving version tag {version!r} is not allowed"
        )
    if not _SEMVER_RE.match(version):
        raise InventoryError(
            f"{path}: invalid semver version {version!r}"
        )


# ---------------------------------------------------------------------------
# Unknown-key rejection
# ---------------------------------------------------------------------------

# Allowed keys for every known TOML table (relative to stages/ runtime/).
# Extra keys or typoed fields cause path-qualified InventoryError.

_KNOWN_KEYS: dict[tuple[str, ...], frozenset[str]] = {}


def _register(path: tuple[str, ...], *keys: str) -> None:
    _KNOWN_KEYS[path] = frozenset(keys)


# --- Top-level ---
_register((), "schema", "stages", "runtime")
_register(("stages",), "base", "toolchain", "rtk-prebuilt", "fd-prebuilt",
          "pi-tools", "openspec-tools", "runtime")
_register(("stages", "base"), "node")
_register(("stages", "base", "node"), "tag", "digest", "source", "update")
_register(("stages", "base", "node", "source"), "type", "registry", "repository")
_register(("stages", "base", "node", "update"), "provider", "stable_only", "track")

_register(("stages", "toolchain"), "rust", "uv", "python", "ty")
_register(("stages", "toolchain", "rust"), "version", "profile", "components", "source", "update")
_register(("stages", "toolchain", "rust", "source"), "type", "manifest")
_register(("stages", "toolchain", "rust", "update"), "provider", "channel", "stable_only")

_register(("stages", "toolchain", "uv"), "version", "source", "artifacts", "update")
_register(("stages", "toolchain", "uv", "source"), "type", "repository", "tag")
_register(("stages", "toolchain", "uv", "update"), "provider", "stable_only", "tag_prefix", "required_platforms")
_register(("stages", "toolchain", "uv", "artifacts", "__ANY__"), "url", "sha256")

_register(("stages", "toolchain", "python"), "version", "source", "update", "override")
_register(("stages", "toolchain", "python", "source"), "type", "implementation")
_register(("stages", "toolchain", "python", "update"), "provider", "implementation", "stable_only")
_register(("stages", "toolchain", "python", "override"), "constraint", "allow_prerelease", "scheme")

_register(("stages", "toolchain", "ty"), "version", "source", "update")
_register(("stages", "toolchain", "ty", "source"), "type", "package")
_register(("stages", "toolchain", "ty", "update"), "provider", "stable_only")

for _prebuilt_stage, _tool_name in [("rtk-prebuilt", "rtk"), ("fd-prebuilt", "fd")]:
    _register(("stages", _prebuilt_stage), _tool_name)
    _register(("stages", _prebuilt_stage, _tool_name), "version", "source", "artifacts", "update")
    _register(("stages", _prebuilt_stage, _tool_name, "source"), "type", "repository", "tag")
    _register(("stages", _prebuilt_stage, _tool_name, "update"), "provider", "stable_only", "tag_prefix", "required_platforms")
    _register(("stages", _prebuilt_stage, _tool_name, "artifacts", "__ANY__"), "url", "sha256")

for _npm_stage, _npm_name in [("pi-tools", "pi"), ("openspec-tools", "openspec")]:
    _register(("stages", _npm_stage), _npm_name)
    _register(("stages", _npm_stage, _npm_name), "version", "source", "update")
    _register(("stages", _npm_stage, _npm_name, "source"), "type", "package")
    _register(("stages", _npm_stage, _npm_name, "update"), "provider", "stable_only")

_register(("stages", "runtime"), "oh-my-zsh")
_register(("stages", "runtime", "oh-my-zsh"), "revision", "source", "update")
_register(("stages", "runtime", "oh-my-zsh", "source"), "type", "repository")
_register(("stages", "runtime", "oh-my-zsh", "update"), "provider", "ref")

# Runtime pi-extensions (dynamic — allowed keys defined per entry)
_register(("runtime",), "pi-extensions")
_register(("runtime", "pi-extensions", "__ANY__"), "version", "source", "update")
_register(("runtime", "pi-extensions", "__ANY__", "source"), "type", "package")
_register(("runtime", "pi-extensions", "__ANY__", "update"), "provider", "stable_only")


def _check_unknown_keys(table: Mapping[str, object], path: tuple[str, ...], *, allowed: set[str] | None = None) -> None:
    """Raise InventoryError if *table* contains keys not in the known set for *path*.

    The special key ``__ANY__`` in the registry matches any last component,
    which supports dynamic tables like pi-extensions.

    If *allowed* is given it serves as an explicit override — the registry
    lookup is skipped entirely.
    """
    if allowed is not None:
        for key in table:
            if key not in allowed:
                raise InventoryError(
                    f"{_dot(path + (key,))}: unknown key {key!r}"
                )
        return

    registry = _KNOWN_KEYS.get(path)
    if registry is None:
        # Try ancestor with __ANY__ wildcard in the last component
        for depth in range(len(path), 0, -1):
            candidate = path[:depth - 1] + ("__ANY__",) + path[depth:]
            registry = _KNOWN_KEYS.get(candidate)
            if registry is not None:
                break
    if registry is None:
        return  # No rule → skip (top-level or genuinely dynamic)

    for key in table:
        if key not in registry:
            raise InventoryError(
                f"{_dot(path + (key,))}: unknown key {key!r}"
            )


def _parse_override_policy(
    override_data: Mapping[str, object], path_prefix: str
) -> OverridePolicy:
    constraint_str = require_string(override_data, ("constraint",))
    try:
        constraint = parse_constraint(constraint_str)
    except ConstraintSyntaxError as e:
        raise ConstraintSyntaxError(f"{path_prefix}.constraint: {e}") from e

    allow_prerelease = require_bool(override_data, ("allow_prerelease",))
    scheme = require_string(override_data, ("scheme",))

    if scheme not in ("numeric",):
        raise InventoryError(
            f"{path_prefix}.scheme: unsupported scheme {scheme!r}, only 'numeric' is allowed"
        )

    if scheme == "numeric" and allow_prerelease:
        raise InventoryError(
            f"{path_prefix}.allow_prerelease: numeric scheme does not support prereleases"
        )

    try:
        validate_constraint_consistency(constraint)
    except ConstraintSyntaxError as e:
        raise ConstraintSyntaxError(f"{path_prefix}.constraint: {e}") from e

    return OverridePolicy(
        constraint=constraint,
        allow_prerelease=allow_prerelease,
        scheme=scheme,
    )


# ---------------------------------------------------------------------------
# Source / Update loader — explicit dispatch (no generic dict[str, type])
# ---------------------------------------------------------------------------

def _load_source(r: _PathReader, path: tuple[str, ...]) -> Any:
    """Parse a [*.source] table and return the typed source dataclass."""
    source_data = r.tbl(path + ("source",))
    stype = require_string(r.root, path + ("source", "type"))
    dot = _dot(path)

    if stype == "github-release":
        repository = require_nonempty_string(r.root, path + ("source", "repository"))
        tag = require_nonempty_string(r.root, path + ("source", "tag"))
        return GitHubReleaseSource(repository=repository, tag=tag)

    elif stype == "npm":
        package = require_nonempty_string(r.root, path + ("source", "package"))
        return NpmSource(package=package)

    elif stype == "pypi":
        package = require_nonempty_string(r.root, path + ("source", "package"))
        return PyPiSource(package=package)

    elif stype == "uv-python":
        impl = require_nonempty_string(r.root, path + ("source", "implementation"))
        if impl != "cpython":
            raise InventoryError(
                f"{dot}.source.implementation: unsupported implementation {impl!r}, only 'cpython' is allowed"
            )
        return UvPythonSource(implementation=impl)

    elif stype == "rust-channel":
        manifest = require_nonempty_string(r.root, path + ("source", "manifest"))
        return RustChannelSource(manifest=manifest)

    elif stype == "docker-registry":
        registry = require_nonempty_string(r.root, path + ("source", "registry"))
        repository = require_nonempty_string(r.root, path + ("source", "repository"))
        return DockerRegistrySource(registry=registry, repository=repository)

    elif stype == "git":
        repository = require_nonempty_string(r.root, path + ("source", "repository"))
        return GitSource(repository=repository)

    else:
        raise InventoryError(
            f"{dot}.source.type: unknown source type {stype!r}"
        )


def _load_update(r: _PathReader, path: tuple[str, ...]) -> Any:
    """Parse a [*.update] table and return the typed update dataclass."""
    update_data = r.tbl(path + ("update",))
    provider = require_string(r.root, path + ("update", "provider"))
    dot = _dot(path)

    if provider == "github-release":
        stable_only = require_bool(r.root, path + ("update", "stable_only"))
        tag_prefix = update_data.get("tag_prefix", "")
        if not isinstance(tag_prefix, str):
            raise InventoryError(
                f"{dot}.update.tag_prefix: expected string, got {type(tag_prefix).__name__}"
            )
        rp_raw = update_data.get("required_platforms", [])
        if not isinstance(rp_raw, list) or not all(isinstance(x, str) for x in rp_raw):
            raise InventoryError(
                f"{dot}.update.required_platforms: expected list of strings"
            )
        return GitHubReleaseUpdate(
            stable_only=stable_only,
            tag_prefix=tag_prefix,
            required_platforms=tuple(rp_raw),
        )

    elif provider == "npm":
        stable_only = require_bool(r.root, path + ("update", "stable_only"))
        return NpmUpdate(stable_only=stable_only)

    elif provider == "pypi":
        stable_only = require_bool(r.root, path + ("update", "stable_only"))
        return PyPiUpdate(stable_only=stable_only)

    elif provider == "uv-python":
        impl = require_nonempty_string(r.root, path + ("update", "implementation"))
        if impl != "cpython":
            raise InventoryError(
                f"{dot}.update.implementation: unsupported implementation {impl!r}, only 'cpython' is allowed"
            )
        stable_only = require_bool(r.root, path + ("update", "stable_only"))
        return UvPythonUpdate(implementation=impl, stable_only=stable_only)

    elif provider == "rust-channel":
        channel = require_nonempty_string(r.root, path + ("update", "channel"))
        if channel != "stable":
            raise InventoryError(
                f"{dot}.update.channel: unsupported channel {channel!r}, only 'stable' is allowed"
            )
        stable_only = require_bool(r.root, path + ("update", "stable_only"))
        return RustChannelUpdate(channel=channel, stable_only=stable_only)

    elif provider == "docker-registry":
        stable_only = require_bool(r.root, path + ("update", "stable_only"))
        track = require_string(r.root, path + ("update", "track"))
        if track != "tag-digest":
            raise InventoryError(
                f"{dot}.update.track: unsupported track {track!r}, only 'tag-digest' is allowed"
            )
        return DockerRegistryUpdate(stable_only=stable_only, track=track)

    elif provider == "git-ref":
        ref = require_nonempty_string(r.root, path + ("update", "ref"))
        return GitRefUpdate(ref=ref)

    else:
        raise InventoryError(
            f"{dot}.update.provider: unknown provider {provider!r}"
        )


# ---------------------------------------------------------------------------
# Source/Update compatibility
# ---------------------------------------------------------------------------

_SOURCE_UPDATE_MAP = {
    "github-release": "github-release",
    "npm": "npm",
    "pypi": "pypi",
    "uv-python": "uv-python",
    "rust-channel": "rust-channel",
    "docker-registry": "docker-registry",
    "git": "git-ref",
}


def _check_compat(source_type: str, update_provider: str, dot: str) -> None:
    expected = _SOURCE_UPDATE_MAP.get(source_type)
    if expected != update_provider:
        raise InventoryError(
            f"{dot}.update.provider: provider {update_provider!r} "
            f"is incompatible with source type {source_type!r}"
        )


# ---------------------------------------------------------------------------
# Entry-specific mandated source/update types
# ---------------------------------------------------------------------------

# Each entry has exactly one legal source type and one legal update provider.
# This is stricter than generic compatibility: Python must be uv-python (not
# pypi even though pypi↔pypi is a valid pair), Rust must be rust-channel,
# etc.

_ENTRY_SOURCE_CLASSES = {
    "stages.base.node": (DockerRegistrySource, DockerRegistryUpdate),
    "stages.toolchain.rust": (RustChannelSource, RustChannelUpdate),
    "stages.toolchain.uv": (GitHubReleaseSource, GitHubReleaseUpdate),
    "stages.toolchain.python": (UvPythonSource, UvPythonUpdate),
    "stages.toolchain.ty": (PyPiSource, PyPiUpdate),
    "stages.rtk-prebuilt.rtk": (GitHubReleaseSource, GitHubReleaseUpdate),
    "stages.fd-prebuilt.fd": (GitHubReleaseSource, GitHubReleaseUpdate),
    "stages.pi-tools.pi": (NpmSource, NpmUpdate),
    "stages.openspec-tools.openspec": (NpmSource, NpmUpdate),
    "stages.runtime.oh-my-zsh": (GitSource, GitRefUpdate),
}


def _check_entry_source_update(
    source: Any, update: Any, dot: str
) -> None:
    """Verify that source and update objects match the mandated classes for *dot*."""
    expected = _ENTRY_SOURCE_CLASSES.get(dot)
    if expected is None:
        return  # pi-extensions handled separately
    exp_src_cls, exp_upd_cls = expected
    if type(source) is not exp_src_cls:
        actual_type = getattr(source, "type", type(source).__name__)
        raise InventoryError(
            f"{dot}.source.type: expected {exp_src_cls.type!r} for this entry, "
            f"got {actual_type!r}"
        )
    if type(update) is not exp_upd_cls:
        actual_prov = getattr(update, "provider", type(update).__name__)
        raise InventoryError(
            f"{dot}.update.provider: expected {exp_upd_cls.provider!r} for this entry, "
            f"got {actual_prov!r}"
        )


# ---------------------------------------------------------------------------
# Artifact loading
# ---------------------------------------------------------------------------

def _load_artifacts(
    r: _PathReader, path: tuple[str, ...], version: str
) -> dict[str, ArtifactEntry]:
    dot = _dot(path)
    artifacts_data = r.tbl(path + ("artifacts",))
    _validate_linux_amd64_artifact(artifacts_data, dot)

    artifacts: dict[str, ArtifactEntry] = {}
    for platform in artifacts_data:
        # Validate platform artifact table keys (url + sha256 only, no typos like sh256)
        plat_path = path + ("artifacts", platform)
        _check_unknown_keys(r.tbl(plat_path), plat_path)
        art_url = r.str(path + ("artifacts", platform, "url"))
        art_sha256 = r.str(path + ("artifacts", platform, "sha256"))
        _validate_sha256(art_sha256, f"{dot}.artifacts.{platform}.sha256")
        _reject_placeholder_sha256(art_sha256, f"{dot}.artifacts.{platform}.sha256")
        _validate_url_contains_version(
            art_url, version, f"{dot}.artifacts.{platform}.url"
        )
        artifacts[platform] = ArtifactEntry(url=art_url, sha256=art_sha256)

    return artifacts


def _validate_required_platforms(
    upd: Any,
    artifacts: dict[str, ArtifactEntry],
    dot: str,
) -> None:
    if isinstance(upd, GitHubReleaseUpdate) and upd.required_platforms:
        for rp in upd.required_platforms:
            if rp not in artifacts:
                raise VersionConfigError(
                    f"{dot}.update.required_platforms: "
                    f"required platform {rp!r} has no artifact entry"
                )


# ---------------------------------------------------------------------------
# Inventory loader
# ---------------------------------------------------------------------------

def load_inventory(versions_path: Path) -> Inventory:
    """Load and validate a versions.toml inventory file."""
    with versions_path.open("rb") as stream:
        raw = tomllib.load(stream)
    return validate_inventory(raw)


def validate_inventory(raw: Mapping[str, object]) -> Inventory:
    """Validate raw TOML data and return an Inventory."""
    r = _PathReader(raw)

    # Schema
    if "schema" not in raw:
        raise InventoryError("schema: missing required top-level key")
    schema = r.int(("schema",))

    if schema != 1:
        raise InventoryError(f"schema: unsupported version {schema}, only 1 is supported")

    # --- top-level unknown keys ---
    known_top = {"schema", "stages", "runtime", "cache"}
    _check_unknown_keys(raw, (), allowed=known_top)

    # --- base ---
    _check_unknown_keys(r.tbl(("stages",)), ("stages",))
    _check_unknown_keys(r.tbl(("stages", "base",)), ("stages", "base",))
    _check_unknown_keys(r.tbl(("stages", "base", "node",)), ("stages", "base", "node",))
    tag = r.str(("stages", "base", "node", "tag"))
    digest = r.str(("stages", "base", "node", "digest"))
    _validate_node_digest(digest, "stages.base.node.digest")
    node_source = _load_source(r, ("stages", "base", "node"))
    node_update = _load_update(r, ("stages", "base", "node"))
    _check_compat(node_source.type, node_update.provider, "stages.base.node")
    _check_entry_source_update(node_source, node_update, "stages.base.node")
    _check_unknown_keys(r.tbl(("stages", "base", "node", "source",)), ("stages", "base", "node", "source",))
    _check_unknown_keys(r.tbl(("stages", "base", "node", "update",)), ("stages", "base", "node", "update",))

    # --- toolchain: rust ---
    _check_unknown_keys(r.tbl(("stages", "toolchain",)), ("stages", "toolchain",))
    _check_unknown_keys(r.tbl(("stages", "toolchain", "rust",)), ("stages", "toolchain", "rust",))
    rust_version = r.str(("stages", "toolchain", "rust", "version"))
    _validate_rust_version(rust_version, "stages.toolchain.rust.version")
    rust_profile = r.str(("stages", "toolchain", "rust", "profile"))
    rust_data = r.tbl(("stages", "toolchain", "rust"))
    components_raw = rust_data.get("components")
    if not isinstance(components_raw, list):
        raise InventoryError("stages.toolchain.rust.components: expected list")
    components: list[str] = []
    for i, c in enumerate(components_raw):
        if not isinstance(c, str):
            raise InventoryError(
                f"stages.toolchain.rust.components[{i}]: expected string"
            )
        components.append(c)
    rust_source = _load_source(r, ("stages", "toolchain", "rust"))
    rust_update = _load_update(r, ("stages", "toolchain", "rust"))
    _check_compat(rust_source.type, rust_update.provider, "stages.toolchain.rust")
    _check_entry_source_update(rust_source, rust_update, "stages.toolchain.rust")
    _check_unknown_keys(r.tbl(("stages", "toolchain", "rust", "source",)), ("stages", "toolchain", "rust", "source",))
    _check_unknown_keys(r.tbl(("stages", "toolchain", "rust", "update",)), ("stages", "toolchain", "rust", "update",))
    _validate_url_contains_version(
        rust_source.manifest, rust_version, "stages.toolchain.rust.source.manifest"
    )

    # --- toolchain: uv ---
    _check_unknown_keys(r.tbl(("stages", "toolchain", "uv",)), ("stages", "toolchain", "uv",))
    uv_version = r.str(("stages", "toolchain", "uv", "version"))
    _validate_uv_version(uv_version, "stages.toolchain.uv.version")
    uv_source = _load_source(r, ("stages", "toolchain", "uv"))
    uv_update = _load_update(r, ("stages", "toolchain", "uv"))
    _check_compat(uv_source.type, uv_update.provider, "stages.toolchain.uv")
    _check_entry_source_update(uv_source, uv_update, "stages.toolchain.uv")
    _check_unknown_keys(r.tbl(("stages", "toolchain", "uv", "source",)), ("stages", "toolchain", "uv", "source",))
    _check_unknown_keys(r.tbl(("stages", "toolchain", "uv", "update",)), ("stages", "toolchain", "uv", "update",))
    if isinstance(uv_source, GitHubReleaseSource) and uv_source.tag != uv_version:
        raise VersionConfigError(
            f"stages.toolchain.uv.source.tag: must equal declared version "
            f"({uv_source.tag!r} != {uv_version!r})"
        )
    uv_artifacts = _load_artifacts(r, ("stages", "toolchain", "uv"), uv_version)
    _validate_required_platforms(uv_update, uv_artifacts, "stages.toolchain.uv")

    # --- toolchain: python ---
    _check_unknown_keys(r.tbl(("stages", "toolchain", "python",)), ("stages", "toolchain", "python",))
    py_version = r.str(("stages", "toolchain", "python", "version"))
    try:
        parse_numeric_version(py_version)
    except VersionSyntaxError as e:
        raise VersionSyntaxError(f"stages.toolchain.python.version: {e}") from e
    py_source = _load_source(r, ("stages", "toolchain", "python"))
    py_update = _load_update(r, ("stages", "toolchain", "python"))
    _check_compat(py_source.type, py_update.provider, "stages.toolchain.python")
    _check_entry_source_update(py_source, py_update, "stages.toolchain.python")
    _check_unknown_keys(r.tbl(("stages", "toolchain", "python", "source",)), ("stages", "toolchain", "python", "source",))
    _check_unknown_keys(r.tbl(("stages", "toolchain", "python", "update",)), ("stages", "toolchain", "python", "update",))

    py_override: Optional[OverridePolicy] = None
    py_data = r.tbl(("stages", "toolchain", "python"))
    if "override" in py_data:
        over_data = r.tbl(("stages", "toolchain", "python", "override"))
        _check_unknown_keys(over_data, ("stages", "toolchain", "python", "override",))
        py_override = _parse_override_policy(over_data, "stages.toolchain.python.override")
        py_ver = parse_numeric_version(py_version)
        if not py_override.constraint.matches(py_ver):
            raise VersionConfigError(
                f"stages.toolchain.python.version: {py_version} does not satisfy "
                f"override constraint '{py_override.constraint}'"
            )

    # --- toolchain: ty ---
    _check_unknown_keys(r.tbl(("stages", "toolchain", "ty",)), ("stages", "toolchain", "ty",))
    ty_version = r.str(("stages", "toolchain", "ty", "version"))
    try:
        parse_numeric_version(ty_version)
    except VersionSyntaxError as e:
        raise VersionSyntaxError(f"stages.toolchain.ty.version: {e}") from e
    ty_source = _load_source(r, ("stages", "toolchain", "ty"))
    ty_update = _load_update(r, ("stages", "toolchain", "ty"))
    _check_compat(ty_source.type, ty_update.provider, "stages.toolchain.ty")
    _check_entry_source_update(ty_source, ty_update, "stages.toolchain.ty")
    _check_unknown_keys(r.tbl(("stages", "toolchain", "ty", "source",)), ("stages", "toolchain", "ty", "source",))
    _check_unknown_keys(r.tbl(("stages", "toolchain", "ty", "update",)), ("stages", "toolchain", "ty", "update",))

    # --- prebuilt tools ---
    _check_unknown_keys(r.tbl(("stages", "rtk-prebuilt",)), ("stages", "rtk-prebuilt",))
    _check_unknown_keys(r.tbl(("stages", "fd-prebuilt",)), ("stages", "fd-prebuilt",))
    rtk_tool = _load_prebuilt_tool(r, ("stages", "rtk-prebuilt", "rtk"))
    fd_tool = _load_prebuilt_tool(r, ("stages", "fd-prebuilt", "fd"))

    # --- npm tools ---
    _check_unknown_keys(r.tbl(("stages", "pi-tools",)), ("stages", "pi-tools",))
    _check_unknown_keys(r.tbl(("stages", "openspec-tools",)), ("stages", "openspec-tools",))
    pi_tool = _load_npm_tool(r, ("stages", "pi-tools", "pi"))
    openspec_tool = _load_npm_tool(r, ("stages", "openspec-tools", "openspec"))

    # --- runtime ---
    _check_unknown_keys(r.tbl(("stages", "runtime",)), ("stages", "runtime",))
    _check_unknown_keys(r.tbl(("stages", "runtime", "oh-my-zsh",)), ("stages", "runtime", "oh-my-zsh",))
    omz_revision = r.str(("stages", "runtime", "oh-my-zsh", "revision"))
    if not GIT_REVISION_RE.match(omz_revision):
        raise InventoryError(
            f"stages.runtime.oh-my-zsh.revision: expected 40 hex characters, got {omz_revision!r}"
        )
    omz_source = _load_source(r, ("stages", "runtime", "oh-my-zsh"))
    omz_update = _load_update(r, ("stages", "runtime", "oh-my-zsh"))
    _check_compat(omz_source.type, omz_update.provider, "stages.runtime.oh-my-zsh")
    _check_entry_source_update(omz_source, omz_update, "stages.runtime.oh-my-zsh")
    _check_unknown_keys(r.tbl(("stages", "runtime", "oh-my-zsh", "source",)), ("stages", "runtime", "oh-my-zsh", "source",))
    _check_unknown_keys(r.tbl(("stages", "runtime", "oh-my-zsh", "update",)), ("stages", "runtime", "oh-my-zsh", "update",))

    # --- pi extensions ---
    _check_unknown_keys(r.tbl(("runtime",)), ("runtime",))
    pi_ext_data = r.tbl(("runtime", "pi-extensions"))
    extensions: dict[str, PiExtensionEntry] = {}
    for name, ext_raw in pi_ext_data.items():
        if not isinstance(ext_raw, dict):
            raise InventoryError(
                f"runtime.pi-extensions.{name}: expected table"
            )
        _check_unknown_keys(ext_raw, ("runtime", "pi-extensions", name,))
        ext_version = require_string(raw, ("runtime", "pi-extensions", name, "version"))
        _validate_extension_version(
            ext_version, f"runtime.pi-extensions.{name}.version"
        )
        # Reject entry-level package — it belongs in source
        if "package" in ext_raw:
            raise InventoryError(
                f"runtime.pi-extensions.{name}.package: "
                f"entry-level 'package' is forbidden; use [*.source].package instead"
            )
        ext_source = _load_source(r, ("runtime", "pi-extensions", name))
        ext_update = _load_update(r, ("runtime", "pi-extensions", name))
        _check_compat(ext_source.type, ext_update.provider, f"runtime.pi-extensions.{name}")
        _check_entry_source_update(ext_source, ext_update, None)
        _check_unknown_keys(r.tbl(("runtime", "pi-extensions", name, "source",)), ("runtime", "pi-extensions", name, "source",))
        _check_unknown_keys(r.tbl(("runtime", "pi-extensions", name, "update",)), ("runtime", "pi-extensions", name, "update",))  # passed through _ENTRY_SOURCE_CLASSES special handling
        if type(ext_source) is not NpmSource:
            raise InventoryError(
                f"runtime.pi-extensions.{name}.source.type: "
                f"expected 'npm' for pi extensions, got {ext_source.type!r}"
            )
        if type(ext_update) is not NpmUpdate:
            raise InventoryError(
                f"runtime.pi-extensions.{name}.update.provider: "
                f"expected 'npm' for pi extensions, got {ext_update.provider!r}"
            )
        extensions[name] = PiExtensionEntry(
            version=ext_version,
            source=ext_source,
            update=ext_update,
        )

    return Inventory(
        schema=schema,
        stages=Stages(
            base=BaseStage(
                node=NodeEntry(tag=tag, digest=digest, source=node_source, update=node_update)
            ),
            toolchain=ToolchainStage(
                rust=RustEntry(
                    version=rust_version, profile=rust_profile,
                    components=tuple(components), source=rust_source, update=rust_update,
                ),
                uv=UvEntry(
                    version=uv_version,
                    artifacts=MappingProxyType(uv_artifacts),
                    source=uv_source, update=uv_update,
                ),
                python=PythonEntry(
                    version=py_version, source=py_source, update=py_update, override=py_override,
                ),
                ty=TyEntry(version=ty_version, source=ty_source, update=ty_update),
            ),
            rtk_prebuilt=RtkPrebuiltStage(rtk=rtk_tool),
            fd_prebuilt=FdPrebuiltStage(fd=fd_tool),
            pi_tools=PiToolsStage(pi=pi_tool),
            openspec_tools=OpenSpecToolsStage(openspec=openspec_tool),
            runtime=RuntimeStage(
                oh_my_zsh=OhMyZshEntry(
                    revision=omz_revision, source=omz_source, update=omz_update,
                )
            ),
        ),
        runtime_pi_extensions=MappingProxyType(extensions),
        cache=_load_cache_config(raw),
    )


# ---------------------------------------------------------------------------
# Cache config loader
# ---------------------------------------------------------------------------

def _load_cache_config(raw: Mapping[str, object]) -> CacheConfig | None:
    """Parse and validate the optional ``[cache]`` section."""
    cache_raw = raw.get("cache")
    if cache_raw is None:
        return None
    if not isinstance(cache_raw, dict):
        raise InventoryError("cache: must be a table")

    cache_dir: str | None = None
    cache_ttl: int | None = None

    for key, val in cache_raw.items():
        if key == "dir":
            if not isinstance(val, str):
                raise InventoryError("cache.dir: must be a string")
            cache_dir = val
        elif key == "ttl":
            if not isinstance(val, int) or val <= 0:
                raise InventoryError("cache.ttl: must be a positive integer")
            cache_ttl = val
        else:
            raise InventoryError(f"cache: unknown key {key!r}")

    return CacheConfig(dir=cache_dir, ttl=cache_ttl)


# ---------------------------------------------------------------------------
# Tool loaders
# ---------------------------------------------------------------------------

def _load_prebuilt_tool(r: _PathReader, path: tuple[str, ...]) -> PrebuiltToolEntry:
    _check_unknown_keys(r.tbl(path), path)
    version = r.str(path + ("version",))
    _validate_prebuilt_version(version, _dot(path) + ".version")
    src = _load_source(r, path)
    upd = _load_update(r, path)
    _check_compat(src.type, upd.provider, _dot(path))
    _check_entry_source_update(src, upd, _dot(path))
    _check_unknown_keys(r.tbl(path + ("source",)), path + ("source",))
    _check_unknown_keys(r.tbl(path + ("update",)), path + ("update",))
    if isinstance(src, GitHubReleaseSource) and src.tag != version:
        raise VersionConfigError(
            f"{_dot(path)}.source.tag: must equal declared version "
            f"({src.tag!r} != {version!r})"
        )
    artifacts = _load_artifacts(r, path, version)
    _validate_required_platforms(upd, artifacts, _dot(path))
    return PrebuiltToolEntry(
        version=version,
        artifacts=MappingProxyType(artifacts),
        source=src, update=upd,
    )


def _load_npm_tool(r: _PathReader, path: tuple[str, ...]) -> NpmToolEntry:
    _check_unknown_keys(r.tbl(path), path)
    version = r.str(path + ("version",))
    _validate_npm_version(version, _dot(path) + ".version")
    src = _load_source(r, path)
    upd = _load_update(r, path)
    _check_compat(src.type, upd.provider, _dot(path))
    _check_entry_source_update(src, upd, _dot(path))
    _check_unknown_keys(r.tbl(path + ("source",)), path + ("source",))
    _check_unknown_keys(r.tbl(path + ("update",)), path + ("update",))
    return NpmToolEntry(version=version, source=src, update=upd)
