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
from .model import Inventory, PiExtensionEntry, PythonEntry

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
    "stages.toolchain.python.version": _apply_python_override,
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
    if isinstance(value, _DOMAIN_PRIMITIVES):
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
            # but the canonical TOML path is stages.toolchain.rust.rustup.artifacts.*
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
