"""Update discovery coordinator and suggestion rendering.

No network — delegates all HTTP/git through injected transports.
"""
from __future__ import annotations

import json
from types import MappingProxyType
from typing import (
    Callable,
    Mapping,
    Optional,
    Sequence,
)

from .errors import (
    VersionConfigError,
    ProviderUnavailableError,
)
from .model import (
    ArtifactEntry,
    CandidateArtifact,
    DockerRegistrySource,
    DockerRegistryUpdate,
    GitHubReleaseSource,
    GitHubReleaseUpdate,
    GitSource,
    GitRefUpdate,
    Inventory,
    NodeEntry,
    NpmSource,
    NpmUpdate,
    OhMyZshEntry,
    PiExtensionEntry,
    PrebuiltToolEntry,
    PythonEntry,
    PyPiSource,
    PyPiUpdate,
    RustChannelSource,
    RustChannelUpdate,
    RustEntry,
    TyEntry,
    UvEntry,
    UvPythonSource,
    UvPythonUpdate,
    UpdateCandidate,
    UpdateKind,
    UpdateResult,
    UpdateStatus,
    UpdateTarget,
    OverridePolicy,
)
from .providers.base import (
    ProviderContext,
    ProviderResult,
    UpdateProvider,
)
from .providers.npm import NpmProvider
from .providers.pypi import PyPiProvider
from .providers.github import GitHubReleaseProvider
from .providers.rust import RustChannelProvider
from .providers.docker_registry import DockerRegistryProvider
from .providers.git import GitRefProvider
from .providers.uv_python import UvPythonProvider


# ---------------------------------------------------------------------------
# Default provider registry
# ---------------------------------------------------------------------------

_DEFAULT_PROVIDERS: Mapping[str, UpdateProvider] = MappingProxyType({
    "npm": NpmProvider(),
    "pypi": PyPiProvider(),
    "github-release": GitHubReleaseProvider(),
    "rust-channel": RustChannelProvider(),
    "docker-registry": DockerRegistryProvider(),
    "git-ref": GitRefProvider(),
    "uv-python": UvPythonProvider(),
})


# ---------------------------------------------------------------------------
# Target traversal
# ---------------------------------------------------------------------------

def build_update_targets(
    inventory: Inventory,
) -> tuple[UpdateTarget, ...]:
    """Flatten the inventory into a deterministic ordered tuple of update targets.

    Pi extensions are sorted by TOML key.
    """
    result: list[UpdateTarget] = []

    s = inventory.stages

    # base.node
    node = s.base.node
    result.append(UpdateTarget(
        path="stages.base.node",
        current=node.tag,
        source=node.source,
        update=node.update,
        artifacts={},
    ))

    # toolchain.rust
    result.append(UpdateTarget(
        path="stages.toolchain.rust",
        current=s.toolchain.rust.version,
        source=s.toolchain.rust.source,
        update=s.toolchain.rust.update,
        artifacts={},
    ))

    # toolchain.uv
    result.append(UpdateTarget(
        path="stages.toolchain.uv",
        current=s.toolchain.uv.version,
        source=s.toolchain.uv.source,
        update=s.toolchain.uv.update,
        artifacts=dict(s.toolchain.uv.artifacts),
    ))

    # toolchain.python
    result.append(UpdateTarget(
        path="stages.toolchain.python",
        current=s.toolchain.python.version,
        source=s.toolchain.python.source,
        update=s.toolchain.python.update,
        artifacts={},
        override=s.toolchain.python.override,
    ))

    # toolchain.ty
    result.append(UpdateTarget(
        path="stages.toolchain.ty",
        current=s.toolchain.ty.version,
        source=s.toolchain.ty.source,
        update=s.toolchain.ty.update,
        artifacts={},
    ))

    # rtk-prebuilt
    result.append(UpdateTarget(
        path="stages.rtk-prebuilt.rtk",
        current=s.rtk_prebuilt.rtk.version,
        source=s.rtk_prebuilt.rtk.source,
        update=s.rtk_prebuilt.rtk.update,
        artifacts=dict(s.rtk_prebuilt.rtk.artifacts),
    ))

    # fd-prebuilt
    result.append(UpdateTarget(
        path="stages.fd-prebuilt.fd",
        current=s.fd_prebuilt.fd.version,
        source=s.fd_prebuilt.fd.source,
        update=s.fd_prebuilt.fd.update,
        artifacts=dict(s.fd_prebuilt.fd.artifacts),
    ))

    # pi-tools.pi
    result.append(UpdateTarget(
        path="stages.pi-tools.pi",
        current=s.pi_tools.pi.version,
        source=s.pi_tools.pi.source,
        update=s.pi_tools.pi.update,
        artifacts={},
    ))

    # openspec-tools.openspec
    result.append(UpdateTarget(
        path="stages.openspec-tools.openspec",
        current=s.openspec_tools.openspec.version,
        source=s.openspec_tools.openspec.source,
        update=s.openspec_tools.openspec.update,
        artifacts={},
    ))

    # runtime.oh-my-zsh
    result.append(UpdateTarget(
        path="stages.runtime.oh-my-zsh",
        current=s.runtime.oh_my_zsh.revision,
        source=s.runtime.oh_my_zsh.source,
        update=s.runtime.oh_my_zsh.update,
        artifacts={},
    ))

    # pi-extensions (sorted by key)
    for name in sorted(inventory.runtime_pi_extensions.keys()):
        ext = inventory.runtime_pi_extensions[name]
        result.append(UpdateTarget(
            path=f"runtime.pi-extensions.{name}",
            current=ext.version,
            source=ext.source,
            update=ext.update,
            artifacts={},
        ))

    return tuple(result)


# ---------------------------------------------------------------------------
# Coordination
# ---------------------------------------------------------------------------


def _classify_candidate(
    target: UpdateTarget,
    candidate: UpdateCandidate,
    current_entry_digest: str | None,
) -> tuple[UpdateStatus, UpdateKind, bool, str | None]:
    """Classify an update candidate for a target.

    Returns (status, kind, applicable, reason).
    """
    kind = UpdateKind.VERSION

    # Detect Docker digest refresh
    if isinstance(target.update, DockerRegistryUpdate):
        if target.update.track == "tag-digest":
            kind = UpdateKind.DIGEST_REFRESH
            # If provider returned the same value as current (tag), it's current
            if candidate.value == target.current:
                return (UpdateStatus.CURRENT, kind, False, None)
            # If no stored digest, can't compare
            if current_entry_digest is None:
                return (UpdateStatus.SKIPPED, kind, False, "no stored digest for comparison")
            # If candidate matches stored digest, it's current
            if candidate.value == current_entry_digest:
                return (UpdateStatus.CURRENT, kind, False, None)
            # Different digest → refresh available
            return (UpdateStatus.OUTDATED, kind, True, None)

    # Detect git revision
    if isinstance(target.update, GitRefUpdate):
        kind = UpdateKind.REVISION

    # Current check
    if candidate.value == target.current:
        return (UpdateStatus.CURRENT, kind, False, None)

    # Check override constraint for Python
    if target.override is not None and isinstance(target.source, UvPythonSource):
        from .constraints import parse_numeric_version
        try:
            cand_ver = parse_numeric_version(candidate.value)
        except Exception:
            return (UpdateStatus.INCOMPLETE, kind, False,
                    f"candidate version {candidate.value!r} is not a valid numeric version")

        if not target.override.constraint.matches(cand_ver):
            return (UpdateStatus.INCOMPLETE, kind, False,
                    f"candidate {candidate.value} does not satisfy {target.override.constraint}")

    # Check artifact completeness for GitHub releases
    if isinstance(target.source, GitHubReleaseSource) and isinstance(target.update, GitHubReleaseUpdate):
        required = target.update.required_platforms
        for platform in required:
            art = candidate.artifacts.get(platform) if candidate.artifacts else None
            if art is None:
                return (UpdateStatus.INCOMPLETE, kind, False,
                        f"missing required platform artifact: {platform}")
            if not art.url:
                return (UpdateStatus.INCOMPLETE, kind, False,
                        f"missing URL for platform artifact: {platform}")
            if art.sha256 is None:
                return (UpdateStatus.INCOMPLETE, kind, False,
                        f"missing SHA-256 for platform artifact: {platform}")

    return (UpdateStatus.OUTDATED, kind, True, None)


def check_updates(
    inventory: Inventory,
    *,
    providers: Mapping[str, UpdateProvider] | None = None,
    context: ProviderContext,
    only: tuple[str, ...] = (),
) -> tuple[UpdateResult, ...]:
    """Discover updates for every target in *inventory*.

    Args:
        inventory: Validated inventory.
        providers: Provider registry (defaults to built-in providers).
        context: Transport and policy context.
        only: Optional filter — provider names or inventory paths.
    """
    if providers is None:
        providers = _DEFAULT_PROVIDERS

    targets = build_update_targets(inventory)

    # Apply --only filter
    if only:
        filtered: list[UpdateTarget] = []
        for t in targets:
            for filt in only:
                if filt == t.update.provider or t.path == filt or t.path.startswith(filt):
                    filtered.append(t)
                    break
        targets = tuple(filtered)
        if not targets and only:
            # Gather known paths and provider names for a helpful
            # error message so users can spot typos.
            from .errors import UnknownFilterError
            all_paths = sorted({t.path for t in build_update_targets(inventory)})
            all_providers = sorted(providers.keys())
            raise UnknownFilterError(
                f"--only filter(s) matched nothing: "
                f"{', '.join(repr(f) for f in only)}\n"
                f"  Known paths: {', '.join(all_paths) or '(none)'}\n"
                f"  Known providers: {', '.join(all_providers)}"
            )

    # Resolve current_entry_digest for node
    node_digest = inventory.stages.base.node.digest

    results: list[UpdateResult] = []
    for target in targets:
        provider_name = target.update.provider
        provider = providers.get(provider_name)

        if provider is None:
            results.append(UpdateResult(
                path=target.path,
                provider=provider_name,
                current=target.current,
                candidate=None,
                status=UpdateStatus.SKIPPED,
                kind=UpdateKind.VERSION,
                applicable=False,
                reason=f"no provider for {provider_name!r}",
                artifacts={},
            ))
            continue

        # Call provider
        try:
            prov_result = provider.discover(target, context)
        except Exception as exc:
            results.append(UpdateResult(
                path=target.path,
                provider=provider_name,
                current=target.current,
                candidate=None,
                status=UpdateStatus.UNAVAILABLE,
                kind=UpdateKind.VERSION,
                applicable=False,
                reason=str(exc),
                artifacts={},
            ))
            continue

        if prov_result.unavailable_reason is not None:
            results.append(UpdateResult(
                path=target.path,
                provider=provider_name,
                current=target.current,
                candidate=None,
                status=UpdateStatus.UNAVAILABLE,
                kind=UpdateKind.VERSION,
                applicable=False,
                reason=prov_result.unavailable_reason,
                artifacts={},
            ))
            continue

        if prov_result.skipped_reason is not None:
            results.append(UpdateResult(
                path=target.path,
                provider=provider_name,
                current=target.current,
                candidate=None,
                status=UpdateStatus.SKIPPED,
                kind=UpdateKind.VERSION,
                applicable=False,
                reason=prov_result.skipped_reason,
                artifacts={},
            ))
            continue

        candidate = prov_result.candidate
        if candidate is None:
            results.append(UpdateResult(
                path=target.path,
                provider=provider_name,
                current=target.current,
                candidate=None,
                status=UpdateStatus.UNAVAILABLE,
                kind=UpdateKind.VERSION,
                applicable=False,
                reason="provider returned no candidate",
                artifacts={},
            ))
            continue

        # Classify
        current_entry_digest = node_digest if target.path == "stages.base.node" else None
        status, kind, applicable, reason = _classify_candidate(
            target, candidate, current_entry_digest
        )

        results.append(UpdateResult(
            path=target.path,
            provider=provider_name,
            current=target.current,
            candidate=candidate.value,
            status=status,
            kind=kind,
            applicable=applicable,
            reason=reason,
            artifacts=candidate.artifacts,
            digest=candidate.digest,
        ))

    return tuple(results)


# ---------------------------------------------------------------------------
# Suggestions
# ---------------------------------------------------------------------------

def render_suggestions(
    results: Sequence[UpdateResult],
) -> str:
    """Render a valid TOML fragment with candidate values for all OUTDATED-APPLICABLE results.

    Only entries with ``status == OUTDATED and applicable == True`` are included.
    Values are placed under their owning ``[path]`` table so the output is
    copy-pasteable into ``versions.toml``.
    """
    lines: list[str] = []
    for r in results:
        if r.status != UpdateStatus.OUTDATED or not r.applicable:
            continue
        if r.candidate is None:
            continue

        # Owning table header
        lines.append(f"[{r.path}]")

        # Version / digest / revision
        if r.kind == UpdateKind.VERSION:
            lines.append(f"version = \"{r.candidate}\"")
        elif r.kind == UpdateKind.DIGEST_REFRESH:
            lines.append(f"digest = \"{r.candidate}\"")
        elif r.kind == UpdateKind.REVISION:
            lines.append(f"revision = \"{r.candidate}\"")
        lines.append("")

        # Source tag only for GitHub releases (other providers have no tag field)
        if r.kind == UpdateKind.VERSION and r.provider == "github-release":
            lines.append(f"[{r.path}.source]")
            lines.append(f"tag = \"{r.candidate}\"")
            lines.append("")

        # Artifact updates for prebuilt tools
        if r.artifacts:
            for platform, art in sorted(r.artifacts.items()):
                if art.sha256 is not None:
                    lines.append(f"[{r.path}.artifacts.{platform}]")
                    lines.append(f"url = \"{art.url}\"")
                    lines.append(f"sha256 = \"{art.sha256}\"")
                    lines.append("")

    if not lines:
        return "\n"
    return "\n".join(lines).rstrip("\n") + "\n"


# ---------------------------------------------------------------------------
# Reports
# ---------------------------------------------------------------------------

def render_table(results: Sequence[UpdateResult]) -> str:
    """Render a human-readable ASCII table of update results."""
    header = "PATH  PROVIDER  CURRENT  CANDIDATE  STATUS  KIND  APPLICABLE  DETAIL"
    lines = [header]

    for r in results:
        art_str = str(r.candidate) if r.candidate is not None else "-"
        applicable_str = "yes" if r.applicable else "no"
        detail = r.reason if r.reason else "-"
        line = f"{r.path}  {r.provider}  {r.current}  {art_str}  {r.status.value}  {r.kind.value}  {applicable_str}  {detail}"
        lines.append(line)

    return "\n".join(lines)


def render_json(results: Sequence[UpdateResult]) -> str:
    """Render update results as a canonical JSON array."""
    data = [r.to_dict() for r in results]
    return json.dumps(
        {"results": data},
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )


def render_suggestions_json(
    results: Sequence[UpdateResult],
) -> str:
    """Render JSON with both results and structured suggestions."""
    results_data = [r.to_dict() for r in results]
    suggestions: list[dict[str, object]] = []
    for r in results:
        if r.status != UpdateStatus.OUTDATED or not r.applicable:
            continue
        if r.candidate is None:
            continue
        changes: dict[str, str] = {}
        if r.kind == UpdateKind.VERSION:
            changes["version"] = r.candidate
        elif r.kind == UpdateKind.DIGEST_REFRESH:
            changes["digest"] = r.candidate
        elif r.kind == UpdateKind.REVISION:
            changes["revision"] = r.candidate

        # Source tag only for GitHub releases (other providers have no tag field)
        if r.kind == UpdateKind.VERSION and r.provider == "github-release":
            changes["source.tag"] = r.candidate

        # Artifact changes
        for platform, art in sorted(r.artifacts.items()):
            if art.url:
                changes[f"artifacts.{platform}.url"] = art.url
            if art.sha256:
                changes[f"artifacts.{platform}.sha256"] = art.sha256

        suggestions.append({"path": r.path, "changes": changes})

    return json.dumps(
        {"results": results_data, "suggestions": suggestions},
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
