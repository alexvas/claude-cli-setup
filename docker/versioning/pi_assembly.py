"""Host-only Pi release acquisition, assembly, and launcher materialization.

This module wires the reviewed Pi release contract to the standalone locked
npm-environment assembler and the Pi consumer launcher:

1. Derive the exact release-asset URLs from the reviewed release contract.
2. Acquire and checksum-verify the two installation assets (never exposed to
   BuildKit).
3. Run the side-effect-free assembler preflight with the exact lock bytes,
   the exact install-package bytes (bound to the lockfile root), the
   reviewed root, and the caller-owned reviewed Node/npm versions.
4. Select ``bin.pi`` from the keyed reviewed-root metadata.
5. Run Docker-backed assembly with binding rechecks and no launcher creation.
6. Plan the consumer launcher (containment-verified) and its evidence.

Every side effect — download, assembler execution, and cache publication — is
injectable, so tests can drive the full pipeline without a Docker daemon.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from docker.npm_environment import (
    AssemblyResult,
    CorporateNetworkPolicy,
    RootSpec,
    assemble_environment,
    assembler_script_digest,
    build_tree_manifest,
    compute_assembler_identity,
    npm_policy_digest,
    preflight,
)
from docker.versioning.build_materialization import StreamingTransport
from docker.versioning.model import EffectiveBuildProjection, PiReleaseSource
from docker.versioning.pi_consumer import (
    LauncherEvidence,
    LauncherPlan,
    launcher_evidence,
    plan_launcher,
    select_pi_metadata,
)
from docker.versioning.pi_release import (
    PiReleaseError,
    acquire_install_assets,
    derive_pi_release_urls,
    download_bytes,
)

# Versioning uses ``linux-amd64``; the assembler uses npm's ``linux-x64``.
_ASSEMBLER_PLATFORM = "linux-x64"


class PiAssemblyError(RuntimeError):
    """Pi acquisition, preflight, assembly, or launcher failure."""


@dataclass(frozen=True)
class PiAssemblyRequest:
    """Inputs for host Pi materialization."""

    projection: EffectiveBuildProjection
    transport: StreamingTransport
    cache_root: str | Path
    executor: object
    """Injected ``RunExecutor`` for the assembler's Docker run."""
    uid: int | None = None
    gid: int | None = None
    proxy_url: str | None = None
    proxy_no_proxy: str | None = None
    corporate_trust_bundle: str | None = None


@dataclass(frozen=True)
class PiMaterialization:
    """Fully materialized Pi environment and its attestation bindings."""

    result: AssemblyResult
    launcher_plan: LauncherPlan
    launcher_evidence: LauncherEvidence
    output_identity: str
    tree_digest: str
    assembler_evidence_digest: str
    launcher_evidence_digest: str


def _corporate_network(request: PiAssemblyRequest) -> CorporateNetworkPolicy:
    return CorporateNetworkPolicy(
        proxy_url=request.proxy_url,
        proxy_no_proxy=request.proxy_no_proxy,
        corporate_trust_bundle=request.corporate_trust_bundle,
    )


def materialize_pi(request: PiAssemblyRequest) -> PiMaterialization:
    """Acquire, preflight, assemble, and evidence the reviewed Pi environment.

    Performs no BuildKit snapshot exposure of the installation assets and no
    npm/network activity inside BuildKit.  All four attested values are
    computed only after successful host-side assembly and launcher planning.
    """
    projection = request.projection
    release = projection.pi_release
    source = PiReleaseSource(
        package=release.package,
        release_repository=release.release_repository,
        release_tag_prefix=release.release_tag_prefix,
    )

    # 1. Exact release-asset URLs and checksum-verified acquisition.
    urls = derive_pi_release_urls(source, projection.pi_version)
    try:
        package_bytes, lock_bytes = acquire_install_assets(
            urls, lambda url: download_bytes(request.transport, url)
        )
    except PiReleaseError as exc:
        raise PiAssemblyError(f"Pi release acquisition failed: {exc}") from exc

    # 2. Side-effect-free preflight with the exact official lock bytes and
    # the exact official install-package bytes (both are bound assembler
    # inputs — the package manifest is never downloaded-and-discarded).
    roots = (RootSpec(release.package, projection.pi_version),)
    validated = preflight(
        lock_bytes,
        package_bytes=package_bytes,
        roots=roots,
        platform=_ASSEMBLER_PLATFORM,
        node_version=projection.node.node_version,
        npm_version=projection.node.npm_version,
    )

    # 3. Select bin.pi only from the exact reviewed root's keyed metadata.
    metadata = select_pi_metadata(validated, package=release.package)

    # 4. Docker-backed assembly with binding rechecks; creates no launcher.
    assembler = compute_assembler_identity(
        image_digest=projection.node.image,
        node_version=projection.node.node_version,
        npm_version=projection.node.npm_version,
        script_digest=assembler_script_digest(),
        policy_digest=npm_policy_digest(),
        platform=_ASSEMBLER_PLATFORM,
    )
    result = assemble_environment(
        validated=validated,
        assembler=assembler,
        cache_root=request.cache_root,
        executor=request.executor,
        uid=request.uid,
        gid=request.gid,
        corporate_network=_corporate_network(request),
    )

    # 5. Consumer launcher plan + evidence (containment verified).
    launcher_plan = plan_launcher(metadata, environment_root=result.environment_root)
    evidence = launcher_evidence(launcher_plan)

    # 6. Re-verify the published tree against the attested canonical digest
    # before admitting it to the BuildKit snapshot.
    recomputed_tree_digest = build_tree_manifest(result.environment_root).digest
    if recomputed_tree_digest != result.tree_digest:
        raise PiAssemblyError(
            "assembled Pi tree digest does not match the attested value"
        )

    return PiMaterialization(
        result=result,
        launcher_plan=launcher_plan,
        launcher_evidence=evidence,
        output_identity=result.output_identity,
        tree_digest=result.tree_digest,
        assembler_evidence_digest=result.evidence_digest,
        launcher_evidence_digest=evidence.digest,
    )


__all__ = [
    "PiAssemblyError",
    "PiAssemblyRequest",
    "PiMaterialization",
    "materialize_pi",
]
