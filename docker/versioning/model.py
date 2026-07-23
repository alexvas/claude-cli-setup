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
class Inventory:
    schema: int
    stages: Stages
    runtime_pi_extensions: Mapping[str, PiExtensionEntry]
