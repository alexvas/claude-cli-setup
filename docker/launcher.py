"""Project launcher — project selection, pi-N allocation, and
run-vector assembly for ``docker-constructor.py run``.

This module owns:
  - :class:`ProjectSelection` — resolved project paths ready for rendering
  - :func:`resolve_project_selection` — CLI-flag → selection with precedence
  - :func:`allocate_pi_name` — lowest-free pi-N from container inspection
  - :func:`build_run_inputs` — selection → :class:`RunRenderInputs`
  - :class:`RunRequest` / :class:`RunResult` — run-transaction DTOs
  - :func:`orchestrate_run` — the full run transaction

All Docker interaction happens through injected boundaries
(:class:`ContainerNameInspector`, :class:`RunExecutor`).
Filesystem effects — inventory loading and projection-file
creation — are owned by :func:`orchestrate_run` via injected
(:class:`ProjectionFactory`) or path-based boundaries, never
performed ad-hoc by the module.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Protocol, Mapping
from types import MappingProxyType

from docker.versioning.dispatch_types import ExitKind


# ═══════════════════════════════════════════════════════════════════
# Exceptions
# ═══════════════════════════════════════════════════════════════════


class NoMainProjectError(Exception):
    """Raised when no main project can be determined."""


class ContainerInspectError(Exception):
    """Raised when Docker container inspection fails."""


# ═══════════════════════════════════════════════════════════════════
# Value objects
# ═══════════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class ProjectSelection:
    """Resolved project selection ready for launch-vector assembly.

    *main_project* is always a non-empty absolute path.
    *optional_projects* preserves insertion order with no duplicates.
    """

    main_project: str
    optional_projects: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.main_project or not os.path.isabs(self.main_project):
            raise ValueError(
                f"main_project must be a non-empty absolute path, "
                f"got {self.main_project!r}"
            )
        for i, p in enumerate(self.optional_projects):
            if not p or not os.path.isabs(p):
                raise ValueError(
                    f"optional_projects[{i}] must be a non-empty "
                    f"absolute path, got {p!r}"
                )


# ═══════════════════════════════════════════════════════════════════
# Injected boundaries
# ═══════════════════════════════════════════════════════════════════


class ContainerNameInspector(Protocol):
    """Injected Docker container-name inspection boundary.

    Returns an unordered set of existing container names visible
    to ``docker ps -a``.  Raises :class:`ContainerInspectError` when
    Docker is unavailable or output cannot be parsed.
    """

    def list_names(self) -> set[str]:
        ...


class ProjectSelector(Protocol):
    """Injected interactive project-selection boundary (TUI).

    Returns a resolved :class:`ProjectSelection` or ``None`` when
    the user cancels.  The caller owns validation and error mapping.
    """

    def select(self) -> ProjectSelection | None:
        ...


class ProjectionFactory(Protocol):
    """Injectable projection-file creation boundary.

    Receives a resolved effective projection and a parent directory
    and returns a context-manager handle that owns the created file.
    The caller promises to enter and exit the handle.
    """

    def __call__(
        self,
        projection: object,  # EffectiveRuntimeProjection (lazy import)
        *,
        parent_dir: str,
    ) -> object:  # RuntimeProjectionHandle
        ...


# ═══════════════════════════════════════════════════════════════════
# Public API (stubs — to be implemented in 11.4)
# ═══════════════════════════════════════════════════════════════════


def resolve_project_selection(
    *,
    main_project: str | None = None,
    projects: tuple[str, ...] = (),
    tui: bool = False,
    base_project_dir: str | None = None,
    selector: ProjectSelector | None = None,
) -> ProjectSelection:
    """Resolve main and optional projects from CLI flags.

    Precedence:
    1. Explicit *main_project*
    2. TUI selection via *selector* (when *tui* is ``True``)
    3. Documented automatic selection (if retained)
    4. Raise :class:`NoMainProjectError`
    """
    raise NotImplementedError("resolve_project_selection")


def allocate_pi_name(inspector: ContainerNameInspector) -> str:
    """Return the lowest free ``pi-N`` container name.

    Inspects existing containers via *inspector* and returns the
    smallest N ≥ 1 such that ``pi-N`` is not in use.  Allocation is
    best-effort — another process may claim the name before
    ``docker run`` executes.
    """
    raise NotImplementedError("allocate_pi_name")


def build_run_inputs(
    *,
    selection: ProjectSelection,
    image: str,
    container_name: str,
    pi_home_host: str,
    projection_host_path: str,
    projection_container_path: str,
    gateway: str = "host-gateway",
    tty: bool = True,
    stdin_open: bool = True,
    chown_on_start: str | None = None,
):
    """Build :class:`~docker.versioning.rendering.RunRenderInputs`
    from a resolved :class:`ProjectSelection` and runtime parameters.
    """
    raise NotImplementedError("build_run_inputs")


# ═══════════════════════════════════════════════════════════════════
# Run transaction
# ═══════════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class ProcessResult:
    """Captured subprocess outcome — immutable and daemon-independent."""

    argv: tuple[str, ...]
    return_code: int
    stdout: str = ""
    stderr: str = ""


class RunExecutor(Protocol):
    """Injected Docker execution boundary for ``docker run``.

    Accepts a fully rendered argument vector and returns a
    :class:`ProcessResult`.  The executor never modifies the vector
    or prompts the user.
    """

    def run(self, argv: tuple[str, ...]) -> ProcessResult:
        ...


class ProcessRunner:
    """Injectable process-execution boundary.

    Subclass and override ``run`` for in-memory fakes that return
    :class:`ProcessResult` instead of invoking a real subprocess.
    """

    def run(self, argv: list[str]) -> ProcessResult:
        """Execute *argv* and return a structured result."""
        import subprocess
        proc = subprocess.run(
            argv, text=True, capture_output=True, check=False,
        )
        return ProcessResult(
            argv=tuple(argv),
            return_code=proc.returncode,
            stdout=proc.stdout,
            stderr=proc.stderr,
        )


@dataclass(frozen=True)
class RunRequest:
    """Immutable all inputs for a run transaction.

    Covers task 11.2: runtime overrides, private projection creation,
    read-only mount, gateway mapping, TTY modes, dry-run, Docker
    failure, and projection cleanup.
    """

    inventory_path: str
    """Path to ``docker-constructor.toml``."""

    image: str
    """Canonical image to run (e.g. ``pi-cli-pi:latest``)."""

    selection: ProjectSelection
    """Resolved project selection from :func:`resolve_project_selection`."""

    pi_home_host: str
    """Host path to the Pi home directory."""

    gateway: str = "host-gateway"
    """Persisted operational gateway for ``--add-host``
    (resolved IP or ``host-gateway`` raw string)."""

    overrides: Mapping[str, str] = field(
        default_factory=lambda: MappingProxyType({}),
    )
    """Runtime override map (``runtime.pi-extensions.<name>.version=...``)."""

    tty: bool = True
    """Allocate a pseudo-TTY."""

    stdin_open: bool = True
    """Keep STDIN open (``--interactive``)."""

    chown_on_start: str | None = None
    """Value for ``CHOWN_WORK_ON_START`` env var."""

    command: tuple[str, ...] = ()
    """Command to pass through to the container entrypoint."""

    dry_run: bool = False
    """When ``True``, render the vector but do not invoke Docker."""

    executor: RunExecutor | None = None
    """Injected run executor; ``None`` means execution impossible."""

    inspector: ContainerNameInspector | None = None
    """Injected container-name inspector for pi-N allocation."""

    _create_projection: ProjectionFactory | None = None
    """Injected projection-file factory; defaults to
    :func:`~docker.versioning.effective.create_runtime_projection`."""

    projection_parent_dir: str = ".docker-generated/runtime"
    """Parent directory for private runtime projection files."""

    def __post_init__(self) -> None:
        if not isinstance(self.overrides, MappingProxyType):
            object.__setattr__(self, "overrides", MappingProxyType(
                dict(self.overrides),
            ))


@dataclass(frozen=True)
class RunResult:
    """Outcome of :func:`orchestrate_run` — structural, not rendered."""

    exit_kind: ExitKind
    """Operational exit kind before facade mapping."""

    message: str | None = None
    """Human-readable diagnostic."""

    run_args: tuple[str, ...] = ()
    """Rendered ``docker run`` argument vector."""

    display_string: str | None = None
    """Shell-escaped display string for dry-run output."""

    process_result: ProcessResult | None = None
    """Captured subprocess outcome when execution was performed."""

    projection_path: str | None = None
    """Host path to the private runtime projection (for test assertions)."""

    projection_hash: str | None = None
    """SHA-256 content hash of the projection (for identity checks)."""

    container_name: str | None = None
    """Allocated pi-N name (for test assertions)."""


def orchestrate_run(request: RunRequest) -> RunResult:
    """Execute the full run transaction.

    1. Load and validate the reviewed inventory.
    2. Apply runtime overrides → :class:`EffectiveRuntimeProjection`.
    3. If *dry_run*: render the ``docker run`` display string, return —
       no projection file is created and no Docker process is invoked.
    4. Create a private runtime projection file (read-only mount).
    5. Allocate a pi-N container name.
    6. Render the ``docker run`` argument vector.
    7. Execute via *executor*, clean up projection, return result.
    8. On any failure during steps 4–7: clean up projection,
       propagate error.
    """
    raise NotImplementedError("orchestrate_run")


# ═══════════════════════════════════════════════════════════════════
# Docker-backed boundaries
# ═══════════════════════════════════════════════════════════════════


class DockerContainerInspector:
    """Real :class:`ContainerNameInspector` backed by ``docker ps -a``
    through an injectable :class:`ProcessRunner`."""

    def __init__(self, runner: ProcessRunner) -> None:
        self._runner = runner

    def list_names(self) -> set[str]:
        """Run ``docker ps -a --format '{{.Names}}'`` and return the
        set of container names."""
        raise NotImplementedError("DockerContainerInspector.list_names")


class DockerRunExecutor:
    """Real :class:`RunExecutor` backed by ``docker run ...``
    through an injectable :class:`ProcessRunner`."""

    def __init__(self, runner: ProcessRunner) -> None:
        self._runner = runner

    def run(self, argv: tuple[str, ...]) -> ProcessResult:
        """Execute the rendered ``docker`` argument vector."""
        raise NotImplementedError("DockerRunExecutor.run")
