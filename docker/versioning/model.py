"""Frozen dataclass models for the version inventory.

Every versioned entry has a corresponding frozen dataclass with
source/update metadata.  Provider-specific types are separate classes,
not generic dict proxies.

All containers exposed after validation are immutable:
- component/tag lists become tuples
- artifact maps become types.MappingProxyType
- extension maps become types.MappingProxyType
"""
from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Mapping, Optional

from .constraints import Constraint, NumericVersion  # re-export for convenience


# ---------------------------------------------------------------------------
# Override policy
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class OverridePolicy:
    constraint: Constraint
    allow_prerelease: bool
    scheme: str


# ---------------------------------------------------------------------------
# Artifact
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ArtifactEntry:
    url: str
    sha256: str


# ---------------------------------------------------------------------------
# Source metadata (provider-specific)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class GitHubReleaseSource:
    repository: str
    tag: str
    type: str = "github-release"


@dataclass(frozen=True)
class NpmSource:
    package: str
    type: str = "npm"


@dataclass(frozen=True)
class PyPiSource:
    package: str
    type: str = "pypi"


@dataclass(frozen=True)
class UvPythonSource:
    implementation: str  # "cpython" only
    type: str = "uv-python"


@dataclass(frozen=True)
class RustChannelSource:
    manifest: str
    type: str = "rust-channel"


@dataclass(frozen=True)
class DockerRegistrySource:
    registry: str
    repository: str
    type: str = "docker-registry"


@dataclass(frozen=True)
class GitSource:
    repository: str
    type: str = "git"


@dataclass(frozen=True)
class StaticUrlSource:
    """A version-independent source whose integrity is verified via a
    published checksum file (e.g. rustup-init bootstrap binary).

    The ``checksum_url`` points to an authoritative ``sha256sum``-format
    file.  The per-platform artifact URLs and digests live in the parent
    entry's ``artifacts`` table (e.g. ``rustup.artifacts.linux-amd64``).
    """
    checksum_url: str
    type: str = "static-url"


# ---------------------------------------------------------------------------
# Update metadata (provider-specific)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class GitHubReleaseUpdate:
    stable_only: bool
    tag_prefix: str = ""
    required_platforms: tuple[str, ...] = ()
    provider: str = "github-release"


@dataclass(frozen=True)
class NpmUpdate:
    stable_only: bool
    provider: str = "npm"


@dataclass(frozen=True)
class PyPiUpdate:
    stable_only: bool
    provider: str = "pypi"


@dataclass(frozen=True)
class UvPythonUpdate:
    implementation: str  # "cpython" only
    stable_only: bool
    provider: str = "uv-python"


@dataclass(frozen=True)
class RustChannelUpdate:
    channel: str
    stable_only: bool
    provider: str = "rust-channel"


@dataclass(frozen=True)
class DockerRegistryUpdate:
    stable_only: bool
    track: str
    provider: str = "docker-registry"


@dataclass(frozen=True)
class GitRefUpdate:
    ref: str
    provider: str = "git-ref"


@dataclass(frozen=True)
class StaticUrlUpdate:
    """Update contract for version-independent static URLs — the artifact
    is content-addressed (SHA-256), and a provider can detect drift by
    re-downloading and comparing the digest."""
    stable_only: bool = True
    provider: str = "static-url"


# ---------------------------------------------------------------------------
# Entry types
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class NodeEntry:
    tag: str
    digest: str
    source: DockerRegistrySource
    update: DockerRegistryUpdate


@dataclass(frozen=True)
class RustEntry:
    version: str
    profile: str
    components: tuple[str, ...]
    source: RustChannelSource
    update: RustChannelUpdate
    rustup: Mapping[str, ArtifactEntry]
    rustup_source: StaticUrlSource
    rustup_update: StaticUrlUpdate


@dataclass(frozen=True)
class UvEntry:
    version: str
    artifacts: Mapping[str, ArtifactEntry]
    source: GitHubReleaseSource
    update: GitHubReleaseUpdate


@dataclass(frozen=True)
class PythonEntry:
    version: str
    source: UvPythonSource
    update: UvPythonUpdate
    override: Optional[OverridePolicy] = None


@dataclass(frozen=True)
class TyEntry:
    version: str
    source: PyPiSource
    update: PyPiUpdate


@dataclass(frozen=True)
class PrebuiltToolEntry:
    version: str
    artifacts: Mapping[str, ArtifactEntry]
    source: GitHubReleaseSource
    update: GitHubReleaseUpdate


@dataclass(frozen=True)
class NpmToolEntry:
    version: str
    source: NpmSource
    update: NpmUpdate


@dataclass(frozen=True)
class OhMyZshEntry:
    revision: str
    source: GitSource
    update: GitRefUpdate


@dataclass(frozen=True)
class PiExtensionEntry:
    version: str
    source: NpmSource
    update: NpmUpdate


# ---------------------------------------------------------------------------
# Stages
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class BaseStage:
    node: NodeEntry


@dataclass(frozen=True)
class ToolchainStage:
    rust: RustEntry
    uv: UvEntry
    python: PythonEntry
    ty: TyEntry


@dataclass(frozen=True)
class RtkPrebuiltStage:
    rtk: PrebuiltToolEntry


@dataclass(frozen=True)
class FdPrebuiltStage:
    fd: PrebuiltToolEntry


@dataclass(frozen=True)
class PiToolsStage:
    pi: NpmToolEntry


@dataclass(frozen=True)
class OpenSpecToolsStage:
    openspec: NpmToolEntry


@dataclass(frozen=True)
class RuntimeStage:
    oh_my_zsh: OhMyZshEntry


@dataclass(frozen=True)
class Stages:
    base: BaseStage
    toolchain: ToolchainStage
    rtk_prebuilt: RtkPrebuiltStage
    fd_prebuilt: FdPrebuiltStage
    pi_tools: PiToolsStage
    openspec_tools: OpenSpecToolsStage
    runtime: RuntimeStage


@dataclass(frozen=True)
class CacheConfig:
    """Validated ``[cache]`` section from docker-constructor.toml."""
    dir: str | None = None
    """Custom cache directory path."""
    ttl: int | None = None
    """Default TTL in seconds (positive integer)."""


@dataclass(frozen=True)
class Inventory:
    schema: int
    stages: Stages
    runtime_pi_extensions: Mapping[str, PiExtensionEntry]
    cache: CacheConfig | None = None


# ---------------------------------------------------------------------------
# Update discovery types (Stage 3)
# ---------------------------------------------------------------------------

from enum import Enum


class UpdateStatus(str, Enum):
    CURRENT = "current"
    OUTDATED = "outdated"
    SKIPPED = "skipped"
    UNAVAILABLE = "unavailable"
    INCOMPLETE = "incomplete"


class UpdateKind(str, Enum):
    VERSION = "version"
    DIGEST_REFRESH = "digest-refresh"
    REVISION = "revision"


@dataclass(frozen=True)
class CandidateArtifact:
    platform: str
    name: str
    url: str
    sha256: str | None


@dataclass(frozen=True)
class UpdateCandidate:
    value: str
    kind: UpdateKind
    artifacts: Mapping[str, CandidateArtifact]
    digest: str | None = None
    metadata: Mapping[str, str] = ()

    def __post_init__(self):
        object.__setattr__(self, "artifacts", MappingProxyType(dict(self.artifacts)))
        object.__setattr__(self, "metadata", MappingProxyType(dict(self.metadata)))


@dataclass(frozen=True)
class UpdateResult:
    path: str
    provider: str
    current: str
    candidate: str | None
    status: UpdateStatus
    kind: UpdateKind
    applicable: bool
    reason: str | None
    artifacts: Mapping[str, CandidateArtifact]
    digest: str | None = None

    def __post_init__(self):
        object.__setattr__(self, "artifacts", MappingProxyType(dict(self.artifacts)))

    def to_dict(self) -> dict[str, object]:
        """Return a deterministic JSON-serializable dict."""
        import json
        result: dict[str, object] = {
            "applicable": self.applicable,
            "candidate": self.candidate,
            "current": self.current,
            "kind": self.kind.value,
            "path": self.path,
            "provider": self.provider,
            "reason": self.reason,
            "status": self.status.value,
        }
        if self.digest is not None:
            result["digest"] = self.digest
        # artifacts: plain dict of platform → {url, sha256}
        if self.artifacts:
            result["artifacts"] = {
                p: {"url": a.url, "sha256": a.sha256}
                for p, a in sorted(self.artifacts.items())
            }
        return result


@dataclass(frozen=True)
class UpdateTarget:
    """A single entry ready for update discovery."""
    path: str
    current: str
    source: object  # SourceMetadata subclass
    update: object  # UpdateMetadata subclass
    artifacts: Mapping[str, ArtifactEntry]
    override: Optional[OverridePolicy] = None

    def __post_init__(self):
        object.__setattr__(self, "artifacts", MappingProxyType(dict(self.artifacts)))
