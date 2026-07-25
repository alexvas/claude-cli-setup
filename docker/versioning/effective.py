"""Effective configuration: override application and deterministic serialization.

No Docker, no network, no subprocess.
"""
from __future__ import annotations

import dataclasses
import json
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Mapping, Optional

from .constraints import Constraint, ConstraintClause, NumericVersion, parse_numeric_version
from .errors import (
    EffectiveConfigError,
    OverrideValidationError,
    UnknownPathError,
    UnsupportedOverrideError,
    VersionSyntaxError,
)
from .model import (
    BuildInventory,
    EffectiveArtifact,
    EffectiveBuildProjection,
    EffectiveNode,
    EffectiveRust,
    EffectiveTool,
    Inventory,
    PiExtensionEntry,
    PythonEntry,
)

# ---------------------------------------------------------------------------
# Override register
# ---------------------------------------------------------------------------

_OverrideHandler = Any  # callable


def _apply_python_override(
    inventory: Inventory, value: str, path: str
) -> Inventory:
    entry = inventory.stages.toolchain.python
    if entry.override is None:
        raise UnsupportedOverrideError(
            f"{path}: no override policy configured"
        )
    policy = entry.override
    if policy.scheme != "numeric":
        raise UnsupportedOverrideError(
            f"{path}: override scheme is {policy.scheme!r}, expected 'numeric'"
        )

    # Parse
    try:
        candidate = parse_numeric_version(value)
    except VersionSyntaxError as exc:
        raise OverrideValidationError(
            f"{path}: {value!r} is not a valid X.Y.Z numeric version"
        ) from exc

    # Constraint check
    if not policy.constraint.matches(candidate):
        raise OverrideValidationError(
            f"{path}: {candidate} does not satisfy {policy.constraint}"
        )

    new_python = dataclasses.replace(entry, version=str(candidate))
    new_toolchain = dataclasses.replace(
        inventory.stages.toolchain, python=new_python
    )
    new_stages = dataclasses.replace(
        inventory.stages, toolchain=new_toolchain
    )
    return dataclasses.replace(inventory, stages=new_stages)


SUPPORTED_OVERRIDES: Mapping[str, object] = {
    "build.stages.toolchain.python.version": _apply_python_override,
}


# ---------------------------------------------------------------------------
# Effective configuration
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class EffectiveConfiguration:
    """Immutable snapshot after override application."""
    inventory: Inventory
    overrides: Mapping[str, str]


def apply_overrides(
    inventory: Inventory,
    overrides: Mapping[str, str],
) -> EffectiveConfiguration:
    """Apply validated overrides and return the effective configuration."""
    result = inventory
    for path, value in overrides.items():
        handler = SUPPORTED_OVERRIDES.get(path)
        if handler is None:
            raise UnsupportedOverrideError(
                f"{path}: not an overrideable path"
            )
        result = handler(result, value, path)
    return EffectiveConfiguration(
        inventory=result,
        overrides=MappingProxyType(dict(overrides)),
    )


# ---------------------------------------------------------------------------
# Build projection resolver (Stage 4)
# ---------------------------------------------------------------------------

# Override paths supported in build projection resolution
# Supported platform identifiers for build projection resolution
_SUPPORTED_PLATFORMS: set[str] = {"linux-amd64", "linux-arm64"}

# Override paths supported in build projection resolution
_BUILD_OVERRIDE_HANDLERS: Mapping[str, str] = {
    "build.stages.toolchain.python.version": "python",
}


def resolve_build_projection(
    build: BuildInventory,
    overrides: Mapping[str, str],
    *,
    platform: str = "linux-amd64",
) -> EffectiveBuildProjection:
    """Resolve the effective build projection from reviewed build inventory.

    Applies validated overrides and returns a frozen projection containing
    only the fields required for Docker build construction and host-side
    verification.  No runtime extensions, update metadata, override policy,
    or operational state appear in the projection.

    *platform* selects the target architecture.  Must be one of
    ``"linux-amd64"`` or ``"linux-arm64"``.
    """
    if platform not in _SUPPORTED_PLATFORMS:
        raise EffectiveConfigError(
            f"Unsupported platform {platform!r}; "
            f"must be one of {sorted(_SUPPORTED_PLATFORMS)}"
        )
    effective_python = build.stages.toolchain.python.version

    for path, value in overrides.items():
        kind = _BUILD_OVERRIDE_HANDLERS.get(path)
        if kind is None:
            raise UnsupportedOverrideError(
                f"{path}: not an overrideable path"
            )
        if kind == "python":
            effective_python = _resolve_python_override(
                build.stages.toolchain.python, value, path
            )

    # Resolve base node image
    node_entry = build.stages.base.node
    registry = node_entry.source.registry.rstrip("/")
    node_image = f"{registry}/{node_entry.source.repository}:{node_entry.tag}@{node_entry.digest}"

    # Resolve Rust + rustup
    rust = build.stages.toolchain.rust

    def _resolve_artifact(artifacts, p: str, name: str):
        art = artifacts.get(p)
        if art is None:
            raise EffectiveConfigError(
                f"No artifact for platform {p!r} in {name} entry"
            )
        return EffectiveArtifact(url=art.url, sha256=art.sha256)

    uv = build.stages.toolchain.uv
    rtk = build.stages.rtk_prebuilt.rtk
    fd = build.stages.fd_prebuilt.fd

    return EffectiveBuildProjection(
        platform=platform,
        node=EffectiveNode(image=node_image),
        rust=EffectiveRust(
            version=rust.version,
            profile=rust.profile,
            components=tuple(rust.components),
            rustup=_resolve_artifact(rust.rustup, platform, "rustup"),
        ),
        uv=EffectiveTool(
            version=uv.version,
            artifact=_resolve_artifact(uv.artifacts, platform, "uv"),
        ),
        python_version=effective_python,
        ty_version=build.stages.toolchain.ty.version,
        rtk=EffectiveTool(
            version=rtk.version,
            artifact=_resolve_artifact(rtk.artifacts, platform, "rtk"),
        ),
        fd=EffectiveTool(
            version=fd.version,
            artifact=_resolve_artifact(fd.artifacts, platform, "fd"),
        ),
        pi_version=build.stages.pi_tools.pi.version,
        openspec_version=build.stages.openspec_tools.openspec.version,
        oh_my_zsh_revision=build.stages.runtime.oh_my_zsh.revision,
    )


def _resolve_python_override(
    entry: PythonEntry,
    value: str,
    path: str,
) -> str:
    """Validate a Python version override and return the effective version."""
    if entry.override is None:
        raise UnsupportedOverrideError(
            f"{path}: no override policy configured"
        )
    policy = entry.override
    if policy.scheme != "numeric":
        raise UnsupportedOverrideError(
            f"{path}: override scheme is {policy.scheme!r}, expected 'numeric'"
        )

    try:
        candidate = parse_numeric_version(value)
    except VersionSyntaxError as exc:
        raise OverrideValidationError(
            f"{path}: {value!r} is not a valid X.Y.Z numeric version"
        ) from exc

    if not policy.constraint.matches(candidate):
        raise OverrideValidationError(
            f"{path}: {candidate} does not satisfy {policy.constraint}"
        )

    return str(candidate)


# ---------------------------------------------------------------------------
# TOML-name mapping
# ---------------------------------------------------------------------------

_TOML_NAMES: dict[str, str] = {
    "rtk_prebuilt": "rtk-prebuilt",
    "fd_prebuilt": "fd-prebuilt",
    "pi_tools": "pi-tools",
    "openspec_tools": "openspec-tools",
    "oh_my_zsh": "oh-my-zsh",
    "pi_extensions": "pi-extensions",
    "stable_only": "stable_only",
    "allow_prerelease": "allow_prerelease",
    "tag_prefix": "tag_prefix",
    "required_platforms": "required_platforms",
    "linux_amd64": "linux-amd64",
    "linux_arm64": "linux-arm64",
}


def _toml_name(field_name: str) -> str:
    return _TOML_NAMES.get(field_name, field_name)


# ---------------------------------------------------------------------------
# Deterministic serialization
# ---------------------------------------------------------------------------

_NATIVE_JSON = (str, int, float, bool, type(None))
_DOMAIN_PRIMITIVES = (Constraint, ConstraintClause, NumericVersion)
_DOMAIN_PRIMITIVE_NAMES = frozenset({
    "Constraint", "ConstraintClause", "NumericVersion",
})


def _is_domain_primitive(value: object) -> bool:
    """Recognize constraint values across both supported import paths.

    The CLI can load these modules as ``versioning.*`` while package tests use
    ``docker.versioning.*``.  Those paths create distinct class identities in
    one process, so an ``isinstance`` check alone is insufficient.
    """
    value_type = type(value)
    return isinstance(value, _DOMAIN_PRIMITIVES) or (
        value_type.__name__ in _DOMAIN_PRIMITIVE_NAMES
        and value_type.__module__.endswith(".constraints")
    )


def _is_inventory(value: object) -> bool:
    """Check if value is an Inventory without importing the class."""
    return dataclasses.is_dataclass(value) and type(value).__name__ == "Inventory"


def to_plain_data(value: object) -> object:
    """Convert a frozen dataclass graph to JSON-serializable plain data.

    Uses TOML-style names (e.g. ``rtk-prebuilt`` instead of ``rtk_prebuilt``).
    MappingProxyType becomes dict; tuples become lists.
    Domain primitives (Constraint, NumericVersion) become canonical strings.
    """
    if isinstance(value, _NATIVE_JSON):
        return value
    if _is_domain_primitive(value):
        return str(value)
    if isinstance(value, (tuple, list)):
        return [to_plain_data(v) for v in value]
    if isinstance(value, Mapping):
        return {
            _toml_name(str(k)): to_plain_data(v)
            for k, v in value.items()
        }
    if _is_inventory(value):
        # Inventory: nest pi-extensions under runtime, not at top level
        result: dict[str, object] = {}
        for field in dataclasses.fields(value):
            if field.name.startswith("_"):
                continue
            v = getattr(value, field.name)
            if field.name == "runtime_pi_extensions":
                runtime = result.setdefault("runtime", {})
                runtime["pi-extensions"] = to_plain_data(v)
            elif field.name == "stages":
                build = result.setdefault("build", {})
                build["stages"] = to_plain_data(v)
            else:
                result[_toml_name(field.name)] = to_plain_data(v)
        return result
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        result: dict[str, object] = {}
        for field in dataclasses.fields(value):
            if field.name.startswith("_"):
                continue
            v = getattr(value, field.name)
            # Round-trip: RustEntry.rustup is Mapping[str,ArtifactEntry] in the model
            # but the canonical TOML path is build.stages.toolchain.rust.rustup.artifacts.*
            # rustup_source / rustup_update are also sub-keys of rustup
            if field.name == "rustup":
                result[_toml_name(field.name)] = {"artifacts": to_plain_data(v)}
            elif field.name in ("rustup_source", "rustup_update"):
                target_key = "source" if field.name == "rustup_source" else "update"
                result.setdefault("rustup", {})[target_key] = to_plain_data(v)
            else:
                result[_toml_name(field.name)] = to_plain_data(v)
        return result
    return str(value)


def serialize_effective_inventory(
    effective: EffectiveConfiguration,
) -> dict[str, object]:
    """Return canonical plain-data representation of the effective inventory."""
    return to_plain_data(effective.inventory)  # type: ignore[return-value]


def get_path(
    effective: EffectiveConfiguration, path: str
) -> object:
    """Traverse the canonical plain data by dot-separated path.

    Raises UnknownPathError for invalid, empty, or special paths.
    """
    if not path or ".." in path:
        raise UnknownPathError(f"{path}: invalid path")
    if path.startswith("__") or path.endswith("__"):
        raise UnknownPathError(f"{path}: restricted path")

    data = to_plain_data(effective.inventory)

    # Special: root path
    if path == ".":
        return data

    segments = path.split(".")
    current: object = data
    for i, segment in enumerate(segments):
        if not segment:
            raise UnknownPathError(f"{path}: empty segment at position {i}")
        if segment.startswith("__") or segment.endswith("__"):
            raise UnknownPathError(f"{path}: restricted segment {segment!r}")
        if not isinstance(current, Mapping):
            raise UnknownPathError(
                f"{path}: {'.'.join(segments[:i])} is not a mapping"
            )
        if segment not in current:
            raise UnknownPathError(f"{path}: {segment!r} not found")
        current = current[segment]

    return current
