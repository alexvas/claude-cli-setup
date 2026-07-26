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

from docker.versioning.dispatch_types import CommandResult, ExitKind


# ═══════════════════════════════════════════════════════════════════════
# Injectables
# ═══════════════════════════════════════════════════════════════════════


class ProcessRunner(Protocol):
    """Injected process execution — testable without Docker/systemd."""

    def run(
        self, cmd: tuple[str, ...], *, timeout: float | None = None
    ) -> ProcessResult: ...


@dataclass(frozen=True)
class ProcessResult:
    """Outcome of a single process execution."""

    returncode: int
    stdout: str
    stderr: str


class ConsentFn(Protocol):
    """Injected consent callback — returns ``True`` when the user approves."""

    def __call__(self, prompt: str) -> bool: ...


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

    confirm: bool = False
    """User consent granted before any mutable side effect.

    Distinguished from ``dry_run``: confirmation controls mutation
    (persistence, publication, Docker execution) while dry-run
    skips execution but may still require consent for publication.
    """

    dry_run: bool = False
    """When ``True``, render the build vector but do not invoke Docker."""

    consent: ConsentFn = lambda _: False
    """Injected consent callback — default denies all prompts.

    The callback is called *after* validation and rendering but
    *before* mutable publication, gateway persistence, and execution.
    """

    runner: ProcessRunner | None = None
    """Injected process runner; ``None`` means execution impossible."""

    gateway_probe_image: str = "alpine:3.20"
    """Image used for ephemeral gateway probes."""

    repo_root: str | None = None
    """Repository root directory (default: auto-detected from inventory)."""

    # ── injectable networking boundaries (faked in tests) ────────────
    _detect_docker_mode: Callable[[], object] | None = None
    """Injectable ``detect_docker_mode`` — returns ``DockerMode``."""

    _diagnose_gateway: Callable[..., object] | None = None
    """Injectable ``diagnose_gateway`` — returns ``GatewayDiagnosis``."""

    _plan_rootless_override: Callable[..., object] | None = None
    """Injectable ``plan_rootless_override`` — returns ``RootlessOverridePlan``."""

    _apply_rootless_override: Callable[..., object | None] | None = None
    """Injectable ``apply_rootless_override`` — returns ``OverrideFailure`` or ``None``."""

    _persist_gateway: Callable[..., object] | None = None
    """Injectable ``persist_gateway`` — returns ``PersistenceResult``."""

    # ── injectable projection boundary (faked in tests) ──────────────
    _publish_projection: Callable[..., object] | None = None
    """Injectable projection publication — writes effective build projection.

    Returns a ``PublishResult`` or raises ``PublishError`` on failure.
    """


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

    gateway_diagnosis: object | None = None
    """Raw ``GatewayDiagnosis`` from networking (or ``None`` on failure)."""

    repair_applied: bool = False
    """``True`` when a rootless override was applied."""


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


def orchestrate_doctor(
    *,
    consent: ConsentFn = lambda _: False,
    probe_image: str = "alpine:3.20",
    apply_override: bool = False,
    runner: ProcessRunner | None = None,
    _detect_docker_mode: Callable[[], object] | None = None,
    _diagnose_gateway: Callable[..., object] | None = None,
    _plan_rootless_override: Callable[..., object] | None = None,
    _apply_rootless_override: Callable[..., object | None] | None = None,
) -> DoctorResult:
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
