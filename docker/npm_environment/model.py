"""Immutable DTOs for the locked npm environment assembler.

All value objects are frozen dataclasses.  Field order is canonical: the
``packages`` tuple is always sorted by lock path and every dependency map is
stored as a lexicographically sorted tuple of ``(name, range)`` pairs so two
semantically identical locks compare equal regardless of JSON key order.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, order=True)
class RootSpec:
    """One exact root package the consumer requires."""

    name: str
    """Exact npm package name, e.g. ``"react"`` or ``"@scope/name"``."""

    version: str
    """Exact, non-moving semver, e.g. ``"18.2.0"``."""


@dataclass(frozen=True)
class OmittedOptional:
    """Explicit evidence for one platform-omitted optional dependency.

    Omission is produced only when the node is present in the lock closure
    and its validated ``os``/``cpu`` constraints are inapplicable to the
    requested platform.  An absent optional node is a ``missing_node`` error,
    never an omission.
    """

    parent_path: str
    """Lock path of the node declaring the optional edge (``""`` for root)."""

    name: str
    """Package name of the omitted optional dependency."""

    range: str
    """The declared range of the omitted optional dependency."""

    reason: str
    """``"platform-inapplicable"`` — locked but excluded by validated os/cpu
    constraints for the requested platform."""

    platform: str
    """The ``os-arch`` platform the omission was evaluated against."""


@dataclass(frozen=True)
class LockPackage:
    """One closed package node from the ``packages`` map."""

    path: str
    """Lock path (``""`` for the root node, ``"node_modules/<name>"``
    otherwise)."""

    name: str
    """Package name, derived from the lock path (root carries its manifest
    name)."""

    version: str
    """Exact resolved version."""

    resolved: str
    """Exact HTTPS registry tarball URL."""

    integrity: str
    """Valid SRI string (``sha512-…`` / ``sha256-…`` / ``sha384-…``), or
    the empty string when the node is an accepted integrity-less registry
    node (see :class:`IntegrityLessNode`)."""

    dependencies: tuple[tuple[str, str], ...]
    """Sorted ``(name, range)`` pairs."""

    optional_dependencies: tuple[tuple[str, str], ...]
    """Sorted ``(name, range)`` pairs."""

    dev_dependencies: tuple[tuple[str, str], ...]
    """Sorted ``(name, range)`` pairs (root only)."""

    peer_dependencies: tuple[tuple[str, str], ...]
    """Sorted ``(name, range)`` pairs."""

    optional_peers: tuple[str, ...]
    """Peer names marked optional via ``peerDependenciesMeta`` (sorted)."""

    dev: bool
    """Node is reachable only through a dev-dependency edge."""

    optional: bool
    """Node is reachable only through optional-dependency edges."""

    peer: bool
    """Node is an auto-installed peer dependency (``peer: true``)."""

    has_install_script: bool
    """Node declares ``hasInstallScript`` (scripts remain disabled)."""

    os: tuple[str, ...] | None
    """``os`` platform list from the lock node, or ``None``."""

    cpu: tuple[str, ...] | None
    """``cpu`` platform list from the lock node, or ``None``."""

    applicable: bool
    """Whether the node is installable on the evaluated platform."""


@dataclass(frozen=True, order=True)
class RootMetadataKey:
    """Canonical key for one reviewed root's preserved metadata.

    Keying by both canonical package identity and resolved lock path means
    metadata from one reviewed root can never overwrite, alias, or stand in
    for another.
    """

    package_name: str
    """Canonical npm package name (e.g. ``"react"``, ``"@scope/name"``)."""

    lock_path: str
    """Exact ``packages`` lock path the root resolved to."""


@dataclass(frozen=True)
class ReviewedRootMetadata:
    """Validated functional metadata preserved for one reviewed root.

    ``bin`` holds sorted ``(command_name, relative_target)`` pairs whose
    targets are validated unambiguous safe relative paths; ``engines_node``
    is the validated ``engines.node`` range or ``None`` when the root
    declares none.  Both are authoritative for this root only and are keyed
    by :class:`RootMetadataKey`.
    """

    package_name: str
    """Canonical npm package name of the reviewed root."""

    lock_path: str
    """Exact ``packages`` lock path the root resolved to."""

    bin: tuple[tuple[str, str], ...]
    """Sorted ``(command_name, relative_target)`` pairs."""

    engines_node: str | None
    """Validated ``engines.node`` range, or ``None`` when undeclared."""

    @property
    def key(self) -> RootMetadataKey:
        """Return the canonical ``(identity, path)`` key for this metadata."""
        return RootMetadataKey(self.package_name, self.lock_path)


@dataclass(frozen=True, order=True)
class IntegrityLessNode:
    """Explicit record of one accepted integrity-less registry node.

    A non-manifest registry package may omit ``integrity`` only when it has
    an exact version and a validated credential-free HTTPS registry
    ``resolved`` URL.  This record marks that omission so no caller can
    mistake the node for a cryptographically byte-pinned entry.
    """

    name: str
    """Canonical package name."""

    path: str
    """Exact ``packages`` lock path."""

    version: str
    """Exact locked version."""

    resolved: str
    """Validated HTTPS registry tarball URL."""


@dataclass(frozen=True)
class ValidatedAssemblyInput:
    """Immutable result of side-effect-free preflight.

    Carries the exact lockfile digest and bytes, canonical roots, platform,
    reviewed tool versions, validated installed closure, optional omissions,
    integrity-less registry-node records, and keyed reviewed-root metadata.

    It performs no Docker, network, cache, staging, lock, or publication
    operation and exposes no output path or output evidence.  The dataclass
    itself is not independently authentic: identity derivation re-runs
    preflight from its bytes and compares the result field-for-field rather
    than trusting the supplied value.
    """

    lockfile_digest: str
    """SHA-256 hex of the exact ``package-lock.json`` bytes."""

    lockfile_bytes: bytes
    """The exact bytes this input was validated from."""

    platform: str
    """The ``os-arch`` platform used for optional applicability."""

    node_version: str
    """Caller-owned reviewed exact Node version."""

    npm_version: str
    """Caller-owned reviewed exact npm version."""

    roots: tuple[RootSpec, ...]
    """Canonical (name-sorted) exact roots."""

    packages: tuple[LockPackage, ...]
    """Validated installed closure, sorted by lock path."""

    omitted_optionals: tuple[OmittedOptional, ...]
    """Explicit platform-inapplicable optional omissions."""

    root_metadata: tuple[ReviewedRootMetadata, ...]
    """Keyed validated ``bin``/``engines.node`` metadata per reviewed root,
    sorted by :class:`RootMetadataKey`."""

    integrity_less: tuple[IntegrityLessNode, ...]
    """Explicit integrity-less registry-node records, sorted by lock path."""


@dataclass(frozen=True)
class LockfileV3:
    """Closed, validated ``package-lock.json`` v3 model."""

    lockfile_version: int
    """Always ``3`` (validated)."""

    source_digest: str
    """SHA-256 hex of the exact lockfile bytes/text this model was parsed
    from.  Used to reject a model parsed from one byte stream being combined
    with the bytes of another."""

    name: str | None
    """Root manifest name, if present."""

    version: str | None
    """Root manifest version, if present."""

    platform: str
    """The ``os-arch`` platform used for optional applicability."""

    roots: tuple[RootSpec, ...]
    """Canonical (name-sorted) exact roots."""

    root: LockPackage
    """The root node (lock path ``""``)."""

    packages: tuple[LockPackage, ...]
    """Reachable, applicable non-root package nodes — the installed closure
    on the evaluated platform — sorted by lock path.  Platform-omitted
    optional nodes and their subtrees are excluded; unrelated lock entries
    are rejected during validation."""

    omitted_optionals: tuple[OmittedOptional, ...]
    """Explicit evidence for each optional node excluded by lock-contained
    os/cpu constraints evaluated against the requested platform."""

    root_metadata: tuple[ReviewedRootMetadata, ...]
    """Validated functional ``bin``/``engines.node`` metadata for every
    reviewed root, keyed by package identity and resolved lock path, sorted
    by :class:`RootMetadataKey`."""

    integrity_less: tuple[IntegrityLessNode, ...]
    """Explicit records of accepted integrity-less registry nodes, sorted
    by lock path."""
