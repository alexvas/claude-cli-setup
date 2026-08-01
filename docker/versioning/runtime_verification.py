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
    command: tuple[str, ...] | None = None
    """The exact command vector that produced the primary diagnostic
    output (e.g. ``("sha256sum", "/run/pi-cli/...")``).  When the
    check involves a single ``_exec()`` call this matches the full
    ``docker exec`` argv; when the check runs multiple commands it
    holds the deciding command's argv.  ``None`` for checks that did
    not execute any command."""
    exit_code: int | None = None
    """Exit code of the command in *command*."""
    raw_stdout: str | None = None
    """Raw stdout captured from the command in *command*."""
    raw_stderr: str | None = None
    """Raw stderr captured from the command in *command*."""


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
    import hashlib
    import tomllib

    errors: list[str] = []
    checks: list[RuntimeCheck] = []
    runner = request.runner
    container = request.container
    pi_home = str(request.container_pi_home)
    pp = request.project_paths

    # ── Load projection + compute host hash ──────────────────────────
    try:
        proj_path = Path(request.runtime_projection_path)
        proj_bytes = proj_path.read_bytes()
        host_hash = hashlib.sha256(proj_bytes).hexdigest()
        proj_data = tomllib.loads(proj_bytes.decode())
    except (OSError, ValueError) as exc:
        return RuntimeVerificationResult(
            container=container,
            checks=(),
            all_ok=False,
            errors=(f"cannot read runtime projection: {exc}",),
        )

    def _exec(cmd: tuple[str, ...]) -> ProcessResult:
        """Run ``docker exec <container> ...``."""
        return runner.run(("docker", "exec", container, *cmd))

    def _add(key: str, ok: bool, detail: str,
             result: ProcessResult | None = None) -> None:
        checks.append(RuntimeCheck(
            key=key, ok=ok, detail=detail,
            command=result.argv if result is not None else None,
            exit_code=result.return_code if result is not None else None,
            raw_stdout=result.stdout if result is not None else None,
            raw_stderr=result.stderr if result is not None else None,
        ))

    # ── projection.identity ──────────────────────────────────────────
    r = _exec(("sha256sum", "/run/pi-cli/docker-constructor.runtime.toml"))
    if r.return_code != 0:
        _add("projection.identity", False,
             f"sha256sum failed (exit {r.return_code}): {r.stderr.strip()}", r)
    else:
        parts = r.stdout.strip().split()
        container_hash = parts[0] if parts else ""
        if container_hash == host_hash:
            _add("projection.identity", True,
                 f"projection hash {host_hash} matches host", r)
        else:
            _add("projection.identity", False,
                 f"hash mismatch: container={container_hash[:12]}…"
                 f" host={host_hash[:12]}…", r)

    # ── projection.readonly ──────────────────────────────────────────
    r = _exec(("grep", "docker-constructor.runtime.toml", "/proc/mounts"))
    if r.return_code != 0:
        _add("projection.readonly", False,
             "runtime projection not found in /proc/mounts", r)
    else:
        mount_line = r.stdout.strip()
        # Mount options are comma-separated in the 4th field.
        # Check if ``ro`` is present as a mount option.
        if mount_line:
            tokens = mount_line.split()
            if len(tokens) >= 4:
                opts = tokens[3].split(",")  # e.g. ro,nosuid,nodev,relatime
                if "ro" in opts:
                    rw = _exec(("test", "-w",
                                "/run/pi-cli/docker-constructor.runtime.toml"))
                    if rw.return_code != 0:
                        _add("projection.readonly", True,
                             "runtime projection is read-only"
                             " (ro mount + not writable)", rw)
                    else:
                        _add("projection.readonly", False,
                             "mount claims ro but file is writable", rw)
                else:
                    _add("projection.readonly", False,
                         f"runtime projection mount is not ro"
                         f" (options: {','.join(opts)})", r)
            else:
                _add("projection.readonly", False,
                     f"unexpected /proc/mounts format: {mount_line[:120]}", r)
        else:
            _add("projection.readonly", False,
                 "empty /proc/mounts line for projection", r)

    # ── extensions.results ───────────────────────────────────────────
    extensions = proj_data.get("extensions", {})
    for _key in sorted(extensions):
        ext = extensions[_key]
        pkg_name = ext["package"]
        expected_ver = ext["version"]
        pkg_json_path = f"/home/dev/.pi/agent/npm/node_modules/{pkg_name}/package.json"
        r = _exec(("cat", pkg_json_path))
        if r.return_code != 0:
            _add("extensions.results", False,
                 f"{pkg_name}: package.json not found", r)
        else:
            try:
                import json as _json
                pkg = _json.loads(r.stdout)
                actual_ver = pkg.get("version", "")
            except Exception:
                actual_ver = ""
            if actual_ver == expected_ver:
                _add("extensions.results", True,
                     f"{pkg_name} v{expected_ver} installed", r)
            else:
                _add("extensions.results", False,
                     f"{pkg_name}: expected v{expected_ver}, got v{actual_ver}", r)

    # ── projects.present ─────────────────────────────────────────────
    for i, p in enumerate(pp, start=1):
        sp = str(p)
        # Directory accessible
        r = _exec(("test", "-d", sp))
        if r.return_code != 0:
            _add("projects.present", False,
                 f"PROJECT_PATH_{i} ({sp}) is not an accessible directory", r)
        else:
            # Env var exact value
            r_env = _exec(("printenv", f"PROJECT_PATH_{i}"))
            actual = r_env.stdout.strip() if r_env.return_code == 0 else ""
            if actual == sp:
                _add("projects.present", True,
                     f"PROJECT_PATH_{i}={sp} (dir present)", r_env)
            else:
                _add("projects.present", False,
                     f"PROJECT_PATH_{i}: expected {sp!r}, got {actual!r}", r_env)
    # Guard: no unexpected next entry
    guard_key = f"PROJECT_PATH_{len(pp) + 1}"
    r_guard = _exec(("printenv", guard_key))
    if r_guard.return_code == 0:
        _add("projects.present", False,
             f"unexpected {guard_key}={r_guard.stdout.strip()!r}", r_guard)

    # ── working.directory ────────────────────────────────────────────
    if pp:
        r = _exec(("pwd",))
        wd = r.stdout.strip() if r.return_code == 0 else ""
        expected_wd = str(pp[0])
        if wd == expected_wd:
            _add("working.directory", True,
                 f"working directory is PROJECT_PATH_1 ({wd})", r)
        else:
            _add("working.directory", False,
                 f"working directory: expected {expected_wd!r}, got {wd!r}", r)
    else:
        _add("working.directory", True,
             "no project paths — nothing to verify")

    # ── ownership.dev ────────────────────────────────────────────────
    # Pi home
    r = _exec(("stat", "-c", "%U:%G", pi_home))
    owner = r.stdout.strip() if r.return_code == 0 else ""
    if owner == "dev:dev":
        _add("ownership.dev", True, f"{pi_home} owned by dev:dev", r)
    else:
        _add("ownership.dev", False,
             f"{pi_home} owned by {owner!r}, expected dev:dev", r)
    # Project paths
    for i, p in enumerate(pp, start=1):
        sp = str(p)
        r = _exec(("stat", "-c", "%U:%G", sp))
        p_owner = r.stdout.strip() if r.return_code == 0 else ""
        if p_owner == "dev:dev":
            _add("ownership.dev", True,
                 f"PROJECT_PATH_{i} ({sp}) owned by dev:dev", r)
        else:
            _add("ownership.dev", False,
                 f"PROJECT_PATH_{i} ({sp}) owned by {p_owner!r}, expected dev:dev", r)

    # ── pi-home.setup ─────────────────────────────────────────────────
    r = _exec(("test", "-d", pi_home))
    if r.return_code != 0:
        _add("pi-home.setup", False, f"{pi_home} does not exist", r)
    else:
        rw = _exec(("test", "-w", pi_home))
        if rw.return_code == 0:
            _add("pi-home.setup", True,
                 f"{pi_home} exists and is writable", rw)
        else:
            _add("pi-home.setup", False,
                 f"{pi_home} exists but is not writable", rw)

    # ── gateway.mapping ──────────────────────────────────────────────
    r = _exec(("getent", "hosts", "host.docker.internal"))
    if r.return_code != 0:
        _add("gateway.mapping", False,
             f"host.docker.internal resolution failed", r)
    else:
        resolved = r.stdout.strip().split()[0] if r.stdout.strip() else ""
        if resolved == request.expected_gateway:
            _add("gateway.mapping", True,
                 f"host.docker.internal → {resolved}", r)
        else:
            _add("gateway.mapping", False,
                 f"host.docker.internal → {resolved!r}, expected"
                 f" {request.expected_gateway!r}", r)

    # ── forbidden.paths ──────────────────────────────────────────────
    forbidden = (
        "/run/pi-cli/docker-constructor.toml",
        "/run/pi-cli/docker-constructor.build.effective.toml",
    )
    for fp in forbidden:
        r = _exec(("test", "-f", fp))
        if r.return_code == 0:
            _add("forbidden.paths", False,
                 f"forbidden path present: {fp}", r)
        else:
            _add("forbidden.paths", True,
                 f"forbidden path absent: {fp}", r)

    # ── Assemble ─────────────────────────────────────────────────────
    all_ok = all(c.ok for c in checks) and len(errors) == 0
    return RuntimeVerificationResult(
        container=container,
        checks=tuple(checks),
        all_ok=all_ok,
        errors=tuple(errors),
    )
