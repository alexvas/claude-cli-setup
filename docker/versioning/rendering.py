"""Deterministic build-environment rendering from effective configuration.

Converts an ``EffectiveConfiguration`` into Compose build arguments and
a generated TOML inventory file.  No Docker, no network, no subprocess.
"""
from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Iterable, Mapping, Optional, Sequence

from .effective import (
    EffectiveBuildProjection,
    EffectiveConfiguration,
    to_plain_data,
)
from .errors import EffectiveConfigError

# ---------------------------------------------------------------------------
# Immutable rendering input models (Stage 6)
# ---------------------------------------------------------------------------

# Fixed container-side destination for the host Pi home mount.
# The container user is always ``dev`` regardless of the host user.
_CONTAINER_PI_HOME = "/home/dev/.pi"

# Fixed read-only container root for runtime artifact mounts.
_RUNTIME_ARTIFACT_ROOT = "/run/pi-cli/runtime-artifacts"


@dataclass(frozen=True)
class ArtifactMount:
    """Post-materialization mount specification for a single
    verified runtime artifact blob.

    The *container_target* MUST be a canonical path beneath
    ``/run/pi-cli/runtime-artifacts``, derived solely from the
    validated integrity digest.  Traversal segments, absolute
    paths outside the canonical root, and non-canonical
    targets are rejected before the renderer emits any mount
    argument."""

    host_path: str
    """Absolute host path to the verified blob in the cache."""

    container_target: str
    """Canonical read-only mount target inside the container
    (e.g. ``"/run/pi-cli/runtime-artifacts/sha512/<digest>"``)."""


def plan_artifact_mounts(
    verified_blobs: "Iterable[VerifiedCacheBlob]",
) -> "tuple[ArtifactMount, ...]":
    """Build one ``ArtifactMount`` per verified materialized blob.

    *host_path* is passed through directly from each blob — the
    planner does **not** reconstruct cache paths.  *container_target*
    is derived from the blob's integrity via ``_derive_artifact_id``,
    always beneath the fixed ``/run/pi-cli/runtime-artifacts`` root.

    Duplicate integrities are collapsed into a single mount.
    Results are sorted by *container_target* for determinism.

    This is the **production mount-planning boundary** — every
    ``ArtifactMount`` consumed by the rendering and launcher
    stages MUST originate here.  No filesystem access; pure
    string computation.
    """
    from .model import _derive_artifact_id

    seen: set[str] = set()
    mounts: list[ArtifactMount] = []
    for blob in verified_blobs:
        if blob.integrity in seen:
            continue
        seen.add(blob.integrity)
        artifact_id = _derive_artifact_id(blob.integrity)
        mounts.append(ArtifactMount(
            host_path=blob.host_path,
            container_target=f"{_RUNTIME_ARTIFACT_ROOT}/{artifact_id}",
        ))
    mounts.sort(key=lambda m: m.container_target)
    return tuple(mounts)


@dataclass(frozen=True)
class CacheControls:
    """Docker build cache controls.

    *enabled* is ``True`` to use the default BuildKit cache; ``False``
    adds ``--no-cache`` to the build command.
    """
    enabled: bool = True


@dataclass(frozen=True)
class BuildRenderInputs:
    """Immutable input for ``docker build`` command rendering.

    Every attribute maps to a concrete Docker CLI argument.  The
    renderer produces a ``tuple[str, ...]`` argument vector from this
    container without invoking Docker, resolving overrides, or reading
    ``docker-constructor.toml``.
    """

    build_context: str
    """Repository root — the Docker build context path."""

    projection: EffectiveBuildProjection
    """Resolved effective build projection from Stage 4."""

    target_stage: str
    """Dockerfile stage name (e.g. ``"runtime"``)."""

    image_tag: str
    """Canonical image tag applied via ``--tag``."""

    platform: str
    """Docker platform string (e.g. ``"linux/amd64"``)."""

    cache: CacheControls = CacheControls()
    """Cache behaviour."""

    pull: bool = False
    """Always pull base images (``--pull``)."""

    progress: str = "auto"
    """BuildKit progress mode: ``"auto"``, ``"plain"``, or ``"tty"``."""

    dockerfile: Optional[str] = None
    """Relative path to the Dockerfile inside *build_context*.

    When ``None`` (the default) Docker uses ``Dockerfile`` in the
    build-context root.  Set to ``"docker/Dockerfile"`` or similar when
    the Dockerfile is not at the repository root.
    """

    dev_uid: int = 1000
    """Host user UID injected as ``DEV_UID`` build argument.

    Controls file ownership inside the built image so that the ``dev``
    container user matches the host user's UID.
    """

    dev_gid: int = 1000
    """Host user GID injected as ``DEV_GID`` build argument."""


@dataclass(frozen=True)
class RunRenderInputs:
    """Immutable input for ``docker run`` command rendering.

    Every attribute maps to a concrete Docker CLI argument or mount.
    The renderer produces a ``tuple[str, ...]`` argument vector from
    this container without invoking Docker, discovering projects,
    probing gateways, or prompting the user.
    """

    image: str
    """Canonical image to run."""

    container_name: str
    """Container name assigned via ``--name``."""

    projection_host_path: str
    """Host path to the private runtime projection file.

    This is the path returned by :meth:`RuntimeProjectionHandle.path`.
    The caller must keep the handle alive while the container runs.
    """

    projection_container_path: str
    """Fixed read-only mount path inside the container
    (e.g. ``"/run/pi-cli/docker-constructor.runtime.toml"``).
    """

    pi_home_host: str
    """Host path to the Pi home directory (e.g. ``"~/.pi"`` or
    ``"/home/alice/.pi"``).  Mounted into the container at the fixed
    destination ``/home/dev/.pi`` — the paths are intentionally
    asymmetric because the container user is always ``dev``.
    """

    main_project: str
    """Host path to the main project.  Bound as ``PROJECT_PATH_1`` and
    set as the container working directory.
    """

    optional_projects: tuple[str, ...] = ()
    """Additional host project paths bound as ``PROJECT_PATH_2``,
    ``PROJECT_PATH_3``, etc.
    """

    gateway: str = "host-gateway"
    """Value for ``--add-host host.docker.internal:<value>``."""

    tty: bool = True
    """Allocate a pseudo-TTY (``--tty``)."""

    stdin_open: bool = True
    """Keep STDIN open (``--interactive``)."""

    command: tuple[str, ...] = ()
    """Command and arguments to pass through to the container entrypoint.
    An empty tuple means the image's default ``CMD`` is used.
    """

    chown_on_start: Optional[str] = None
    """Value for ``CHOWN_WORK_ON_START`` environment variable inside
    the container.  ``None`` omits the variable; a string like ``"1"``
    or ``"0"`` adds ``--env CHOWN_WORK_ON_START=<value>``.
    """

    artifact_mounts: tuple[ArtifactMount, ...] = ()
    """Verified runtime artifact blobs to mount as individual
    read-only volumes.  An empty tuple means no artifact mounts
    (dry-run or pre-materialization error).  Every mount target
    is validated for canonical form before rendering."""

    validate_artifact_sources: bool = True
    """When ``False`` (dry-run), filesystem checks on
    ``host_path`` are skipped; only target canonical form and
    destination collisions are validated.  Defaults to ``True``
    to enforce regular-file/symlink checks before Docker execution."""


# ── platform helpers ────────────────────────────────────────────────

# Mapping from internal platform names to Docker platform strings.
_PLATFORM_MAP: Mapping[str, str] = MappingProxyType({
    "linux-amd64": "linux/amd64",
    "linux-arm64": "linux/arm64",
})


def _docker_platform(internal: str) -> str:
    """Translate an internal platform name to a Docker platform string."""
    try:
        return _PLATFORM_MAP[internal]
    except KeyError:
        raise EffectiveConfigError(
            f"unknown platform: {internal!r}"
        )


# ── build-arg emission (ordered, no generic traversal) ──────────────

# Deterministic order matching every Dockerfile ARG declaration.
_BUILD_ARG_ORDER: tuple[tuple[str, str], ...] = (
    ("NODE_BASE_IMAGE", "node.image"),
    ("RUST_VERSION", "rust.version"),
    ("RUST_PROFILE", "rust.profile"),
    ("RUST_COMPONENTS", "rust.components"),
    ("RUSTUP_URL", "rust.rustup.url"),
    ("RUSTUP_SHA256", "rust.rustup.sha256"),
    ("UV_VERSION", "uv.version"),
    ("UV_URL", "uv.artifact.url"),
    ("UV_SHA256", "uv.artifact.sha256"),
    ("PYTHON_VERSION", "python_version"),
    ("TY_VERSION", "ty_version"),
    ("RTK_VERSION", "rtk.version"),
    ("RTK_URL", "rtk.artifact.url"),
    ("RTK_SHA256", "rtk.artifact.sha256"),
    ("FD_VERSION", "fd.version"),
    ("FD_URL", "fd.artifact.url"),
    ("FD_SHA256", "fd.artifact.sha256"),
    ("PI_VERSION", "pi_version"),
    ("OPENSPEC_VERSION", "openspec_version"),
    ("OH_MY_ZSH_VERSION", "oh_my_zsh_revision"),
)


def _resolve_build_arg(proj: EffectiveBuildProjection, path: str) -> str:
    """Resolve a dotted path against the projection to a string value.

    ``tuple[str, ...]`` fields (e.g. ``rust.components``) are joined
    with a single space.
    """
    parts = path.split(".")
    obj: object = proj
    for part in parts:
        obj = getattr(obj, part)
    if isinstance(obj, tuple):
        return " ".join(obj)
    return str(obj)


def _emit_build_args(args: list[str], proj: EffectiveBuildProjection) -> None:
    """Append ``--build-arg NAME=VALUE`` pairs to *args* in
    ``_BUILD_ARG_ORDER``."""
    for arg_name, field_path in _BUILD_ARG_ORDER:
        raw = _resolve_build_arg(proj, field_path)
        args.extend(("--build-arg", f"{arg_name}={raw}"))


# ── validation ──────────────────────────────────────────────────────


def _validate_build_projection(proj: EffectiveBuildProjection) -> None:
    """Reject projection fields that are missing or empty."""
    # Every scalar version/revision field must be non-empty.
    for label, value in (
        ("NODE_BASE_IMAGE", proj.node.image),
        ("RUST_VERSION", proj.rust.version),
        ("RUST_PROFILE", proj.rust.profile),
        ("UV_VERSION", proj.uv.version),
        ("PYTHON_VERSION", proj.python_version),
        ("TY_VERSION", proj.ty_version),
        ("RTK_VERSION", proj.rtk.version),
        ("FD_VERSION", proj.fd.version),
        ("PI_VERSION", proj.pi_version),
        ("OPENSPEC_VERSION", proj.openspec_version),
        ("OH_MY_ZSH_VERSION", proj.oh_my_zsh_revision),
    ):
        if not value.strip():
            raise EffectiveConfigError(f"{label} is empty")

    # Rust components must not be empty.
    if not proj.rust.components:
        raise EffectiveConfigError("RUST_COMPONENTS is empty")

    # Every artifact must have a non-empty URL and SHA256.
    for label, art in (
        ("RUSTUP", proj.rust.rustup),
        ("UV", proj.uv.artifact),
        ("RTK", proj.rtk.artifact),
        ("FD", proj.fd.artifact),
    ):
        if not art.url.strip():
            raise EffectiveConfigError(f"{label}_URL is empty")
        if not art.sha256.strip():
            raise EffectiveConfigError(f"{label}_SHA256 is empty")


# ── run-vector helpers ──────────────────────────────────────────────

_PROJECTION_CANONICAL_CONTAINER_PATH: str = (
    "/run/pi-cli/docker-constructor.runtime.toml"
)


def _validate_run_inputs(inputs: RunRenderInputs) -> None:
    """Validate all ``RunRenderInputs`` fields before rendering."""
    # Required string fields must be non-empty.
    for label, value in (
        ("image", inputs.image),
        ("container_name", inputs.container_name),
        ("main_project", inputs.main_project),
    ):
        if not value.strip():
            raise ValueError(f"{label} must not be empty")

    # Optional projects must not contain empty entries.
    for i, p in enumerate(inputs.optional_projects):
        if not p.strip():
            raise ValueError(f"optional_projects[{i}] is empty")

    # Duplicate project paths (main vs optional, or among optionals).
    all_projects = [inputs.main_project] + list(inputs.optional_projects)
    seen: set[str] = set()
    for p in all_projects:
        if p in seen:
            raise ValueError(f"duplicate project path: {p}")
        seen.add(p)

    # Project and Pi-home paths must be absolute.
    for label, value in (
        ("main_project", inputs.main_project),
        ("pi_home_host", inputs.pi_home_host),
    ):
        if not value.startswith("/"):
            raise ValueError(f"{label} must be an absolute path, got {value!r}")
    for i, p in enumerate(inputs.optional_projects):
        if not p.startswith("/"):
            raise ValueError(
                f"optional_projects[{i}] must be an absolute path, got {p!r}"
            )

    # Projection container path must be canonical.
    if inputs.projection_container_path != _PROJECTION_CANONICAL_CONTAINER_PATH:
        raise ValueError(
            f"projection_container_path must be "
            f"{_PROJECTION_CANONICAL_CONTAINER_PATH!r}, "
            f"got {inputs.projection_container_path!r}"
        )

    # Projection host path must be under .docker-generated/runtime/ and
    # must not be a forbidden file.
    _validate_projection_host_path(inputs.projection_host_path)

    # Destination mount collisions: every dst must be unique across
    # Pi home, projection, and all project mounts.
    all_dsts: set[str] = {_CONTAINER_PI_HOME, inputs.projection_container_path}
    for p in all_projects:
        if p in all_dsts:
            raise ValueError(
                f"project path {p!r} collides with a fixed mount destination"
            )
        all_dsts.add(p)

    artifact_root = "/run/pi-cli/runtime-artifacts"
    seen_sources: set[str] = set()
    for mount in inputs.artifact_mounts:
        if inputs.validate_artifact_sources:
            # Reject missing, symlink, or non-regular *before* realpath so
            # the defined error message surfaces even for missing blobs.
            if not os.path.isabs(mount.host_path):
                raise ValueError(
                    "artifact mount source must be canonical and absolute"
                )
            if not os.path.isfile(mount.host_path) or os.path.islink(mount.host_path):
                raise ValueError(
                    "artifact mount source must be a regular non-symlink file"
                )
            source: str
            try:
                source = os.path.realpath(mount.host_path)
            except OSError:
                raise ValueError(
                    "artifact mount source must be a regular non-symlink file"
                )
            if source != mount.host_path:
                raise ValueError(
                    "artifact mount source must be canonical and absolute"
                )
        else:
            # Dry-run: no filesystem access — use absolute path directly.
            source = os.path.abspath(mount.host_path)

        target = os.path.normpath(mount.container_target)
        if not target.startswith(artifact_root + "/") or target != mount.container_target:
            raise ValueError("artifact mount target must be canonical beneath fixed root")
        if source in seen_sources or target in all_dsts or source == target:
            raise ValueError("duplicate or aliased artifact mount")
        seen_sources.add(source)
        all_dsts.add(target)


def plan_dry_run_artifact_mounts(
    selected_artifacts: "Iterable[SelectedArtifact]",
) -> "tuple[ArtifactMount, ...]":
    """Build artifact mounts for dry-run display from resolution output.

    Derives *host_path* from ``DEFAULT_RUNTIME_ARTIFACT_CACHE_ROOT``
    (the deterministic cache location) and *container_target* from
    ``_RUNTIME_ARTIFACT_ROOT``.  No filesystem access — the blobs may
    not exist yet.  Duplicate integrities are collapsed; results are
    sorted by *container_target*.
    """
    from . import artifact_cache
    from .model import _derive_artifact_id

    seen: set[str] = set()
    mounts: list[ArtifactMount] = []
    for art in selected_artifacts:
        if art.integrity in seen:
            continue
        seen.add(art.integrity)
        artifact_id = _derive_artifact_id(art.integrity)
        mounts.append(ArtifactMount(
            host_path=os.path.abspath(
                os.path.join(
                    artifact_cache.DEFAULT_RUNTIME_ARTIFACT_CACHE_ROOT,
                    artifact_id,
                )
            ),
            container_target=f"{_RUNTIME_ARTIFACT_ROOT}/{artifact_id}",
        ))
    mounts.sort(key=lambda m: m.container_target)
    return tuple(mounts)


def _validate_projection_host_path(host_path: str) -> None:
    """Reject projection host paths that are forbidden or outside
    the allowed ``.docker-generated/runtime/`` directory."""
    import os

    # Must be absolute.
    if not host_path.startswith("/"):
        raise ValueError(
            f"projection_host_path must be absolute, got {host_path!r}"
        )

    normalized = os.path.normpath(host_path)
    parts = normalized.split(os.sep)

    # Must have at least: /, .docker-generated, runtime, <file>
    if len(parts) < 3:
        raise ValueError(
            f"projection_host_path must be under .docker-generated/runtime/, "
            f"got {host_path!r}"
        )

    # The parent directory must be named '.docker-generated' and its
    # child must be 'runtime'.
    if parts[-3] != ".docker-generated" or parts[-2] != "runtime":
        raise ValueError(
            f"projection_host_path must be under .docker-generated/runtime/, "
            f"got {host_path!r}"
        )

    # Reject effective build projection.
    if "build.effective" in parts[-1]:
        raise ValueError(
            f"projection_host_path must not reference effective build "
            f"projection, got {host_path!r}"
        )

    # Reject docker-constructor.toml explicitly (the reviewed source).
    if parts[-1] == "docker-constructor.toml":
        raise ValueError(
            f"projection_host_path must not be docker-constructor.toml, "
            f"got {host_path!r}"
        )


def _emit_run_mount(
    args: list[str],
    type_: str,
    src: str,
    dst: str,
    *,
    readonly: bool = False,
) -> None:
    """Append a ``--mount`` argument to *args*."""
    parts = [f"type={type_}", f"src={src}", f"dst={dst}"]
    if readonly:
        parts.append("readonly")
    args.extend(("--mount", ",".join(parts)))


# ── existing rendering functions ────────────────────────────────────


def render_build_vector(inputs: BuildRenderInputs) -> tuple[str, ...]:
    """Render a deterministic ``docker build`` argument vector.

    Returns a ``tuple[str, ...]`` suitable for ``subprocess.run``.
    The renderer never invokes Docker, reads ``docker-constructor.toml``,
    or resolves overrides.

    Raises:
        EffectiveConfigError: a required projection field is missing
            or empty, or the command platform does not match the
            projection platform.
    """
    # 1.  Validate platform match between command and projection.
    expected_platform = _docker_platform(inputs.projection.platform)
    if inputs.platform != expected_platform:
        raise EffectiveConfigError(
            f"platform mismatch: command expects {inputs.platform!r}, "
            f"projection built for {expected_platform!r}"
        )

    # 2.  Validate required projection fields and image tag.
    _validate_build_projection(inputs.projection)
    if not inputs.image_tag.strip():
        raise ValueError("image_tag must not be empty")
    if not inputs.target_stage.strip():
        raise ValueError("target_stage must not be empty")
    if not inputs.build_context.strip():
        raise ValueError("build_context must not be empty")
    if inputs.progress not in ("auto", "plain", "tty"):
        raise ValueError(
            f"unsupported progress mode {inputs.progress!r}; "
            f"expected 'auto', 'plain', or 'tty'"
        )

    # 3.  Build the deterministic argument vector.
    args: list[str] = ["docker", "build"]

    # Flags — always in this order.
    args.extend(("--tag", inputs.image_tag))
    args.extend(("--target", inputs.target_stage))
    args.extend(("--platform", inputs.platform))
    args.extend(("--progress", inputs.progress))

    if inputs.dockerfile is not None:
        args.extend(("--file", inputs.dockerfile))

    if not inputs.cache.enabled:
        args.append("--no-cache")

    if inputs.pull:
        args.append("--pull")

    # Build arguments — deterministic order matching the Dockerfile ARGs.
    _emit_build_args(args, inputs.projection)

    # DEV_UID / DEV_GID — host-user identity, not from the projection.
    if inputs.dev_uid < 0:
        raise ValueError(f"dev_uid must be >= 0, got {inputs.dev_uid}")
    if inputs.dev_gid < 0:
        raise ValueError(f"dev_gid must be >= 0, got {inputs.dev_gid}")
    args.extend(("--build-arg", f"DEV_UID={inputs.dev_uid}"))
    args.extend(("--build-arg", f"DEV_GID={inputs.dev_gid}"))

    # Build context is always the final positional argument.
    args.append(inputs.build_context)

    return tuple(args)


def render_run_vector(inputs: RunRenderInputs) -> tuple[str, ...]:
    """Render a deterministic ``docker run`` argument vector.

    Returns a ``tuple[str, ...]`` suitable for ``subprocess.run``.
    The renderer never invokes Docker, discovers projects, probes
    gateways, or prompts the user.
    """
    # 1.  Validate all inputs before rendering.
    _validate_run_inputs(inputs)

    # 2.  Build the deterministic argument vector.
    args: list[str] = ["docker", "run", "--rm"]

    # --name
    args.extend(("--name", inputs.container_name))

    # TTY / stdin flags
    if inputs.tty:
        args.append("--tty")
    if inputs.stdin_open:
        args.append("--interactive")

    # Mounts — ordered: Pi home, projection, main project, optional projects.
    _emit_run_mount(args, "bind", inputs.pi_home_host, _CONTAINER_PI_HOME)
    _emit_run_mount(
        args, "bind",
        inputs.projection_host_path,
        inputs.projection_container_path,
        readonly=True,
    )
    _emit_run_mount(args, "bind", inputs.main_project, inputs.main_project)
    for p in inputs.optional_projects:
        _emit_run_mount(args, "bind", p, p)
    for mount in sorted(inputs.artifact_mounts, key=lambda item: item.container_target):
        _emit_run_mount(
            args, "bind", mount.host_path, mount.container_target, readonly=True,
        )

    # Working directory
    args.extend(("--workdir", inputs.main_project))

    # Environment: PROJECT_PATH_*
    all_projects = (inputs.main_project,) + inputs.optional_projects
    for i, proj_path in enumerate(all_projects, start=1):
        args.extend(("--env", f"PROJECT_PATH_{i}={proj_path}"))

    if inputs.chown_on_start is not None:
        args.extend(("--env", f"CHOWN_WORK_ON_START={inputs.chown_on_start}"))

    # Gateway
    args.extend(("--add-host", f"host.docker.internal:{inputs.gateway}"))

    # Image
    args.append(inputs.image)

    # Command passthrough
    args.extend(inputs.command)

    return tuple(args)


def render_command_display(args: tuple[str, ...]) -> str:
    """Render a command vector as a shell-escaped string for display.

    Returns a ``str`` suitable for terminal output (logs, dry-run
    messages).  The returned string MUST NOT be fed back into
    ``subprocess`` — it may contain shell metacharacters that would
    alter the executed command.
    """
    import shlex

    return shlex.join(list(args))


def render_build_environment(
    effective: EffectiveConfiguration,
    *,
    platform: str = "linux-amd64",
) -> Mapping[str, str]:
    """Return a deterministic mapping of build-argument names to string values.

    Each key is a Docker ``--build-arg`` name; each value is a plain string
    (never a list or mapping).  The mapping is derived from the immutable
    *effective* configuration and never consults the network or filesystem.
    """
    inv = effective.inventory

    artifacts_uv = inv.stages.toolchain.uv.artifacts.get(platform)
    if artifacts_uv is None:
        raise EffectiveConfigError(
            f"No artifact for platform {platform!r} in uv entry"
        )
    artifacts_rtk = inv.stages.rtk_prebuilt.rtk.artifacts.get(platform)
    if artifacts_rtk is None:
        raise EffectiveConfigError(
            f"No artifact for platform {platform!r} in rtk entry"
        )
    artifacts_fd = inv.stages.fd_prebuilt.fd.artifacts.get(platform)
    if artifacts_fd is None:
        raise EffectiveConfigError(
            f"No artifact for platform {platform!r} in fd entry"
        )

    node = inv.stages.base.node
    registry = node.source.registry.rstrip("/")
    repository = node.source.repository
    node_image = f"{registry}/{repository}:{node.tag}@{node.digest}"

    result: dict[str, str] = {}

    # Base
    result["NODE_BASE_IMAGE"] = node_image

    # Toolchain
    result["RUST_VERSION"] = inv.stages.toolchain.rust.version
    result["RUST_PROFILE"] = inv.stages.toolchain.rust.profile
    result["RUST_COMPONENTS"] = " ".join(inv.stages.toolchain.rust.components)
    # Mandatory rustup bootstrap artifact
    rustup_artifact = inv.stages.toolchain.rust.rustup.get(platform)
    if rustup_artifact is None:
        raise EffectiveConfigError(
            f"No artifact for platform {platform!r} in rustup entry"
        )
    result["RUSTUP_URL"] = rustup_artifact.url
    result["RUSTUP_SHA256"] = rustup_artifact.sha256
    result["UV_VERSION"] = inv.stages.toolchain.uv.version
    result["UV_URL"] = artifacts_uv.url
    result["UV_SHA256"] = artifacts_uv.sha256
    result["PYTHON_VERSION"] = inv.stages.toolchain.python.version
    result["TY_VERSION"] = inv.stages.toolchain.ty.version

    # Prebuilt
    result["RTK_VERSION"] = inv.stages.rtk_prebuilt.rtk.version
    result["RTK_URL"] = artifacts_rtk.url
    result["RTK_SHA256"] = artifacts_rtk.sha256
    result["FD_VERSION"] = inv.stages.fd_prebuilt.fd.version
    result["FD_URL"] = artifacts_fd.url
    result["FD_SHA256"] = artifacts_fd.sha256

    # Node tools
    result["PI_VERSION"] = inv.stages.pi_tools.pi.version
    result["OPENSPEC_VERSION"] = inv.stages.openspec_tools.openspec.version

    # Runtime
    result["OH_MY_ZSH_VERSION"] = inv.stages.runtime.oh_my_zsh.revision

    # Pi extensions (deterministic sorted by name)
    for name in sorted(inv.runtime_pi_extensions.keys()):
        ext = inv.runtime_pi_extensions[name]
        prefix = name.upper().replace("-", "_").replace("@", "")
        result[f"{prefix}_VERSION"] = ext.version

    return MappingProxyType(result)


def write_effective_inventory(
    effective: EffectiveConfiguration,
    destination: Path,
    *,
    repo_root: Path | None = None,
    output_path: str | None = None,
) -> None:
    """Write the effective inventory as TOML to *destination*.

    The file is written atomically via a sibling temporary file followed
    by ``os.replace()``.  The parent directory is created if needed.

    When *repo_root* and *output_path* are provided, the path is validated:

    * Must be a relative path inside *repo_root*
    * Must not be the authoritative ``docker-constructor.toml``
    * Must not contain ``..`` traversal or absolute paths
    * Must not resolve to a symlink pointing outside *repo_root*

    The validated *destination* is then ``repo_root / output_path``
    resolved.
    """
    if repo_root is not None and output_path is not None:
        destination = _validate_inventory_output(repo_root, output_path)

    data = to_plain_data(effective.inventory)

    destination.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(
        suffix=".toml",
        prefix=".versions-",
        dir=str(destination.parent),
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            _write_toml(fh, data)
    except Exception:
        os.unlink(tmp_path)
        raise
    os.replace(tmp_path, destination)


def _validate_inventory_output(
    repo_root: Path, relative_path: str
) -> Path:
    """Validate *relative_path* is safe and return the resolved ``Path``.

    Rejects:
    * Absolute paths
    * ``..`` traversal
    * The authoritative ``docker-constructor.toml``
    * Symlink escapes (resolved real path outside repo_root)
    """
    repo_root = repo_root.resolve()

    # Reject absolute paths
    if relative_path.startswith("/") or Path(relative_path).is_absolute():
        raise EffectiveInventoryOutputError(
            f"Effective inventory output must be a relative path, "
            f"not {relative_path!r}"
        )

    # Reject traversal
    if ".." in Path(relative_path).parts:
        raise EffectiveInventoryOutputError(
            f"Effective inventory output must be inside the repo root; "
            f"{relative_path!r} contains '..'"
        )

    # Reject docker-constructor.toml (exact match only, not prefixed)
    norm = Path(relative_path).as_posix()
    if norm in ("docker-constructor.toml", "./docker-constructor.toml"):
        raise EffectiveInventoryOutputError(
            "Effective inventory output cannot be docker-constructor.toml "
            "(the authoritative source)"
        )

    # Resolve and check boundaries + symlinks.
    # Use strict=False for the intermediate resolve so we can detect
    # symlinks at the leaf component separately.
    raw = repo_root / relative_path  # may not exist yet
    # Resolve parent without following symlinks at the leaf
    raw_parent = raw.parent.resolve() if raw.parent != raw else raw.parent

    # Check parent is inside repo_root
    try:
        raw_parent.relative_to(repo_root)
    except ValueError:
        raise EffectiveInventoryOutputError(
            f"Effective inventory output must be inside the repo root; "
            f"{relative_path!r} resolves to {str(raw_parent)!r}"
        )

    # Walk intermediate components for symlink escapes
    for parent in raw_parent.parents:
        if parent == repo_root:
            break
        if parent.is_symlink():
            real_parent = parent.resolve()
            try:
                real_parent.relative_to(repo_root)
            except ValueError:
                raise EffectiveInventoryOutputError(
                    f"Effective inventory output traverses a symlink "
                    f"pointing outside the repo root: {str(parent)!r} "
                    f"-> {str(real_parent)!r}"
                )

    # Reject if the leaf exists and is a symlink outside
    if raw.is_symlink():
        real = raw.resolve()
        try:
            real.relative_to(repo_root)
        except ValueError:
            raise EffectiveInventoryOutputError(
                f"Effective inventory output is a symlink pointing "
                f"outside the repo root: {relative_path!r} "
                f"-> {str(real)!r}"
            )

    resolved = raw.resolve()

    return resolved


class EffectiveInventoryOutputError(ValueError):
    """Raised when the effective inventory output path is invalid."""


def compose_command(args: Sequence[str]) -> tuple[str, ...]:
    """Return the canonical ``docker compose`` argument tuple.

    ``args`` are the user-supplied arguments after ``--``, e.g.
    ``("build", "pi")``.
    """
    return ("docker", "compose", *args)


# ---------------------------------------------------------------------------
# Deterministic TOML serialization
# ---------------------------------------------------------------------------

_TOML_BARE_KEY_RE = __import__("re").compile(r'^[A-Za-z0-9_-]+$')


def _toml_key(k: str) -> str:
    """Quote *k* if it contains characters not allowed in TOML bare keys.

    Uses TOML basic-string quoting with proper escape of backslash and
    double-quote characters.
    """
    if _TOML_BARE_KEY_RE.match(k):
        return k
    escaped = k.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def _write_toml(fh: object, data: object, *, _prefix: str = "") -> None:
    """Write plain-data *data* as deterministically-ordered TOML.

    Uses dotted-key table headers (``[build.stages.toolchain.rust]``) for
    sections and inline ``key = value`` for leaves and small tables.
    """
    if isinstance(data, dict):
        _write_dict(fh, data, _prefix)
    elif isinstance(data, list):
        _write_array(fh, data, _prefix)
    elif isinstance(data, str):
        fh.write(f"{_toml_str(data)}\n")
    elif isinstance(data, bool):
        fh.write(f"{'true' if data else 'false'}\n")
    elif isinstance(data, (int, float)):
        fh.write(f"{data}\n")
    elif data is None:
        fh.write("# <absent>\n")
    else:
        fh.write(f"{_toml_str(str(data))}\n")


def _write_dict(fh: object, data: dict, prefix: str) -> None:
    keys = sorted(data.keys(), key=str)
    # Scalars first, then arrays, then nested dicts.
    # TOML requires that bare ``key = value`` lines appear before
    # any ``[header]`` — otherwise they get absorbed into the last table.
    # Arrays (e.g. components = [...]) must also precede nested tables
    # because a plain ``key = [...]`` after a ``[subsection]`` header
    # would be captured into that subsection.
    scalars: list[tuple[str, object]] = []
    nested: list[tuple[str, object]] = []
    arrays: list[tuple[str, object]] = []

    for k in keys:
        v = data[k]
        if isinstance(v, dict):
            if _is_leaf_dict(v):
                scalars.append((k, v))  # inline table counts as scalar
            else:
                nested.append((k, v))
        elif isinstance(v, list):
            arrays.append((k, v))
        else:
            scalars.append((k, v))

    # --- scalars ---
    for k, v in scalars:
        qk = _toml_key(k)
        if isinstance(v, dict):
            # Inline table — omit None values (TOML has no null literal)
            parts = []
            for sk in sorted(v.keys(), key=str):
                sv = v[sk]
                if sv is None:
                    continue
                parts.append(f"{_toml_key(sk)} = {_toml_value(sv)}")
            if parts:
                fh.write(f"{qk} = {{ ")
                fh.write(", ".join(parts))
                fh.write(" }\n")
            # else: empty inline table → omit entirely
        elif isinstance(v, str):
            fh.write(f"{qk} = {_toml_str(v)}\n")
        elif isinstance(v, bool):
            fh.write(f"{qk} = {'true' if v else 'false'}\n")
        elif isinstance(v, (int, float)):
            fh.write(f"{qk} = {v}\n")
        elif v is None:
            fh.write(f"# {qk} = <absent>\n")
        else:
            fh.write(f"{qk} = {_toml_str(str(v))}\n")

    # --- nested dicts (table headers) ---
    # Emit arrays BEFORE nested tables so that ``components = [...]``
    # lines are not captured into a preceding ``[subsection]``.
    for k, v in arrays:
        qk = _toml_key(k)
        full = f"{prefix}.{qk}" if prefix else qk
        if all(isinstance(i, dict) for i in v):
            for item in v:
                fh.write(f"\n[[{full}]]\n")
                _write_inline_dict(fh, item)
        else:
            fh.write(f"{qk} = [")
            fh.write(", ".join(_toml_value(i) for i in v))
            fh.write("]\n")

    # --- nested dicts (table headers) ---
    for k, v in nested:
        qk = _toml_key(k)
        full = f"{prefix}.{qk}" if prefix else qk
        fh.write(f"\n[{full}]\n")
        _write_dict(fh, v, full)


def _is_leaf_dict(d: dict) -> bool:
    """Return True if *d* contains only scalar/string values (no nested dicts/lists)."""
    for v in d.values():
        if isinstance(v, (dict, list)):
            return False
    return True


def _write_inline_dict(fh: object, data: dict) -> None:
    """Write an inline key=value dict for array-of-tables entries."""
    for k in sorted(data.keys(), key=str):
        v = data[k]
        fh.write(f"{k} = {_toml_value(v)}\n")


def _write_array(fh: object, data: list, prefix: str) -> None:
    if not prefix:
        fh.write("[]\n")
        return
    if all(isinstance(i, dict) for i in data):
        for item in data:
            fh.write(f"\n[[{prefix}]]\n")
            _write_inline_dict(fh, item)
    else:
        fh.write(f"{prefix} = [")
        fh.write(", ".join(_toml_value(i) for i in data))
        fh.write("]\n")


def _toml_value(v: object) -> str:
    """Format a scalar value for TOML."""
    if isinstance(v, str):
        return _toml_str(v)
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        return str(v)
    if v is None:
        return '""'
    return _toml_str(str(v))


def _toml_str(s: str) -> str:
    """Quote *s* as a TOML basic string, escaping backslashes and quotes."""
    escaped = s.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


# ---------------------------------------------------------------------------
# Effective Build Projection serialization (Stage 4)
# ---------------------------------------------------------------------------

import dataclasses as _dc


def serialize_effective_build(projection) -> dict[str, object]:
    """Serialize an EffectiveBuildProjection to a deterministic plain dict."""
    p = projection
    return {
        "platform": p.platform,
        "node": {
            "image": p.node.image,
        },
        "rust": _serialize_rust(p.rust),
        "uv": _serialize_tool(p.uv),
        "python": {
            "version": p.python_version,
        },
        "ty": {
            "version": p.ty_version,
        },
        "rtk": _serialize_tool(p.rtk),
        "fd": _serialize_tool(p.fd),
        "pi": {
            "version": p.pi_version,
        },
        "openspec": {
            "version": p.openspec_version,
        },
        "oh-my-zsh": {
            "revision": p.oh_my_zsh_revision,
        },
    }


def _serialize_rust(rust) -> dict[str, object]:
    result: dict[str, object] = {
        "version": rust.version,
        "profile": rust.profile,
        "components": list(rust.components),
        "rustup": {
            "url": rust.rustup.url,
            "sha256": rust.rustup.sha256,
        },
    }
    return result


def _serialize_tool(tool) -> dict[str, object]:
    return {
        "version": tool.version,
        "artifact": {
            "url": tool.artifact.url,
            "sha256": tool.artifact.sha256,
        },
    }


def validate_effective_build(data: dict[str, object]):
    """Validate a plain dict against the EffectiveBuildProjection schema.

    Raises ValueError or EffectiveConfigError on invalid data.
    """
    from .model import EffectiveBuildProjection, EffectiveNode, EffectiveRust, \
        EffectiveTool, EffectiveArtifact

    if not isinstance(data, dict):
        raise ValueError("effective build projection must be a dict")

    required = {"platform", "node", "rust", "uv", "python", "ty", "rtk", "fd", "pi", "openspec", "oh-my-zsh"}
    missing = required - set(data.keys())
    if missing:
        raise ValueError(f"missing required sections: {sorted(missing)}")

    platform_val = data.get("platform")
    if platform_val not in ("linux-amd64", "linux-arm64"):
        raise ValueError(f"platform must be 'linux-amd64' or 'linux-arm64', got {platform_val!r}")

    node = data["node"]
    if not isinstance(node, dict) or "image" not in node:
        raise ValueError("node section missing 'image'")

    rust = data["rust"]
    for key in ("version", "profile", "components", "rustup"):
        if key not in rust:
            raise ValueError(f"rust section missing {key!r}")
    rustup = rust["rustup"]
    if not isinstance(rustup, dict):
        raise ValueError("rust.rustup must be a dict")
    for akey in ("url", "sha256"):
        if akey not in rustup:
            raise ValueError(f"rust.rustup missing {akey!r}")

    for section_name in ("uv", "rtk", "fd"):
        sec = data[section_name]
        if not isinstance(sec, dict):
            raise ValueError(f"{section_name} must be a dict")
        for key in ("version", "artifact"):
            if key not in sec:
                raise ValueError(f"{section_name} section missing {key!r}")
        art = sec["artifact"]
        if not isinstance(art, dict):
            raise ValueError(f"{section_name}.artifact must be a dict")
        for akey in ("url", "sha256"):
            if akey not in art:
                raise ValueError(f"{section_name}.artifact missing {akey!r}")

    for section_name in ("python", "ty", "pi", "openspec"):
        sec = data[section_name]
        if not isinstance(sec, dict) or "version" not in sec:
            raise ValueError(f"{section_name} section missing 'version'")

    oh = data["oh-my-zsh"]
    if not isinstance(oh, dict) or "revision" not in oh:
        raise ValueError("oh-my-zsh section missing 'revision'")

    # Reject runtime / extension keys (platform is allowed as a top-level scalar)
    forbidden = {"runtime", "pi-extensions", "extensions", "cache", "update", "override"}
    for key in data:
        if key in forbidden:
            raise ValueError(f"forbidden key in build projection: {key!r}")


def write_effective_build(
    projection,
    *,
    repo_root,
) -> Path:
    """Write the effective build projection atomically to the canonical path.

    The canonical output is always ``.docker-generated/docker-constructor.build.effective.toml``
    relative to *repo_root*.  No other destination is accepted.

    Symlink escapes are rejected: if ``.docker-generated`` or the leaf file
    is a symlink that points outside *repo_root*, the write is refused.

    Validates the projection before touching any existing file.
    Writes to a temporary sibling, flushes, and os.replaces.
    """
    repo_root = Path(repo_root).resolve()

    # Build unresolved canonical path; reject symlink escapes
    canonical_parent = repo_root / ".docker-generated"
    canonical_dest = canonical_parent / "docker-constructor.build.effective.toml"

    _require_not_symlink_escape(canonical_parent, repo_root, label=".docker-generated")
    # Leaf symlinks are always rejected — os.replace would overwrite the
    # target, leaving the canonical path as a symlink.
    if canonical_dest.is_symlink():
        raise EffectiveInventoryOutputError(
            f"docker-constructor.build.effective.toml is a symlink: {canonical_dest}"
        )

    destination = canonical_dest.resolve()

    # Validate before touching disk
    data = serialize_effective_build(projection)
    validate_effective_build(data)

    # Atomic write
    destination.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(
        suffix=".toml",
        prefix=".build-effective-",
        dir=str(destination.parent),
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            _write_toml(fh, data)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp_path, destination)
    except Exception:
        os.unlink(tmp_path)
        raise
    return destination


def _require_not_symlink_escape(path: Path, repo_root: Path, *, label: str) -> None:
    """Raise if *path* is a symlink that resolves outside *repo_root*.

    Used only for directory symlinks.  Leaf-file symlinks are unconditionally
    rejected by the caller.
    """
    if not path.is_symlink():
        return
    resolved = path.resolve()
    try:
        resolved.relative_to(repo_root)
    except ValueError:
        raise EffectiveInventoryOutputError(
            f"{label} is a symlink escaping repo root: {path} -> {resolved}"
        ) from None
