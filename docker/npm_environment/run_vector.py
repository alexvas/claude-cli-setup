"""Deterministic Docker run-vector rendering for the npm assembler.

``render_run_vector`` rechecks the validated-input and assembler bindings
before returning an immutable :class:`DockerRunVector`.  ``render_docker_argv``
turns that vector into the exact ``docker run`` argument list handed to the
execution boundary.  The vector carries a pinned image digest, numeric
UID/GID, a private HOME, read-only inputs, an opaque writable npm cache, one
writable staging output, and no consumer mounts or ambient environment.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .assembler import (
    ASSEMBLER_SCRIPT,
    assembler_script_digest,
    npm_policy_digest,
)
from .errors import LockedNpmError
from .identity import (
    AssemblerIdentity,
    compute_assembler_input_identity,
)
from .image_ref import validate_image_reference
from .model import ValidatedAssemblyInput

#: Fixed container paths — private HOME and the opaque npm cache both live
#: under the disposable cache mount; the staging workspace is the workdir.
ASSEMBLER_HOME = "/cache/home"
ASSEMBLER_CACHE = "/cache"
ASSEMBLER_WORKDIR = "/work"
LOCKFILE_CONTAINER_PATH = "/work/package-lock.json"


@dataclass(frozen=True, order=True)
class Mount:
    """One narrow bind mount for the assembler container."""

    host: str
    """Host path (must already be prepared by the caller)."""

    container: str
    """Container path."""

    mode: str
    """``"ro"`` or ``"rw"``."""


@dataclass(frozen=True)
class DockerRunVector:
    """Immutable, deterministic ``docker run`` vector for one assembly."""

    image: str
    """Pinned immutable image reference (bare digest or
    repository-qualified digest)."""

    user: str
    """Numeric ``"uid:gid"`` host identity."""

    name: str
    """Container name used for cancellation cleanup."""

    home: str
    """Private container HOME."""

    workdir: str
    """Container working directory (writable staging)."""

    env: tuple[tuple[str, str], ...]
    """Explicit, deterministic environment (no ambient input)."""

    mounts: tuple[Mount, ...]
    """Read-only inputs, opaque cache, and writable staging — nothing else."""

    command: tuple[str, ...]
    """``/bin/sh -c <canonical assembler script>``."""


def recheck_assembler_bindings(assembler: AssemblerIdentity) -> None:
    """Reject an assembler whose image reference or script/policy digests
    do not match the canonical script and policy bytes actually executed.

    The image reference is validated first so an invalid or mutable
    reference fails before any cache, staging, executor, or Docker effect.
    The assembler digest itself is re-verified by
    :func:`compute_assembler_input_identity`; this check ties the image
    reference and the two content digests to the fixed assembler script and
    npm policy.
    """
    validate_image_reference(assembler.image_digest)
    if assembler.script_digest != assembler_script_digest():
        raise LockedNpmError(
            "script_digest_mismatch",
            "the assembler script digest does not match the canonical "
            "assembler script bytes",
        )
    if assembler.policy_digest != npm_policy_digest():
        raise LockedNpmError(
            "policy_digest_mismatch",
            "the assembler policy digest does not match the fixed npm policy",
        )


def render_run_vector(
    *,
    validated: ValidatedAssemblyInput,
    assembler: AssemblerIdentity,
    staging: Path,
    npm_cache: Path,
    uid: int,
    gid: int,
    name: str,
) -> DockerRunVector:
    """Render a deterministic run vector after rechecking all bindings.

    Re-verifies the supplied validated input (re-running preflight and
    comparing field-for-field) and the assembler identity, rejects any
    script/policy digest drift, and then renders the vector with a pinned
    image digest, numeric UID/GID, private HOME, explicit environment,
    read-only lockfile input, opaque cache, and writable staging.
    """
    recheck_assembler_bindings(assembler)
    compute_assembler_input_identity(validated, assembler)

    env = (
        ("HOME", ASSEMBLER_HOME),
        ("npm_config_cache", ASSEMBLER_CACHE),
        ("REVIEWED_NODE_VERSION", validated.node_version),
        ("REVIEWED_NPM_VERSION", validated.npm_version),
    )
    mounts = (
        Mount(str(staging), ASSEMBLER_WORKDIR, "rw"),
        Mount(
            str(staging / "package-lock.json"),
            LOCKFILE_CONTAINER_PATH,
            "ro",
        ),
        Mount(str(npm_cache), ASSEMBLER_CACHE, "rw"),
    )
    return DockerRunVector(
        image=assembler.image_digest,
        user=f"{uid}:{gid}",
        name=name,
        home=ASSEMBLER_HOME,
        workdir=ASSEMBLER_WORKDIR,
        env=env,
        mounts=mounts,
        command=("/bin/sh", "-c", ASSEMBLER_SCRIPT),
    )


def render_docker_argv(
    vector: DockerRunVector, *, docker_bin: str = "docker"
) -> tuple[str, ...]:
    """Render the exact ``docker run`` argument list for *vector*."""
    argv = [docker_bin, "run", "--rm", "--name", vector.name, "--user", vector.user]
    for key, value in vector.env:
        argv.extend(("--env", f"{key}={value}"))
    for mount in vector.mounts:
        argv.extend(("--volume", f"{mount.host}:{mount.container}:{mount.mode}"))
    argv.extend(("--workdir", vector.workdir, vector.image))
    argv.extend(vector.command)
    return tuple(argv)
