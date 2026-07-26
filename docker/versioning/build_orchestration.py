"""Internal build and doctor orchestration — Stage 9.

This module owns:

* build inputs → effective projection → build vector rendering
* gateway diagnosis → rootless-override planning → persistence
* Docker execution through an injected ``ProcessRunner``
* explicit repair intent (doctor) with consent enforcement

It does **not** own argument parsing, user prompts, generic rendering,
exit-code selection, or terminal inspection — those remain in the facade
(``docker.constructor_cli``).

All side-effecting operations accept injectable fakes so tests require
neither a Docker daemon nor systemd.

**Stage 9.1 RED**: This file defines the immutable DTO contract and
stub orchestration functions.  Every ``orchestrate_*`` returns a
placeholder ``OPERATIONAL`` result so that the test suite can capture
the full expected contract before implementation begins.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from types import MappingProxyType
from typing import Callable, Mapping, Optional, Protocol, Sequence

from docker.networking import (
    GatewayDiagnosis,
    OverrideFailure,
    PersistenceResult,
    ProcessResult,
    ProcessRunner,
    RootlessOverridePlan,
)
from docker.versioning.dispatch_types import CommandResult, ExitKind


# ═══════════════════════════════════════════════════════════════════════
# Injectables
# ═══════════════════════════════════════════════════════════════════════


class BuildExecutor(Protocol):
    """Injected Docker build execution — accepts the exact :func:`render_build_vector`
    tuple (not a list) and returns a :class:`~docker.networking.ProcessResult`.

    Distinct from :class:`~docker.networking.ProcessRunner`, which uses
    ``list[str]`` for gateway / service operations."""

    def run(self, argv: tuple[str, ...]) -> ProcessResult: ...


# ═══════════════════════════════════════════════════════════════════════
# Build orchestration types
# ═══════════════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class BuildRequest:
    """Immutable all inputs for a build transaction.

    Covers task 9.1 item 7: inventory path, overrides, platform, tag,
    context/Dockerfile, target, cache/pull/progress, UID/GID, confirmation,
    dry-run.
    """

    inventory_path: str
    """Path to ``docker-constructor.toml``."""

    platform: str = "linux-amd64"
    """Target platform (``linux-amd64`` or ``linux-arm64``)."""

    tag: str | None = None
    """Optional image-tag override (default: ``pi-cli-pi:latest``)."""

    overrides: Mapping[str, str] = field(
        default_factory=lambda: MappingProxyType({}),
    )
    """Override map for the build projection (PATH=VALUE pairs)."""

    target: str = "runtime"
    """Dockerfile target stage name."""

    context: str | None = None
    """Build context directory (default: parent of inventory)."""

    dockerfile: str | None = None
    """Path to the Dockerfile relative to context.

    ``None`` (default) means Docker resolves ``Dockerfile`` at the
    build-context root — matching the repository layout.
    """

    cache: bool = True
    """Enable Docker build cache."""

    pull: bool = False
    """Force pull base images (``--pull``)."""

    progress: str = "auto"
    """Progress output style: ``auto``, ``plain``, or ``tty``."""

    uid: int | None = None
    """Host user UID injected via ``--build-arg DEV_UID=...``.

    Must be a non-negative integer.  ``None`` means use the default
    from ``BuildRenderInputs`` (usually 1000).
    """

    gid: int | None = None
    """Host user GID injected via ``--build-arg DEV_GID=...``.

    Must be a non-negative integer.  ``None`` means use the default
    from ``BuildRenderInputs`` (usually 1000).
    """

    confirmed: bool = False
    """Facade-obtained confirmation — an immutable boolean decision.

    ``True`` means the user explicitly agreed or ``--yes`` was active.
    Orchestration **never** prompts; it only enforces this flag.

    When ``False`` (and ``dry_run=False``) the transaction must return
    a ``SUCCESS`` cancellation without invoking any side effects
    (diagnosis, persistence, publication, or Docker execution).
    """

    dry_run: bool = False
    """When ``True``, render the build vector but do not invoke Docker."""

    runner: BuildExecutor | None = None
    """Injected build executor; ``None`` means execution impossible."""

    gateway_probe_image: str = "alpine:3.20"
    """Image used for ephemeral gateway probes."""

    repo_root: str | None = None
    """Repository root directory (default: auto-detected from inventory)."""

    # ── injectable networking boundaries (faked in tests) ────────────

    _diagnose_gateway: Callable[..., GatewayDiagnosis] | None = None
    """Injectable ``diagnose_gateway`` — returns ``GatewayDiagnosis``."""

    _persist_gateway: Callable[..., PersistenceResult] | None = None
    """Injectable ``persist_gateway`` — returns ``PersistenceResult``."""

    # ── injectable projection boundary (faked in tests) ──────────────
    _publish_projection: Callable[..., PublishResult] | None = None
    """Injectable projection publication — writes effective build projection.

    Returns a ``PublishResult`` or raises ``PublishError`` on failure.
    """

    def __post_init__(self) -> None:
        """Normalize ``overrides`` to an immutable mapping.

        A frozen dataclass still stores the caller-owned dict; a caller
        holding a reference to the original dict could mutate the request
        after construction.  This normalizes any mutable ``dict`` to a
        ``MappingProxyType``."""
        if not isinstance(self.overrides, MappingProxyType):
            object.__setattr__(self, "overrides", MappingProxyType(
                dict(self.overrides),
            ))


@dataclass(frozen=True)
class PublishResult:
    """Result of projection publication — task 12."""

    published_path: str
    """Canonical host-side path where the effective projection was written."""


@dataclass(frozen=True)
class PublishError(Exception):
    """Publication failure — task 12 (atomic write failure, etc.)."""

    detail: str


@dataclass(frozen=True)
class BuildResult:
    """Outcome of ``orchestrate_build()`` — structural, not rendered."""

    exit_kind: ExitKind
    """Operational exit kind before facade mapping."""

    message: str | None = None
    """Human-readable diagnostic."""

    build_args: tuple[str, ...] = ()
    """Rendered ``docker build`` argument vector (dry-run or pre-execution)."""

    display_string: str | None = None
    """Shell-escaped human-readable display string (distinct from executable tuple)."""

    process_result: ProcessResult | None = None
    """Captured subprocess outcome when execution was performed."""

    host_gateway_ip: str | None = None
    """Persisted ``HOST_GATEWAY_IP`` (``None`` when probe failed)."""


# ═══════════════════════════════════════════════════════════════════════
# Doctor / repair types
# ═══════════════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class DoctorResult:
    """Outcome of ``orchestrate_doctor()`` — structural, not rendered."""

    exit_kind: ExitKind
    """Operational exit kind before facade mapping."""

    message: str | None = None
    """Human-readable diagnostic."""

    initial_diagnosis: GatewayDiagnosis | None = None
    """Raw ``GatewayDiagnosis`` from the first probe run."""

    override_plan: RootlessOverridePlan | None = None
    """Derived ``RootlessOverridePlan`` (``None`` when not applicable)."""

    repair_applied: bool = False
    """``True`` when a rootless override was successfully applied."""

    repair_failure: OverrideFailure | None = None
    """Structured ``OverrideFailure`` when repair could not complete."""

    post_repair_diagnosis: GatewayDiagnosis | None = None
    """``GatewayDiagnosis`` after repair (``None`` when repair not performed)."""

    selected_gateway: str | None = None
    """IP address of the chosen gateway after successful diagnosis."""


@dataclass(frozen=True)
class DoctorRequest:
    """Immutable all inputs for a doctor transaction.

    Mirrors the typed request pattern of ``BuildRequest`` for symmetry.
    """

    apply_override: bool = False
    """Explicit repair intent — only ``True`` when ``--apply-rootless-override``
    is passed.  ``--yes`` alone must **not** imply repair."""

    repair_consent: bool = False
    """User consent for repair obtained by the facade before this call.

    The facade handles all prompting; the orchestration receives an
    immutable boolean.  True means the user explicitly confirmed
    the repair intent.  Ignored when apply_override is False.
    """

    probe_image: str = "alpine:3.20"
    """Docker image used for gateway probe containers."""

    probe_timeout: float | None = None
    """Timeout (seconds) for each gateway probe container."""

    # -- injectables (all default to ``None`` = use real implementations) --

    runner: ProcessRunner | None = None
    """Injected process runner for probe containers / service commands."""

    _diagnose_gateway: Callable[..., GatewayDiagnosis] | None = None
    _plan_rootless_override: Callable[..., RootlessOverridePlan] | None = None
    _apply_rootless_override: Callable[..., OverrideFailure | None] | None = None


# ═══════════════════════════════════════════════════════════════════════
# Stubs (9.1 RED — returns placeholder results, defines the full contract)
# ═══════════════════════════════════════════════════════════════════════


def orchestrate_build(request: BuildRequest) -> BuildResult:
    """STUB — returns a placeholder ``OPERATIONAL`` result.

    This stub exists so that 9.1 RED tests can define the full
    expected contract before the real implementation is written.
    Every test in ``test_constructor_build_orchestration.py`` must
    fail against this stub (except a handful of shape-assertion tests).
    """
    return BuildResult(
        exit_kind=ExitKind.OPERATIONAL,
        message="orchestrate_build not implemented",
    )


def orchestrate_doctor(request: DoctorRequest) -> DoctorResult:
    """STUB — returns a placeholder ``OPERATIONAL`` result."""
    return DoctorResult(
        exit_kind=ExitKind.OPERATIONAL,
        message="orchestrate_doctor not implemented",
    )


def dispatch(
    inventory_path: Path,
    command: str,
    *,
    command_args: Mapping[str, object],
) -> CommandResult:
    """STUB — route build or doctor commands (not yet implemented)."""
    return CommandResult(
        exit_kind=ExitKind.OPERATIONAL,
        message=f"'{command}' orchestration not implemented",
    )
