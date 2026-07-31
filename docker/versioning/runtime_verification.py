"""Runtime verification — inspect a running container's state against
host-side expectations without injecting host metadata.

All process boundaries are injectable so tests remain daemon-independent.

Checks
------

+--------------------------+-----------------------------------------------------------+
| Key                      | What is verified                                          |
+==========================+===========================================================+
| ``projection.identity``  | The mount at ``/run/pi-cli/docker-constructor.runtime.toml``   |
|                          | is identical to the host file at ``runtime_projection_path``   |
|                          | (hash computed from the host file, never caller-supplied).     |
+--------------------------+-----------------------------------------------------------+
| ``projection.readonly``  | The runtime projection mount is read-only.  Verified via        |
|                          | ``/proc/mounts`` mount options (``ro``), not merely file       |
|                          | permissions — ``test -w`` is a secondary sanity check only.    |
+--------------------------+-----------------------------------------------------------+
| ``extensions.results``   | Every declared Pi extension has its npm package installed    |
|                          | at the expected version under                                |
|                          | ``/home/dev/.pi/agent/npm/node_modules/<package>/``          |
|                          | (verified by reading ``package.json``).                      |
+--------------------------+-----------------------------------------------------------+
| ``projects.present``     | ``PROJECT_PATH_1..N`` environment variables each contain        |
|                          | exactly the corresponding request-supplied path, AND each      |
|                          | directory exists and is accessible.  Numbering is consecutive  |
|                          | 1..N with no unexpected next entry.                           |
+--------------------------+-----------------------------------------------------------+
| ``working.directory``    | The container working directory equals ``PROJECT_PATH_1``.   |
+--------------------------+-----------------------------------------------------------+
| ``ownership.dev``        | ``/home/dev/.pi`` and every project path are owned            |
|                          | by ``dev:dev`` (UID/GID 1000:1000).                          |
+--------------------------+-----------------------------------------------------------+
| ``pi-home.setup``        | ``~/.pi`` exists and is writable by dev.                     |
+--------------------------+-----------------------------------------------------------+
| ``gateway.mapping``      | ``host.docker.internal`` resolves to exactly the address    |
|                          | persisted as ``expected_gateway`` during build.  A          |
|                          | different resolved address or a resolution failure are both |
|                          | check failures — there is no fallback.                     |
+--------------------------+-----------------------------------------------------------+
| ``forbidden.paths``      | ``/run/pi-cli/docker-constructor.toml`` (reviewed inventory)    |
|                          | and ``/run/pi-cli/docker-constructor.build.effective.toml``     |
|                          | (effective build projection) are NOT present inside the         |
|                          | container.  ``/.dockerenv`` is NOT checked — it normally        |
|                          | exists inside Docker containers.                                |
+--------------------------+-----------------------------------------------------------+

Every check runs ``docker exec <container> <command>`` through the
injected *runner*.  The effective runtime projection is read from the
host only — it is NEVER mounted or passed into the container as part
of verification.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, Sequence


# ── Process boundary (shared contract) ───────────────────────────────


@dataclass(frozen=True)
class ProcessResult:
    argv: tuple[str, ...]
    return_code: int
    stdout: str
    stderr: str


class ProcessRunner(Protocol):
    def run(self, argv: Sequence[str]) -> ProcessResult:
        """Execute *argv* and return the outcome."""
        ...


# ── Runtime verification models ──────────────────────────────────────


@dataclass(frozen=True)
class RuntimeCheck:
    """A single runtime-property observation."""
    key: str
    """Unique check key (e.g. ``"projection.identity"``)."""
    ok: bool
    """``True`` when the check passes."""
    detail: str
    """Human-readable description or failure reason."""


@dataclass(frozen=True)
class RuntimeVerificationResult:
    """Complete result of a runtime verification pass."""
    container: str
    checks: tuple[RuntimeCheck, ...]
    all_ok: bool
    """``True`` when every check is ``ok``."""
    errors: tuple[str, ...]
    """Non-check errors (container not found, exec failure, etc.)."""


# ── Request ──────────────────────────────────────────────────────────


@dataclass(frozen=True)
class VerifyRuntimeRequest:
    """Request to verify a running container against host-side runtime
expectations."""
    container: str
    """Container name or ID to inspect via ``docker exec``."""
    runtime_projection_path: Path
    """Path to the host-side effective runtime projection TOML file.
    The ``projection.identity`` check hashes this file and compares
    the container-side copy — the hash is derived from this path,
    not caller-supplied."""
    project_paths: tuple[Path, ...]
    """Project paths **inside the container** that should be present
    as ``PROJECT_PATH_1..N``."""
    container_pi_home: Path
    """Pi home path **inside the container** (e.g. ``"/home/dev/.pi"``).
    All runtime checks use this as the container-side directory — the
    host-side mapping is the launcher's responsibility and is not
    needed for verification."""
    expected_gateway: str
    """Gateway address persisted during build (e.g. ``"192.168.65.1"``).
    The ``gateway.mapping`` check MUST compare ``host.docker.internal``
    resolution to this exact value — a different address or resolution
    failure is a check failure."""
    runner: ProcessRunner
    """Injected process boundary for ``docker exec ...`` invocations."""


# ── Public API ───────────────────────────────────────────────────────


def verify_runtime(request: VerifyRuntimeRequest) -> RuntimeVerificationResult:
    """Run property checks against *container* and compare the
    observed state against host-side expectations.

    Every check uses ``docker exec`` through the injected *runner*.
    The effective runtime projection is read from the host only — it is
    NEVER mounted or passed into the container as part of verification.
    """
    raise NotImplementedError("verify_runtime — 12.2 RED")
