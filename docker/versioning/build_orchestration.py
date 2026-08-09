"""Internal build and doctor orchestration — Stage 9.

This module owns:

* build inputs → effective projection → build vector rendering
* gateway diagnosis → rootless-override planning → persistence for doctor
* Docker execution through an injected ``ProcessRunner``
* explicit repair intent (doctor) with consent enforcement

It does **not** own argument parsing, user prompts, generic rendering,
exit-code selection, or terminal inspection — those remain in the facade
(``docker.constructor_cli``).

All side-effecting operations accept injectable fakes so tests require
neither a Docker daemon nor systemd.

**Stage 9.3 GREEN**: Real implementations of ``orchestrate_build``
and ``orchestrate_doctor`` with planning/execution separation.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from types import MappingProxyType
from typing import Callable, Mapping, Optional, Protocol, Sequence

from docker.networking import (
    DockerMode,
    GatewayDiagnosis,
    OverrideFailure,
    OverrideState,
    PersistenceResult,
    ProcessResult,
    ProcessRunner,
    RootlessOverridePlan,
    diagnose_gateway,
    persist_gateway,
    plan_rootless_override,
    apply_rootless_override,
)
from docker.versioning.dispatch_types import ExitKind
from docker.versioning.effective import (
    EffectiveBuildProjection,
    resolve_build_projection,
)
from docker.versioning.errors import (
    InventoryError,
    UnsupportedOverrideError,
    VersionConfigError,
)
from docker.versioning.inventory import load_inventory, load_local_config_for_inventory
from docker.versioning.model import HostAccessPolicy, Inventory
from docker.versioning.rendering import (
    BuildRenderInputs,
    CacheControls,
    _docker_platform,
    render_build_vector,
    render_command_display,
    write_effective_build,
)


# ═══════════════════════════════════════════════════════════════════════
# Injectables
# ═══════════════════════════════════════════════════════════════════════


class BuildExecutor(Protocol):
    """Injected Docker build execution — accepts the exact :func:`render_build_vector`
    tuple (not a list) and returns a :class:`~docker.networking.ProcessResult`.

    Distinct from :class:`~docker.networking.ProcessRunner`, which uses
    ``list[str]`` for gateway / service operations."""

    def run(self, argv: tuple[str, ...]) -> ProcessResult: ...


class SubprocessBuildExecutor:
    """Production :class:`BuildExecutor` that delegates to ``subprocess.run``
    with ``shell=False``, capturing stdout and stderr."""

    def run(self, argv: tuple[str, ...]) -> ProcessResult:
        """Execute *argv* via ``subprocess.run``.

        Raises:
            FileNotFoundError: when the ``docker`` binary is missing.
            OSError: on permission or other low-level failures.
        """
        completed = subprocess.run(
            list(argv),
            capture_output=True,
            text=True,
        )
        return ProcessResult(
            argv=argv,
            return_code=completed.returncode,
            stdout=completed.stdout or "",
            stderr=completed.stderr or "",
        )


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
    """Deprecated compatibility field; builds never use gateway probes."""

    _diagnose_gateway: Callable[..., GatewayDiagnosis] | None = None
    """Deprecated compatibility injection; builds never invoke it."""

    _persist_gateway: Callable[..., object] | None = None
    """Deprecated compatibility injection; builds never invoke it."""

    repo_root: str | None = None
    """Repository root directory (default: auto-detected from inventory)."""

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

    publish_result: PublishResult | None = None
    """Publication outcome when projection was written."""


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

    persistence_result: PersistenceResult | None = None
    """Outcome of persisting the selected gateway for future runs."""


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

    probe_timeout: int | None = None
    """Timeout (seconds) for each gateway probe container (1–300)."""

    inventory_path: Path | None = None
    """Resolved inventory path for policy-aware doctor dispatch.

    When ``None`` (legacy or test callers), doctor falls back to the
    unconditional gateway-diagnosis path."""

    # -- injectables (all default to ``None`` = use real implementations) --

    runner: ProcessRunner | None = None
    """Injected process runner for probe containers / service commands."""

    _diagnose_gateway: Callable[..., GatewayDiagnosis] | None = None
    _persist_gateway: Callable[..., PersistenceResult] | None = None
    _plan_rootless_override: Callable[..., RootlessOverridePlan] | None = None
    _apply_rootless_override: Callable[..., OverrideFailure | None] | None = None


# ═══════════════════════════════════════════════════════════════════════
# Internal planning DTO (Stage 9.3)
# ═══════════════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class BuildTransactionPlan:
    """Immutable output of ``plan_build`` — everything needed to
    display or execute a build, computed without side effects."""

    exit_kind: ExitKind
    """``SUCCESS`` when planning completed, ``CONFIG`` on validation failure."""

    message: str | None = None
    """Diagnostic when planning fails."""

    build_args: tuple[str, ...] = ()
    """Rendered ``docker build`` argument vector."""

    display_string: str | None = None
    """Human-readable shell-escaped display string."""

    render_inputs: BuildRenderInputs | None = None
    """Inputs used to produce *build_args* (available for publication)."""

    inventory: Inventory | None = None
    """Loaded inventory (available for effective-projection serialisation)."""

    effective_projection: EffectiveBuildProjection | None = None
    """Resolved build projection (available for publication)."""


# ═══════════════════════════════════════════════════════════════════════
# Plan / execute (Stage 9.3)
# ═══════════════════════════════════════════════════════════════════════


def _publish_projection_default(projection, *, repo_root: Path) -> PublishResult:
    """Default publisher — wraps ``write_effective_build``."""
    try:
        written = write_effective_build(
            projection,
            repo_root=repo_root,
        )
        return PublishResult(published_path=str(written))
    except Exception as exc:
        raise PublishError(detail=str(exc)) from exc


def plan_build(request: BuildRequest) -> BuildTransactionPlan:
    """Load, validate, resolve, and render — no side effects.

    Returns a ``BuildTransactionPlan``.  When validation fails the plan
    carries ``exit_kind=CONFIG`` and a diagnostic message; the caller
    must not proceed to execution.
    """
    # 1. Load inventory (CONFIG on missing / invalid TOML / bad schema)
    inv_path = Path(request.inventory_path)
    try:
        inventory = load_inventory(inv_path)
    except (VersionConfigError, OSError, ValueError, KeyError) as exc:
        return BuildTransactionPlan(
            exit_kind=ExitKind.CONFIG,
            message=str(exc),
        )

    # 2. Resolve effective build projection (validates overrides inline)
    try:
        projection = resolve_build_projection(
            inventory.build,
            request.overrides,
            platform=request.platform,
        )
    except (VersionConfigError, UnsupportedOverrideError, ValueError, KeyError) as exc:
        return BuildTransactionPlan(
            exit_kind=ExitKind.CONFIG,
            message=str(exc),
        )

    # 3. Build render inputs
    build_context = request.context if request.context is not None else str(inv_path.parent.absolute())
    tag = request.tag if request.tag is not None else "pi-cli-pi:latest"

    try:
        docker_platform = _docker_platform(request.platform)
        render_inputs = BuildRenderInputs(
            build_context=build_context,
            projection=projection,
            target_stage=request.target,
            image_tag=tag,
            platform=docker_platform,
            cache=CacheControls(enabled=request.cache),
            pull=request.pull,
            progress=request.progress,
            dockerfile=request.dockerfile,
            dev_uid=request.uid if request.uid is not None else 1000,
            dev_gid=request.gid if request.gid is not None else 1000,
        )

        # 4. Render
        build_args = render_build_vector(render_inputs)
        display_string = render_command_display(build_args)
    except (ValueError, VersionConfigError) as exc:
        return BuildTransactionPlan(
            exit_kind=ExitKind.CONFIG,
            message=str(exc),
        )

    return BuildTransactionPlan(
        exit_kind=ExitKind.SUCCESS,
        build_args=build_args,
        display_string=display_string,
        render_inputs=render_inputs,
        inventory=inventory,
        effective_projection=projection,
    )


def execute_build(
    plan: BuildTransactionPlan,
    request: BuildRequest,
) -> BuildResult:
    """Publish the effective build projection and execute Docker.

    Callers must have already validated ``plan.exit_kind == SUCCESS``
    and confirmed ``request.confirmed is True`` (and that this is not
    a dry-run). Gateway diagnosis belongs to the explicit ``doctor``
    transaction and is intentionally not a build precondition.
    """
    build_args = plan.build_args
    display_string = plan.display_string
    repo_root = (
        Path(request.repo_root) if request.repo_root
        else Path(request.inventory_path).parent
    )

    # 1. Publish effective projection
    publish = request._publish_projection
    try:
        if publish is not None:
            publish_result = publish(
                plan.effective_projection,
                repo_root=repo_root,
            )
        else:
            publish_result = _publish_projection_default(
                plan.effective_projection, repo_root=repo_root,
            )
    except (PublishError, Exception) as exc:
        return BuildResult(
            exit_kind=ExitKind.OPERATIONAL,
            message=f"failed to publish effective projection: {getattr(exc, 'detail', str(exc))}",
            build_args=build_args,
            display_string=display_string,
        )

    # 2. Execute Docker build
    runner = request.runner or SubprocessBuildExecutor()
    try:
        proc = runner.run(build_args)
    except FileNotFoundError as exc:
        return BuildResult(
            exit_kind=ExitKind.OPERATIONAL,
            message=f"docker executable not found: {exc}",
            build_args=build_args,
            display_string=display_string,
            publish_result=publish_result,
        )
    except OSError as exc:
        return BuildResult(
            exit_kind=ExitKind.OPERATIONAL,
            message=f"docker execution failed: {exc}",
            build_args=build_args,
            display_string=display_string,
            publish_result=publish_result,
        )
    exit_kind = ExitKind.SUCCESS if proc.return_code == 0 else ExitKind.OPERATIONAL
    message: str | None = None
    if proc.return_code != 0:
        message = proc.stderr or f"build exited with code {proc.return_code}"

    return BuildResult(
        exit_kind=exit_kind,
        message=message,
        build_args=build_args,
        display_string=display_string,
        process_result=proc,
        publish_result=publish_result,
    )


# ═══════════════════════════════════════════════════════════════════════
# Public orchestration (Stage 9.3)
# ═══════════════════════════════════════════════════════════════════════


def orchestrate_build(request: BuildRequest) -> BuildResult:
    """Orchestrate a complete build transaction.

    Flow:
    1. Plan — load, validate, resolve, render (no side effects)
    2. If plan fails: return CONFIG
    3. If dry-run: return plan with SUCCESS
    4. If not confirmed: return SUCCESS cancellation
    5. Execute — publish and invoke Docker
    """
    plan = plan_build(request)
    if plan.exit_kind != ExitKind.SUCCESS:
        return BuildResult(
            exit_kind=plan.exit_kind,
            message=plan.message,
            build_args=plan.build_args,
            display_string=plan.display_string,
        )

    if request.dry_run:
        return BuildResult(
            exit_kind=ExitKind.SUCCESS,
            build_args=plan.build_args,
            display_string=plan.display_string,
        )

    if not request.confirmed:
        return BuildResult(
            exit_kind=ExitKind.SUCCESS,
            message="build not confirmed",
        )

    return execute_build(plan, request)


def _persist_host_access_address(
    companion_path: Path,
    address: str,
    *,
    _fs: Any = None,
    _tmp_suffix: str | None = None,
) -> PersistenceResult:
    """Atomically write ``[host-access].address`` to the local companion.

    Preserves all other recognised sections (including ``[cache]``),
    comments, and blank lines.  Never adds reviewed-policy fields
    (``enabled``, ``mode``, ``proxy-port``).

    Returns a ``PersistenceResult`` — callers inspect ``.written`` to
    decide whether the operation succeeded.
    """
    import os
    import time

    if _fs is None:
        from docker.networking import Filesystem as _Fs
        _fs = _Fs()

    if not address or not address.strip():
        return PersistenceResult(
            path=companion_path, gateway=address,
            written=False, error="address must be non-empty",
        )

    if _fs.is_symlink(companion_path):
        return PersistenceResult(
            path=companion_path, gateway=address,
            written=False,
            error="local companion must not be a symlink; replace it with a real file",
        )

    unique = (
        _tmp_suffix
        if _tmp_suffix is not None
        else f"{os.getpid()}.{int(time.time() * 1_000_000)}"
    )
    tmp = companion_path.with_name(f"{companion_path.name}.tmp.{unique}")

    # Read-and-update existing content, preserving everything except
    # [host-access].address.
    lines: list[str] = []
    if _fs.is_file(companion_path):
        lines = _fs.read_text(companion_path).splitlines()

    new_lines: list[str] = []
    in_host_access = False
    address_written = False

    for line in lines:
        stripped = line.strip()
        # Detect section headers — tolerate trailing inline comments
        section_name = _parse_toml_section_header(stripped)
        if section_name is not None:
            in_host_access = (section_name == "host-access")
            new_lines.append(line)
            if in_host_access and not address_written:
                new_lines.append(f'address = "{address}"')
                address_written = True
            continue

        # Skip comment lines — must not trigger key detection
        if stripped.startswith("#"):
            new_lines.append(line)
            continue

        if in_host_access and _is_toml_key_line(stripped, "address"):
            # Replace existing address line only when not already written
            if not address_written:
                new_lines.append(f'address = "{address}"')
                address_written = True
            # else: skip duplicate address lines — section header
            # insertion already handled it
            continue

        new_lines.append(line)

    if not address_written:
        new_lines.append("")
        new_lines.append("[host-access]")
        new_lines.append(f'address = "{address}"')

    content = "\n".join(new_lines) + "\n"

    try:
        _fs.write_text(tmp, content)
        _fs.rename(tmp, companion_path)
    except OSError as exc:
        if _fs.is_file(tmp):
            try:
                _fs.delete(tmp)
            except OSError:
                pass
        return PersistenceResult(
            path=companion_path, gateway=address,
            written=False, error=str(exc),
        )
    finally:
        if _fs.is_file(tmp):
            try:
                _fs.delete(tmp)
            except OSError:
                pass

    return PersistenceResult(
        path=companion_path, gateway=address, written=True,
    )


def _is_toml_key_line(stripped: str, key: str) -> bool:
    """True when *stripped* is a TOML assignment to *key*."""
    if "=" not in stripped:
        return False
    left = stripped.split("=", 1)[0].strip()
    return left == key


def _parse_toml_section_header(stripped: str) -> str | None:
    """Return the section name if *stripped* is a TOML section header.

    Handles trailing inline comments: ``[host-access] # comment``.
    Returns ``None`` when *stripped* is not a section header.
    """
    # TOML inline comments start with # outside a string.
    # Section headers have no string values, so splitting on # is safe.
    bare = stripped.split("#", 1)[0].strip()
    if bare.startswith("[") and bare.endswith("]"):
        return bare[1:-1].strip()
    return None


def _resolve_doctor_host_access(
    inventory_path: Path | None,
) -> tuple[str | None, Path | None, str | None]:
    """Resolve the host-access mode and companion path for doctor.

    Returns ``(mode, companion_path, error)``.

    * ``error`` is not ``None`` — the inventory was explicitly supplied
      but is unreadable, malformed, or failed validation.  The caller
      must return a ``CONFIG`` ``DoctorResult`` with the error message.
    * ``mode=None`` — policy is disabled; doctor finishes successfully
      without probing.
    * ``mode="docker-gateway"``, ``companion=None`` — legacy callers
      that do not supply an inventory path; diagnosis runs but the
      result is not persisted locally.
    * ``mode="docker-gateway"``, ``companion=<Path>`` — normal
      docker-gateway flow with atomic local persistence.
    * ``mode="external-address"`` — no probing; user address is used.
    """
    if inventory_path is None:
        # Legacy / test callers without an inventory — fall back to
        # unconditional docker-gateway diagnosis (no local persist).
        return "docker-gateway", None, None
    try:
        inv = load_inventory(inventory_path)
    except Exception as exc:
        return None, None, f"cannot load inventory: {exc}"
    ha = getattr(inv.runtime, "host_access", None)
    if ha is None:
        return None, None, None
    if not isinstance(ha, HostAccessPolicy):
        return None, None, None
    if not ha.enabled:
        return None, None, None
    mode = ha.mode
    if not mode:
        return None, None, None
    from docker.versioning.inventory import resolve_local_companion_path
    companion = resolve_local_companion_path(inventory_path)
    return mode, companion, None


def _persist_selected_gateway(
    gateway: str | None,
    *,
    companion: Path | None = None,
) -> tuple[PersistenceResult | None, str | None]:
    """Persist a verified gateway to the local companion."""
    if gateway is None:
        return None, None
    path = companion
    if path is None:
        return None, None
    try:
        result = _persist_host_access_address(path, gateway)
    except Exception as exc:
        return None, str(exc)
    if not result.written:
        return result, result.error or "unknown error"
    return result, None


def orchestrate_doctor(request: DoctorRequest) -> DoctorResult:
    """Orchestrate a complete doctor (gateway diagnosis + optional repair).

    Flow:
    0. Resolve host-access mode from reviewed inventory.
       - disabled / absent → success, no probing
       - external-address → success, no probing, preserve local address
       - docker-gateway → continue to step 1
    1. Initial diagnosis (only for docker-gateway mode)
    2. Derive override plan (always, even without repair)
    3. If ``apply_override`` and ``repair_consent`` and not rootful:
       a. Skip apply when plan state is MATCHING (already no-op)
       b. Apply override
       c. Re-diagnose on success
    4. If ``apply_override`` but rootful: return POLICY
    5. Otherwise return diagnosis-only result
    """
    # 0. Mode-aware dispatch
    mode, companion, resolve_error = _resolve_doctor_host_access(request.inventory_path)
    if resolve_error is not None:
        return DoctorResult(
            exit_kind=ExitKind.CONFIG,
            message=resolve_error,
        )
    if mode is None:
        return DoctorResult(
            exit_kind=ExitKind.SUCCESS,
            message="Host access is disabled — no gateway diagnosis needed.",
        )
    if mode == "external-address":
        return DoctorResult(
            exit_kind=ExitKind.SUCCESS,
            message="Host access is external-address — no gateway diagnosis needed. "
                    "The locally configured address is used as-is.",
        )
    # docker-gateway mode continues below

    # 1. Initial diagnosis
    diagnose = request._diagnose_gateway or diagnose_gateway
    diagnose_kwargs: dict[str, object] = {}
    if request.probe_image is not None:
        diagnose_kwargs["probe_image"] = request.probe_image
    if request.probe_timeout is not None:
        diagnose_kwargs["probe_timeout"] = request.probe_timeout
    if request.runner is not None:
        diagnose_kwargs["_runner"] = request.runner
    try:
        initial = diagnose(**diagnose_kwargs)
    except Exception as exc:
        return DoctorResult(
            exit_kind=ExitKind.OPERATIONAL,
            message=f"gateway diagnosis failed: {exc}",
        )
    gateway = initial.host_gateway_ip
    initial_persistence, error = _persist_selected_gateway(gateway, companion=companion)
    if error is not None:
        return DoctorResult(
            exit_kind=ExitKind.OPERATIONAL,
            message=f"cannot persist gateway: {error}",
            initial_diagnosis=initial,
            selected_gateway=gateway,
            persistence_result=initial_persistence,
        )

    if gateway is None:
        # Diagnosis-only (no repair intent) → permanently unreachable
        if not request.apply_override:
            detail = "no route"
            if initial.probes:
                first = initial.probes[0]
                if first.detail:
                    detail = first.detail
            return DoctorResult(
                exit_kind=ExitKind.OPERATIONAL,
                message=f"no working gateway IP found: {detail}",
                initial_diagnosis=initial,
                selected_gateway=None,
            )
        # Repair requested and rootless → the override exists precisely
        # to fix this connectivity failure.  Continue through plan/apply.
        if initial.mode != DockerMode.ROOTLESS:
            return DoctorResult(
                exit_kind=ExitKind.OPERATIONAL,
                message="no working gateway IP found and Docker is not rootless",
                initial_diagnosis=initial,
                selected_gateway=None,
            )

    # 2. Derive override plan — always (planning is read-only).
    #    Uses the injected fake when present, otherwise the real
    #    ``plan_rootless_override``.
    plan_fn = request._plan_rootless_override or plan_rootless_override
    try:
        override_plan = plan_fn(_mode=initial.mode)
    except Exception as exc:
        return DoctorResult(
            exit_kind=ExitKind.OPERATIONAL,
            message=f"override planning failed: {exc}",
            initial_diagnosis=initial,
            selected_gateway=gateway,
        )

    # 3. Repair not requested → diagnosis-only success
    if not request.apply_override:
        return DoctorResult(
            exit_kind=ExitKind.SUCCESS,
            initial_diagnosis=initial,
            override_plan=override_plan,
            selected_gateway=gateway,
            persistence_result=initial_persistence,
            repair_applied=False,
        )

    # 4. Repair requested but Docker is rootful → POLICY
    if initial.mode == DockerMode.ROOTFUL:
        return DoctorResult(
            exit_kind=ExitKind.POLICY,
            message="rootless override not applicable: Docker is rootful",
            initial_diagnosis=initial,
            override_plan=override_plan,
            selected_gateway=gateway,
            persistence_result=initial_persistence,
            repair_applied=False,
        )

    # 5. Repair requested — check consent
    if not request.repair_consent:
        return DoctorResult(
            exit_kind=ExitKind.SUCCESS,
            message="repair consent denied",
            initial_diagnosis=initial,
            override_plan=override_plan,
            selected_gateway=gateway,
            persistence_result=initial_persistence,
            repair_applied=False,
        )

    # 6. Already matching — no-op
    #    If the override is already installed but the gateway is still
    #    unreachable, the no-op repair cannot restore connectivity.
    if override_plan is not None and override_plan.state == OverrideState.MATCHING:
        if gateway is None:
            return DoctorResult(
                exit_kind=ExitKind.OPERATIONAL,
                message=(
                    "gateway unreachable and rootless override "
                    "already matching; repair cannot help"
                ),
                initial_diagnosis=initial,
                override_plan=override_plan,
                selected_gateway=None,
                repair_applied=False,
            )
        return DoctorResult(
            exit_kind=ExitKind.SUCCESS,
            initial_diagnosis=initial,
            override_plan=override_plan,
            selected_gateway=gateway,
            persistence_result=initial_persistence,
            repair_applied=False,
        )

    # 7. Apply override
    apply_fn = request._apply_rootless_override or apply_rootless_override
    try:
        failure = apply_fn(plan=override_plan, consent=request.repair_consent)
    except Exception as exc:
        return DoctorResult(
            exit_kind=ExitKind.OPERATIONAL,
            message=f"override application failed: {exc}",
            initial_diagnosis=initial,
            override_plan=override_plan,
            selected_gateway=gateway,
            persistence_result=initial_persistence,
            repair_applied=False,
        )
    if failure is not None:
        return DoctorResult(
            exit_kind=ExitKind.OPERATIONAL,
            message=f"override application failed: {failure.detail}",
            initial_diagnosis=initial,
            override_plan=override_plan,
            repair_failure=failure,
            selected_gateway=gateway,
            persistence_result=initial_persistence,
            repair_applied=False,
        )

    # 8. Re-diagnose after successful repair
    try:
        post = diagnose(**diagnose_kwargs)
    except Exception as exc:
        return DoctorResult(
            exit_kind=ExitKind.OPERATIONAL,
            message=f"post-repair diagnosis failed: {exc}",
            initial_diagnosis=initial,
            override_plan=override_plan,
            selected_gateway=gateway,
            persistence_result=initial_persistence,
            repair_applied=True,
        )

    post_gateway = post.host_gateway_ip
    persistence, error = _persist_selected_gateway(post_gateway, companion=companion)
    if error is not None:
        return DoctorResult(
            exit_kind=ExitKind.OPERATIONAL,
            message=f"cannot persist gateway: {error}",
            initial_diagnosis=initial,
            override_plan=override_plan,
            post_repair_diagnosis=post,
            selected_gateway=post_gateway,
            persistence_result=persistence,
            repair_applied=True,
        )
    return DoctorResult(
        exit_kind=ExitKind.SUCCESS if post_gateway else ExitKind.OPERATIONAL,
        message=None if post_gateway else "gateway unreachable after repair",
        initial_diagnosis=initial,
        override_plan=override_plan,
        post_repair_diagnosis=post,
        selected_gateway=post_gateway,
        persistence_result=persistence,
        repair_applied=True,
    )


# ═══════════════════════════════════════════════════════════════════════
# Public doctor API (Stage 9.4)
# ═══════════════════════════════════════════════════════════════════════


def diagnose_doctor(
    *,
    probe_image: str | None = None,
    probe_timeout: int | None = None,
    _diagnose_gateway: Callable[..., GatewayDiagnosis] | None = None,
    _plan_rootless_override: Callable[..., RootlessOverridePlan] | None = None,
) -> DoctorResult:
    """Run gateway diagnosis without repair — always read-only.

    Returns a ``DoctorResult`` with the initial diagnosis and override
    plan, but ``repair_applied`` is always ``False``.
    """
    request = DoctorRequest(
        apply_override=False,
        repair_consent=False,
        probe_image=probe_image,
        probe_timeout=probe_timeout,
        _diagnose_gateway=_diagnose_gateway,
        _plan_rootless_override=_plan_rootless_override,
    )
    return orchestrate_doctor(request)


def repair_rootless(
    *,
    consent: bool,
    probe_image: str | None = None,
    probe_timeout: int | None = None,
    _diagnose_gateway: Callable[..., GatewayDiagnosis] | None = None,
    _plan_rootless_override: Callable[..., RootlessOverridePlan] | None = None,
    _apply_rootless_override: Callable[..., OverrideFailure | None] | None = None,
) -> DoctorResult:
    """Diagnose gateway and apply rootless override when applicable.

    *consent* must be ``True`` for the override to be applied.
    When Docker is rootful, returns ``POLICY``.
    """
    request = DoctorRequest(
        apply_override=True,
        repair_consent=consent,
        probe_image=probe_image,
        probe_timeout=probe_timeout,
        _diagnose_gateway=_diagnose_gateway,
        _plan_rootless_override=_plan_rootless_override,
        _apply_rootless_override=_apply_rootless_override,
    )
    return orchestrate_doctor(request)
