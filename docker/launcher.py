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

import enum
import hashlib
import json
import os
from dataclasses import dataclass, field
from typing import Protocol, Mapping

import docker.versioning.artifact_cache as artifact_cache
from docker.versioning.dispatch_types import ExitKind
from docker.versioning.model import _derive_artifact_id
from docker.versioning.rendering import (
    RunRenderInputs,
    plan_artifact_mounts,
    plan_dry_run_artifact_mounts,
)
from types import MappingProxyType


class ExecutionMode(enum.Enum):
    """Explicit mode for the Docker process boundary.

    ``CAPTURED`` — stdout/stderr are captured for diagnostics;
    no ``--tty``/``--interactive`` flags are passed to Docker.

    ``INTERACTIVE`` — stdin/stdout/stderr inherit the host
    terminal.  The mode controls stream inheritance; it does
    **not** guarantee which Docker flags (``--tty``,
    ``--interactive``) appear — those are chosen separately
    based on ``tty`` and ``stdin_open``."""
    CAPTURED = "captured"
    INTERACTIVE = "interactive"


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
    resolved_main: str | None = None
    resolved_optional: tuple[str, ...] = ()

    if main_project is not None:
        # Explicit main wins; optionals come from CLI
        resolved_main = main_project
        resolved_optional = tuple(projects)
    elif tui and selector is not None:
        # Unwrapped paragraph
        sel = selector.select()
        if sel is None:
            raise NoMainProjectError(
                "No main project selected (TUI cancelled)"
            )
        resolved_main = sel.main_project
        resolved_optional = sel.optional_projects
    else:
        raise NoMainProjectError(
            "No main project specified.  Use --main-project / -m "
            "to select a project directory, or --tui to choose "
            "interactively."
        )

    # Normalise and validate
    resolved_main = os.path.normpath(resolved_main)
    norm_optional = tuple(os.path.normpath(p) for p in resolved_optional)

    # Duplicate detection
    seen: set[str] = {resolved_main}
    deduped: list[str] = []
    for p in norm_optional:
        if p in seen:
            raise ValueError(
                f"Duplicate project path after normalisation: {p!r}"
            )
        seen.add(p)
        deduped.append(p)

    return ProjectSelection(
        main_project=resolved_main,
        optional_projects=tuple(deduped),
    )


def allocate_pi_name(inspector: ContainerNameInspector) -> str:
    """Return the lowest free ``pi-N`` container name.

    Inspects existing containers via *inspector* and returns the
    smallest N ≥ 1 such that ``pi-N`` is not in use.  Allocation is
    best-effort — another process may claim the name before
    ``docker run`` executes.
    """
    try:
        names = inspector.list_names()
    except Exception:
        raise

    # Parse pi-N numbers from existing names
    taken: set[int] = set()
    for name in names:
        if not name.startswith("pi-"):
            continue
        suffix = name[3:]
        # Must be a positive integer with no leading zeros
        # (pi-01 reserves pi-1 because int("01") == 1)
        if not suffix:
            continue
        try:
            n = int(suffix)
        except ValueError:
            continue
        if n >= 1:
            taken.add(n)

    if not taken:
        return "pi-1"

    # Find the lowest gap (or next after max)
    max_taken = max(taken)
    for n in range(1, max_taken + 2):
        if n not in taken:
            return f"pi-{n}"

    # Should never reach here — fallback safe
    return f"pi-{max_taken + 1}"


def build_run_inputs(
    *,
    selection: ProjectSelection,
    image: str,
    container_name: str,
    pi_home_host: str,
    projection_host_path: str,
    projection_container_path: str,
    tty: bool = True,
    stdin_open: bool = True,
    chown_on_start: str | None = None,
) -> RunRenderInputs:
    """Build :class:`~docker.versioning.rendering.RunRenderInputs`
    from a resolved :class:`ProjectSelection` and runtime parameters.

    Host-access inputs are always disabled — callers that need host
    access must construct ``RunRenderInputs`` with an explicit
    ``host_access`` argument.
    """
    return RunRenderInputs(
        image=image,
        container_name=container_name,
        pi_home_host=pi_home_host,
        projection_host_path=projection_host_path,
        projection_container_path=projection_container_path,
        main_project=selection.main_project,
        optional_projects=selection.optional_projects,
        tty=tty,
        stdin_open=stdin_open,
        chown_on_start=chown_on_start,
    )


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

    def run(self, argv: tuple[str, ...], *,
            interactive: bool = False) -> ProcessResult:
        ...


class ArtifactByteFetcher(Protocol):
    """Injected byte-fetch boundary for runtime artifact
    downloads.

    Called once per selected artifact cache-miss.  Returns the
    raw bytes from the reviewed URL.  Test doubles return
    controlled bytes so digest-mismatch and network-error
    paths are deterministic."""

    def __call__(self, url: str) -> bytes: ...


class ProcessRunner:
    """Injectable process-execution boundary.

    Subclass and override ``run`` for in-memory fakes that return
    :class:`ProcessResult` instead of invoking a real subprocess.
    """

    def run(self, argv: list[str], *,
            mode: ExecutionMode = ExecutionMode.CAPTURED) -> ProcessResult:
        """Execute *argv* and return a structured result.

        ``mode`` controls whether stdout/stderr are captured or
        the host terminal is inherited."""
        import subprocess
        if mode is ExecutionMode.CAPTURED:
            proc = subprocess.run(
                argv, text=True, capture_output=True, check=False,
            )
        else:
            proc = subprocess.run(
                argv, text=True, capture_output=False,
                stdin=None, stdout=None, stderr=None, check=False,
            )
        return ProcessResult(
            argv=tuple(argv),
            return_code=proc.returncode,
            stdout=proc.stdout or "",
            stderr=proc.stderr or "",
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

    repo_root: str | None = None
    """Repository root for the fixed corporate trust bundle.

    Mandatory whenever corporate trust is enabled.  It is never inferred
    from the inventory path; a direct caller that enables corporate trust
    without supplying it fails closed with a CONFIG error before Docker.
    """

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

    projection_parent_dir: str = field(default_factory=lambda: os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        ".docker-generated",
        "runtime",
    ))
    """Absolute parent directory for private runtime projection files.

    The default is anchored to the constructor checkout rather than the
    caller's current working directory because Docker bind-mount sources and
    runtime projection validation require an absolute host path.
    """

    _artifact_fetcher: ArtifactByteFetcher | None = None
    """Injected byte-fetch boundary for deterministic
    materialization tests.  ``None`` selects the real
    download transport; a test double returns controlled
    bytes so digest-mismatch paths are network-independent."""

    _artifact_cache_root: str | None = None
    """Test-only resolved runtime-artifact cache injection seam."""

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

    artifact_cache_hits: tuple[str, ...] = ()
    """Artifact IDs already present and valid in the cache (dry-run only)."""

    artifact_cache_misses: tuple[str, ...] = ()
    """Artifact IDs not yet materialized in the cache (dry-run only)."""


def _resolve_host_access(
    policy: object | None,
    inventory_path: Path,
) -> "RunHostAccess | None":
    """Resolve host-access rendering inputs from reviewed policy
    and the local companion.

    Returns ``None`` when the policy is enabled but the local
    companion is missing or its ``[host-access].address`` is absent.
    The caller must translate ``None`` into a config-failure
    ``RunResult``.

    Raises ``InventoryError`` (from ``load_local_config_for_inventory``)
    when the companion exists but is malformed, contains unknown keys,
    or holds an invalid address — carrying the path-specific Phase 1
    diagnostic.
    """
    from docker.versioning.inventory import load_local_config_for_inventory
    from docker.versioning.rendering import RunHostAccess

    if policy is None:
        return RunHostAccess.disabled()
    enabled = getattr(policy, "enabled", False)
    if not enabled:
        return RunHostAccess.disabled()

    mode = getattr(policy, "mode", None)
    proxy_port = getattr(policy, "proxy_port", None)
    if not mode:
        return RunHostAccess.disabled()

    try:
        local = load_local_config_for_inventory(inventory_path)
    except FileNotFoundError:
        return None

    if local is None:
        return None

    addr = getattr(local.host_access, "address", None) if local.host_access else None
    if not addr or not isinstance(addr, str):
        return None

    try:
        return RunHostAccess(address=addr, mode=mode, proxy_port=proxy_port)
    except ValueError:
        return None


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
    import shlex
    from pathlib import Path

    from docker.versioning.effective import (
        create_runtime_projection,
        resolve_runtime,
    )
    from docker.versioning.errors import (
        EffectiveConfigError,
        OverrideValidationError,
        UnsupportedOverrideError,
    )
    from docker.versioning.inventory import (
        InventoryError,
        load_inventory,
        resolve_corporate_trust_bundle_path,
        resolve_local_corporate_settings,
    )
    from docker.versioning.rendering import RunHostAccess, render_run_vector

    # ── Step 1: load inventory ──────────────────────────────
    try:
        inventory = load_inventory(Path(request.inventory_path))
    except Exception as exc:
        return RunResult(
            exit_kind=ExitKind.CONFIG,
            message=f"Failed to load inventory: {exc}",
        )

    # ── Step 1b: validate local corporate settings ──────────
    host_access_policy = getattr(inventory.runtime, "host_access", None)
    host_access_mode = (
        getattr(host_access_policy, "mode", None)
        if getattr(host_access_policy, "enabled", False)
        else None
    )
    try:
        local_corporate = resolve_local_corporate_settings(
            Path(request.inventory_path),
            repository_root=(
                Path(request.repo_root) if request.repo_root else None
            ),
            host_access_mode=host_access_mode,
        )
    except InventoryError as exc:
        return RunResult(
            exit_kind=ExitKind.CONFIG,
            message=str(exc),
        )

    # Corporate trust bundle host path — resolved only on the enabled path
    # (the fixed repository-local bundle was already validated above).
    corporate_trust_bundle: str | None = None
    if local_corporate.corporate_trust.enabled and request.repo_root:
        corporate_trust_bundle = os.path.abspath(
            resolve_corporate_trust_bundle_path(Path(request.repo_root))
        )
    proxy_url = local_corporate.network_proxy.url
    proxy_no_proxy = local_corporate.network_proxy.no_proxy

    # All persistent runtime-artifact state lives beneath the shared,
    # secured constructor cache root; checkout-local generated output is
    # reserved for projections and evidence.
    from docker.versioning.cache_storage import (
        prepare_default_root, prepare_local_root,
        runtime_artifacts_blobs_child, runtime_artifacts_locks_child,
        runtime_artifacts_tmp_child,
    )
    xdg_cache_home = os.environ.get("XDG_CACHE_HOME")
    cache_home = Path(os.path.expanduser("~"))
    local_cache_dir = getattr(
        getattr(local_corporate, "cache", None), "dir", None,
    )
    try:
        if request._artifact_cache_root is None:
            prepared_cache_root = (
                prepare_local_root(
                    local_cache_dir,
                    xdg_cache_home=xdg_cache_home,
                    home=cache_home,
                )
                if local_cache_dir is not None
                else prepare_default_root(xdg_cache_home, home=cache_home)
            )
            runtime_cache_root = str(
                runtime_artifacts_blobs_child(prepared_cache_root)
            )
            runtime_locks_root = str(
                runtime_artifacts_locks_child(prepared_cache_root)
            )
            runtime_tmp_root = str(
                runtime_artifacts_tmp_child(prepared_cache_root)
            )
        else:
            runtime_cache_root = request._artifact_cache_root
            runtime_locks_root = str(
                runtime_artifacts_locks_child(
                    Path(runtime_cache_root).parent.parent
                )
            )
            runtime_tmp_root = str(
                runtime_artifacts_tmp_child(
                    Path(runtime_cache_root).parent.parent
                )
            )
    except Exception as exc:
        return RunResult(
            exit_kind=ExitKind.CONFIG,
            message=f"Failed to prepare runtime artifact cache: {exc}",
        )

    # ── Step 1c: resolve host-access policy ─────────────────
    try:
        host_access = _resolve_host_access(
            getattr(inventory.runtime, "host_access", None),
            Path(request.inventory_path),
        )
    except InventoryError as exc:
        return RunResult(
            exit_kind=ExitKind.CONFIG,
            message=str(exc),
        )
    if host_access is None:
        return RunResult(
            exit_kind=ExitKind.CONFIG,
            message="Host access is enabled but the local companion "
                    "is missing or has no [host-access] address. "
                    "Run 'doctor' first or set [host-access].address "
                    "in the local companion.",
        )

    # ── Step 2: apply overrides ──────────────────────────────
    try:
        selected_artifacts, effective = resolve_runtime(
            inventory.runtime,
            request.overrides,
        )
    except (
        UnsupportedOverrideError,
        OverrideValidationError,
        EffectiveConfigError,
        ValueError,
    ) as exc:
        return RunResult(
            exit_kind=ExitKind.CONFIG,
            message=str(exc),
        )

    # ── Step 3: dry-run ─────────────────────────────────────
    if request.dry_run:
        import dataclasses

        try:
            # Compute projection hash from the resolved effective
            # projection for display/identity purposes.
            proj_raw: dict[str, object] = {
                "extensions": {
                    name: dataclasses.asdict(entry)
                    for name, entry in effective.extensions.items()
                }
            }
            projection_hash = hashlib.sha256(
                json.dumps(
                    proj_raw, sort_keys=True, default=str,
                ).encode("utf-8")
            ).hexdigest()
            # Plan artifact mounts from the resolved selection without
            # materialization — host paths are deterministic cache
            # locations, container targets are fixed beneath the
            # runtime-artifacts root.
            dry_run_mounts = plan_dry_run_artifact_mounts(
                selected_artifacts, cache_root=runtime_cache_root,
            )
            # Inspect the cache read-only — verify each unique
            # blob's bytes against its declared SRI integrity
            # using the no-follow, descriptor-relative inspection
            # API.  Corrupt, missing, symlinked, or non-regular
            # entries are reported as planned misses.
            seen: set[str] = set()
            hits: list[str] = []
            misses: list[str] = []
            for art in selected_artifacts:
                if art.integrity in seen:
                    continue
                seen.add(art.integrity)
                artifact_id = _derive_artifact_id(art.integrity)
                if artifact_cache.inspect_verified_blob_readonly(
                    art.integrity,
                    cache_root=runtime_cache_root,
                ):
                    hits.append(artifact_id)
                else:
                    misses.append(artifact_id)
            # Render a dummy projection for display purposes only.
            # No file is ever created.
            projection_container_path = (
                "/run/pi-cli/docker-constructor.runtime.toml"
            )
            render_inputs = RunRenderInputs(
                image=request.image,
                container_name="pi-N",
                pi_home_host=request.pi_home_host,
                projection_host_path=(
                    "/tmp/.docker-generated/runtime/projection.toml"
                ),
                projection_container_path=projection_container_path,
                main_project=request.selection.main_project,
                optional_projects=request.selection.optional_projects,
                host_access=host_access,
                tty=request.tty,
                stdin_open=request.stdin_open,
                command=request.command,
                chown_on_start=request.chown_on_start,
                artifact_mounts=dry_run_mounts,
                validate_artifact_sources=False,
                corporate_trust_bundle=corporate_trust_bundle,
                proxy_url=proxy_url,
                proxy_no_proxy=proxy_no_proxy,
            )
            run_args = render_run_vector(render_inputs)
            display = shlex.join(run_args)
        except Exception as exc:
            return RunResult(
                exit_kind=ExitKind.CONFIG,
                message=f"Dry-run render failed: {exc}",
            )
        return RunResult(
            exit_kind=ExitKind.SUCCESS,
            run_args=run_args,
            display_string=display,
            projection_hash=projection_hash,
            artifact_cache_hits=tuple(hits),
            artifact_cache_misses=tuple(misses),
        )

    # ── Step 3b: materialize unique selected artifacts ─────
    # selected_artifacts from resolve_runtime already deduplicates by
    # integrity.  Each entry in the projection retains its independent
    # package/version/metadata identity.

    try:
        class _InjectedTransport:
            def fetch_chunks(self, url: str):
                assert request._artifact_fetcher is not None
                data = request._artifact_fetcher(url)
                if not isinstance(data, bytes):
                    raise TypeError("artifact fetcher must return bytes")
                yield data

        transport = (_InjectedTransport() if request._artifact_fetcher
                     else artifact_cache.HttpStreamingTransport())
        if request._artifact_cache_root is not None:
            os.makedirs(runtime_tmp_root, mode=0o700, exist_ok=True)
        configured_root = os.path.abspath(runtime_cache_root)
        if os.path.islink(configured_root):
            raise artifact_cache.ArtifactMaterializationError(
                "containment", "runtime artifact cache root is a symlink",
            )
        root = os.path.realpath(configured_root)
        blobs = artifact_cache.materialize_selected_artifacts(
            selected_artifacts,
            transport=transport,
            filesystem=artifact_cache.LocalCacheFilesystem(),
            lock_factory=artifact_cache.FileIdentityLockFactory(
                root, lock_root=runtime_locks_root,
            ),
            temp_dir=artifact_cache.LocalTemporaryDirectory(),
            temp_root=runtime_tmp_root,
            cache_root=root,
        )
        artifact_mounts = plan_artifact_mounts(blobs.values())
    except Exception as exc:
        return RunResult(
            exit_kind=ExitKind.OPERATIONAL,
            message=f"Failed to materialize runtime artifacts: {exc}",
        )

    # ── boundary validation ────────────────────────────────
    if request.executor is None:
        return RunResult(
            exit_kind=ExitKind.OPERATIONAL,
            message="No executor configured",
        )
    if request.inspector is None:
        return RunResult(
            exit_kind=ExitKind.OPERATIONAL,
            message="No container inspector configured",
        )

    # ── Step 4: create projection ───────────────────────────
    factory = request._create_projection
    if factory is None:
        # The real factory generates its own unique non-existent
        # path inside the repo's .docker-generated/runtime/.
        # Do NOT pre-create a file — create_runtime_projection
        # uses atomic hard-link promotion with no-clobber
        # semantics.
        def _real_factory(projection: object, *, parent_dir: str) -> object:
            # Keep generated projections checkout-local even when persistent
            # cache roots are redirected.  Supply a unique non-existent path
            # so create_runtime_projection retains atomic no-clobber publish.
            import uuid
            from docker.versioning.effective import Filesystem
            return create_runtime_projection(
                projection,  # type: ignore[arg-type]
                host_path=os.path.join(parent_dir, f"runtime-{uuid.uuid4().hex}.toml"),
                _fs=Filesystem(repo_runtime_dir=parent_dir),
            )

        factory = _real_factory

    try:
        handle = factory(
            effective,
            parent_dir=request.projection_parent_dir,
        )
    except Exception as exc:
        return RunResult(
            exit_kind=ExitKind.CONFIG,
            message=f"Failed to create runtime projection: {exc}",
        )

    projection_hash: str | None = None
    try:
        with handle:
            # Capture projection identity
            projection_path = getattr(handle, "path", None)
            projection_hash = getattr(handle, "content_hash", None)
            projection_container_path = (
                "/run/pi-cli/docker-constructor.runtime.toml"
            )

            # ── Step 5: allocate pi-N ────────────────────────
            try:
                container_name = allocate_pi_name(request.inspector)
            except Exception as exc:
                return RunResult(
                    exit_kind=ExitKind.OPERATIONAL,
                    message=f"Failed to allocate container name: {exc}",
                )

            # ── Step 6: render vector ────────────────────────
            render_inputs = RunRenderInputs(
                image=request.image,
                container_name=container_name,
                pi_home_host=request.pi_home_host,
                projection_host_path=projection_path or "",
                projection_container_path=projection_container_path,
                main_project=request.selection.main_project,
                optional_projects=request.selection.optional_projects,
                host_access=host_access,
                tty=request.tty,
                stdin_open=request.stdin_open,
                command=request.command,
                chown_on_start=request.chown_on_start,
                artifact_mounts=artifact_mounts,
                corporate_trust_bundle=corporate_trust_bundle,
                proxy_url=proxy_url,
                proxy_no_proxy=proxy_no_proxy,
            )
            run_args = render_run_vector(render_inputs)

            # ── Step 7: execute ──────────────────────────────
            try:
                result = request.executor.run(
                    run_args,
                    interactive=(request.tty or request.stdin_open),
                )
            except Exception as exc:
                return RunResult(
                    exit_kind=ExitKind.OPERATIONAL,
                    message=str(exc),
                    run_args=run_args,
                    projection_path=projection_path,
                    projection_hash=projection_hash,
                    container_name=container_name,
                )

            if result.return_code == 0:
                return RunResult(
                    exit_kind=ExitKind.SUCCESS,
                    run_args=run_args,
                    process_result=result,
                    projection_path=projection_path,
                    projection_hash=projection_hash,
                    container_name=container_name,
                )
            else:
                return RunResult(
                    exit_kind=ExitKind.OPERATIONAL,
                    message=f"Container exited with code "
                            f"{result.return_code}",
                    run_args=run_args,
                    process_result=result,
                    projection_path=projection_path,
                    projection_hash=projection_hash,
                    container_name=container_name,
                )

    finally:
        # Step 8: projection is cleaned up by the context manager.
        # Handle attributes are captured above before __exit__ runs.
        pass


# ═══════════════════════════════════════════════════════════════════
# Docker-backed boundaries
# ═══════════════════════════════════════════════════════════════════


class DockerContainerInspector:
    """Real :class:`ContainerNameInspector` backed by ``docker ps -a``
    through an injectable :class:`ProcessRunner`."""

    _ARGV = ["docker", "ps", "-a", "--format", "{{.Names}}"]

    def __init__(self, runner: ProcessRunner) -> None:
        self._runner = runner

    def list_names(self) -> set[str]:
        """Run ``docker ps -a --format '{{.Names}}'`` and return the
        set of container names."""
        try:
            result = self._runner.run(list(self._ARGV),
                                      mode=ExecutionMode.CAPTURED)
        except OSError as exc:
            raise ContainerInspectError(str(exc)) from exc

        if result.return_code != 0:
            raise ContainerInspectError(
                result.stderr.strip() or "docker ps failed"
            )

        lines = result.stdout.split("\n")
        names: set[str] = set()
        for line in lines:
            stripped = line.strip()
            if stripped:
                names.add(stripped)
        return names


class DockerRunExecutor:
    """Real :class:`RunExecutor` backed by ``docker run ...``
    through an injectable :class:`ProcessRunner`."""

    def __init__(self, runner: ProcessRunner) -> None:
        self._runner = runner

    def run(self, argv: tuple[str, ...], *,
            interactive: bool = False) -> ProcessResult:
        """Execute the rendered ``docker`` argument vector."""
        mode = (
            ExecutionMode.INTERACTIVE if interactive
            else ExecutionMode.CAPTURED
        )
        return self._runner.run(list(argv), mode=mode)
