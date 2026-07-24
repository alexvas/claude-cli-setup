"""Deterministic build-environment rendering from effective configuration.

Converts an ``EffectiveConfiguration`` into Compose build arguments and
a generated TOML inventory file.  No Docker, no network, no subprocess.
"""
from __future__ import annotations

import os
import tempfile
from pathlib import Path
from types import MappingProxyType
from typing import Mapping, Sequence

from .effective import EffectiveConfiguration, to_plain_data
from .errors import EffectiveConfigError


def render_build_environment(
    effective: EffectiveConfiguration,
    *,
    platform: str = "linux-amd64",
    inventory_output: str = ".docker-generated/docker-constructor.toml",
) -> Mapping[str, str]:
    """Return a deterministic mapping of build-argument names to string values.

    Each key is a Compose ``--build-arg`` name; each value is a plain string
    (never a list or mapping).  The mapping is derived from the immutable
    *effective* configuration and never consults the network or filesystem.
    """
    inv = effective.inventory

    artifacts_uv = inv.stages.toolchain.uv.artifacts.get(platform)
    if artifacts_uv is None:
        raise EffectiveConfigError(
            f"No artifact for platform {platform!r} in uv entry"
        )
    artifacts_rtk = inv.stages.rtk_prebuilt.rtk.artifacts.get(platform)
    if artifacts_rtk is None:
        raise EffectiveConfigError(
            f"No artifact for platform {platform!r} in rtk entry"
        )
    artifacts_fd = inv.stages.fd_prebuilt.fd.artifacts.get(platform)
    if artifacts_fd is None:
        raise EffectiveConfigError(
            f"No artifact for platform {platform!r} in fd entry"
        )

    node = inv.stages.base.node
    registry = node.source.registry.rstrip("/")
    repository = node.source.repository
    node_image = f"{registry}/{repository}:{node.tag}@{node.digest}"

    result: dict[str, str] = {}

    # Base
    result["NODE_BASE_IMAGE"] = node_image

    # Toolchain
    result["RUST_VERSION"] = inv.stages.toolchain.rust.version
    result["RUST_PROFILE"] = inv.stages.toolchain.rust.profile
    result["RUST_COMPONENTS"] = " ".join(inv.stages.toolchain.rust.components)
    # Mandatory rustup bootstrap artifact
    rustup_artifact = inv.stages.toolchain.rust.rustup.get(platform)
    if rustup_artifact is not None:
        result["RUSTUP_URL"] = rustup_artifact.url
        result["RUSTUP_SHA256"] = rustup_artifact.sha256
    result["UV_VERSION"] = inv.stages.toolchain.uv.version
    result["UV_URL"] = artifacts_uv.url
    result["UV_SHA256"] = artifacts_uv.sha256
    result["PYTHON_VERSION"] = inv.stages.toolchain.python.version
    result["TY_VERSION"] = inv.stages.toolchain.ty.version

    # Prebuilt
    result["RTK_VERSION"] = inv.stages.rtk_prebuilt.rtk.version
    result["RTK_URL"] = artifacts_rtk.url
    result["RTK_SHA256"] = artifacts_rtk.sha256
    result["FD_VERSION"] = inv.stages.fd_prebuilt.fd.version
    result["FD_URL"] = artifacts_fd.url
    result["FD_SHA256"] = artifacts_fd.sha256

    # Node tools
    result["PI_VERSION"] = inv.stages.pi_tools.pi.version
    result["OPENSPEC_VERSION"] = inv.stages.openspec_tools.openspec.version

    # Runtime
    result["OH_MY_ZSH_VERSION"] = inv.stages.runtime.oh_my_zsh.revision

    # Pi extensions (deterministic sorted by name)
    for name in sorted(inv.runtime_pi_extensions.keys()):
        ext = inv.runtime_pi_extensions[name]
        prefix = name.upper().replace("-", "_").replace("@", "")
        result[f"{prefix}_VERSION"] = ext.version

    # Effective inventory path
    result["EFFECTIVE_VERSIONS_FILE"] = inventory_output

    return result


def effective_environment(
    effective: EffectiveConfiguration,
    platform: str = "linux-amd64",
) -> Mapping[str, str]:
    """Build a deterministic mapping of environment variable names to values.

    Excludes ``EFFECTIVE_VERSIONS_FILE`` — it is a Compose build-time concern,
    not a shell environment variable.
    """
    env = render_build_environment(effective, platform=platform)
    return MappingProxyType({
        k: v for k, v in env.items()
        if k != "EFFECTIVE_VERSIONS_FILE"
    })


def write_effective_inventory(
    effective: EffectiveConfiguration,
    destination: Path,
    *,
    repo_root: Path | None = None,
    output_path: str | None = None,
) -> None:
    """Write the effective inventory as TOML to *destination*.

    The file is written atomically via a sibling temporary file followed
    by ``os.replace()``.  The parent directory is created if needed.

    When *repo_root* and *output_path* are provided, the path is validated:

    * Must be a relative path inside *repo_root*
    * Must not be the authoritative ``docker-constructor.toml``
    * Must not contain ``..`` traversal or absolute paths
    * Must not resolve to a symlink pointing outside *repo_root*

    The validated *destination* is then ``repo_root / output_path``
    resolved.
    """
    if repo_root is not None and output_path is not None:
        destination = _validate_inventory_output(repo_root, output_path)

    data = to_plain_data(effective.inventory)

    destination.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(
        suffix=".toml",
        prefix=".versions-",
        dir=str(destination.parent),
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            _write_toml(fh, data)
    except Exception:
        os.unlink(tmp_path)
        raise
    os.replace(tmp_path, destination)


def _validate_inventory_output(
    repo_root: Path, relative_path: str
) -> Path:
    """Validate *relative_path* is safe and return the resolved ``Path``.

    Rejects:
    * Absolute paths
    * ``..`` traversal
    * The authoritative ``docker-constructor.toml``
    * Symlink escapes (resolved real path outside repo_root)
    """
    repo_root = repo_root.resolve()

    # Reject absolute paths
    if relative_path.startswith("/") or Path(relative_path).is_absolute():
        raise EffectiveInventoryOutputError(
            f"Effective inventory output must be a relative path, "
            f"not {relative_path!r}"
        )

    # Reject traversal
    if ".." in Path(relative_path).parts:
        raise EffectiveInventoryOutputError(
            f"Effective inventory output must be inside the repo root; "
            f"{relative_path!r} contains '..'"
        )

    # Reject docker-constructor.toml (exact match only, not prefixed)
    norm = Path(relative_path).as_posix()
    if norm in ("docker-constructor.toml", "./docker-constructor.toml"):
        raise EffectiveInventoryOutputError(
            "Effective inventory output cannot be docker-constructor.toml "
            "(the authoritative source)"
        )

    # Resolve and check boundaries + symlinks.
    # Use strict=False for the intermediate resolve so we can detect
    # symlinks at the leaf component separately.
    raw = repo_root / relative_path  # may not exist yet
    # Resolve parent without following symlinks at the leaf
    raw_parent = raw.parent.resolve() if raw.parent != raw else raw.parent

    # Check parent is inside repo_root
    try:
        raw_parent.relative_to(repo_root)
    except ValueError:
        raise EffectiveInventoryOutputError(
            f"Effective inventory output must be inside the repo root; "
            f"{relative_path!r} resolves to {str(raw_parent)!r}"
        )

    # Walk intermediate components for symlink escapes
    for parent in raw_parent.parents:
        if parent == repo_root:
            break
        if parent.is_symlink():
            real_parent = parent.resolve()
            try:
                real_parent.relative_to(repo_root)
            except ValueError:
                raise EffectiveInventoryOutputError(
                    f"Effective inventory output traverses a symlink "
                    f"pointing outside the repo root: {str(parent)!r} "
                    f"-> {str(real_parent)!r}"
                )

    # Reject if the leaf exists and is a symlink outside
    if raw.is_symlink():
        real = raw.resolve()
        try:
            real.relative_to(repo_root)
        except ValueError:
            raise EffectiveInventoryOutputError(
                f"Effective inventory output is a symlink pointing "
                f"outside the repo root: {relative_path!r} "
                f"-> {str(real)!r}"
            )

    resolved = raw.resolve()

    return resolved


class EffectiveInventoryOutputError(ValueError):
    """Raised when the effective inventory output path is invalid."""


def compose_command(args: Sequence[str]) -> tuple[str, ...]:
    """Return the canonical ``docker compose`` argument tuple.

    ``args`` are the user-supplied arguments after ``--``, e.g.
    ``("build", "pi")``.
    """
    return ("docker", "compose", *args)


# ---------------------------------------------------------------------------
# Deterministic TOML serialization
# ---------------------------------------------------------------------------


def _write_toml(fh: object, data: object, *, _prefix: str = "") -> None:
    """Write plain-data *data* as deterministically-ordered TOML.

    Uses dotted-key table headers (``[stages.toolchain.rust]``) for
    sections and inline ``key = value`` for leaves and small tables.
    """
    if isinstance(data, dict):
        _write_dict(fh, data, _prefix)
    elif isinstance(data, list):
        _write_array(fh, data, _prefix)
    elif isinstance(data, str):
        fh.write(f"{_toml_str(data)}\n")
    elif isinstance(data, bool):
        fh.write(f"{'true' if data else 'false'}\n")
    elif isinstance(data, (int, float)):
        fh.write(f"{data}\n")
    elif data is None:
        fh.write("# <absent>\n")
    else:
        fh.write(f"{_toml_str(str(data))}\n")


def _write_dict(fh: object, data: dict, prefix: str) -> None:
    keys = sorted(data.keys(), key=str)
    # Scalars first, then arrays, then nested dicts.
    # TOML requires that bare ``key = value`` lines appear before
    # any ``[header]`` — otherwise they get absorbed into the last table.
    # Arrays (e.g. components = [...]) must also precede nested tables
    # because a plain ``key = [...]`` after a ``[subsection]`` header
    # would be captured into that subsection.
    scalars: list[tuple[str, object]] = []
    nested: list[tuple[str, object]] = []
    arrays: list[tuple[str, object]] = []

    for k in keys:
        v = data[k]
        if isinstance(v, dict):
            if _is_leaf_dict(v):
                scalars.append((k, v))  # inline table counts as scalar
            else:
                nested.append((k, v))
        elif isinstance(v, list):
            arrays.append((k, v))
        else:
            scalars.append((k, v))

    # --- scalars ---
    for k, v in scalars:
        if isinstance(v, dict):
            # Inline table — omit None values (TOML has no null literal)
            parts = []
            for sk in sorted(v.keys(), key=str):
                sv = v[sk]
                if sv is None:
                    continue
                parts.append(f"{sk} = {_toml_value(sv)}")
            if parts:
                fh.write(f"{k} = {{ ")
                fh.write(", ".join(parts))
                fh.write(" }\n")
            # else: empty inline table → omit entirely
        elif isinstance(v, str):
            fh.write(f"{k} = {_toml_str(v)}\n")
        elif isinstance(v, bool):
            fh.write(f"{k} = {'true' if v else 'false'}\n")
        elif isinstance(v, (int, float)):
            fh.write(f"{k} = {v}\n")
        elif v is None:
            fh.write(f"# {k} = <absent>\n")
        else:
            fh.write(f"{k} = {_toml_str(str(v))}\n")

    # --- nested dicts (table headers) ---
    # Emit arrays BEFORE nested tables so that ``components = [...]``
    # lines are not captured into a preceding ``[subsection]``.
    for k, v in arrays:
        full = f"{prefix}.{k}" if prefix else str(k)
        if all(isinstance(i, dict) for i in v):
            for item in v:
                fh.write(f"\n[[{full}]]\n")
                _write_inline_dict(fh, item)
        else:
            fh.write(f"{k} = [")
            fh.write(", ".join(_toml_value(i) for i in v))
            fh.write("]\n")

    # --- nested dicts (table headers) ---
    for k, v in nested:
        full = f"{prefix}.{k}" if prefix else str(k)
        fh.write(f"\n[{full}]\n")
        _write_dict(fh, v, full)


def _is_leaf_dict(d: dict) -> bool:
    """Return True if *d* contains only scalar/string values (no nested dicts/lists)."""
    for v in d.values():
        if isinstance(v, (dict, list)):
            return False
    return True


def _write_inline_dict(fh: object, data: dict) -> None:
    """Write an inline key=value dict for array-of-tables entries."""
    for k in sorted(data.keys(), key=str):
        v = data[k]
        fh.write(f"{k} = {_toml_value(v)}\n")


def _write_array(fh: object, data: list, prefix: str) -> None:
    if not prefix:
        fh.write("[]\n")
        return
    if all(isinstance(i, dict) for i in data):
        for item in data:
            fh.write(f"\n[[{prefix}]]\n")
            _write_inline_dict(fh, item)
    else:
        fh.write(f"{prefix} = [")
        fh.write(", ".join(_toml_value(i) for i in data))
        fh.write("]\n")


def _toml_value(v: object) -> str:
    """Format a scalar value for TOML."""
    if isinstance(v, str):
        return _toml_str(v)
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        return str(v)
    if v is None:
        return '""'
    return _toml_str(str(v))


def _toml_str(s: str) -> str:
    """Quote *s* as a TOML basic string, escaping backslashes and quotes."""
    escaped = s.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'
