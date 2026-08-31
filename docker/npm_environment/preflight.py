"""Side-effect-free assembler input preflight.

``preflight`` performs closed parsing, root and closure validation,
transitive-metadata handling, keyed reviewed-root metadata extraction, and
satisfaction of every declared reviewed-root ``engines.node`` range, then
returns an immutable :class:`ValidatedAssemblyInput`.  It performs no Docker
execution, network access, cache mutation, staging, identity locking, or
publication and exposes no output path or output evidence.
"""

from __future__ import annotations

from typing import Sequence

from docker.versioning.semver import SemverError, validate as _validate_semver

from .errors import LockedNpmError
from .lockfile import parse_lockfile
from .model import RootSpec, ValidatedAssemblyInput
from .semver_range import satisfies


def preflight(
    raw: bytes,
    *,
    roots: Sequence[RootSpec],
    platform: str,
    node_version: str,
    npm_version: str,
) -> ValidatedAssemblyInput:
    """Validate the exact lockfile bytes into a :class:`ValidatedAssemblyInput`.

    *raw* is the exact ``package-lock.json`` bytes; *platform* is an
    ``os-arch`` token; *roots* are the exact root package versions;
    *node_version* and *npm_version* are the caller-owned reviewed exact
    tool versions.  Raises :class:`LockedNpmError` for every contract
    violation, including a reviewed-root ``engines.node`` range that the
    reviewed Node version does not satisfy.
    """
    for label, value in (("node", node_version), ("npm", npm_version)):
        if not isinstance(value, str) or not value:
            raise LockedNpmError(
                "invalid_tool_version",
                f"reviewed {label} version must be an exact non-empty semver, "
                f"got {value!r}",
            )
        try:
            _validate_semver(value)
        except SemverError as exc:
            raise LockedNpmError(
                "invalid_tool_version",
                f"reviewed {label} version {value!r} is not an exact semver",
            ) from exc

    lockfile = parse_lockfile(raw, platform=platform, roots=roots)

    # Only reviewed-root ``engines.node`` declarations are authoritative.
    # Transitive and manifest ranges were syntax-validated and discarded
    # during parsing and never constrain the reviewed Node version.
    for meta in lockfile.root_metadata:
        if meta.engines_node is not None and not satisfies(
            meta.engines_node, node_version
        ):
            raise LockedNpmError(
                "incompatible_node_engine",
                f"reviewed root {meta.package_name!r} at {meta.lock_path!r} "
                f"declares engines.node {meta.engines_node!r}, which is not "
                f"satisfied by reviewed Node {node_version!r}",
            )

    return ValidatedAssemblyInput(
        lockfile_digest=lockfile.source_digest,
        lockfile_bytes=raw,
        platform=platform,
        node_version=node_version,
        npm_version=npm_version,
        roots=lockfile.roots,
        packages=lockfile.packages,
        omitted_optionals=lockfile.omitted_optionals,
        root_metadata=lockfile.root_metadata,
        integrity_less=lockfile.integrity_less,
    )
