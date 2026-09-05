"""Docker execution boundary for the locked npm assembler.

``assemble`` is the effectful assembly operation: it rechecks the validated
input and assembler bindings before any filesystem effect, prepares an
owner-private staging workspace, writes the read-only lockfile input, renders
the deterministic run vector (including any resolved credential-free
corporate proxy/trust policy), and runs it through an injected executor.  A
nonzero container exit becomes a structured :class:`LockedNpmError` with
redacted stdout/stderr.  Every ``BaseException`` path — interruption,
executor failure, or npm failure — force-removes the container and removes
the staging workspace while preserving any prior committed environments.

Configured proxy endpoints and trust paths are never persisted: the
successful :class:`AssemblyRun` stores only redacted vector/argv/log copies,
and every failure detail is redacted before it is raised or attached.
"""

from __future__ import annotations

import dataclasses
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import IO, Protocol, Sequence

from .assembler import EXIT_NODE_VERSION_MISMATCH, EXIT_NPM_VERSION_MISMATCH
from .errors import LockedNpmError
from .identity import AssemblerIdentity, compute_assembler_input_identity
from .model import ValidatedAssemblyInput
from .network import CorporateNetworkPolicy
from .run_vector import (
    DockerRunVector,
    Mount,
    recheck_assembler_bindings,
    render_docker_argv,
    render_run_vector,
)
from .storage import (
    AssemblerNamespace,
    prepare_assembler_namespace,
    prepare_staging_workspace,
    remove_staging_workspace,
)
from .streaming import (
    READER_FAILURE_DETAIL_BYTES,
    REDACTED,
    DiagnosticSink,
    STREAM_STDERR,
    STREAM_STDOUT,
    StreamingCapture,
    collect_streams,
    redact_tail,
    redact_text,
)

#: Control-flow exceptions that must propagate unchanged from the executor
#: boundary (never converted into a structured assembler failure).
_CONTROL_FLOW_EXCEPTIONS = (KeyboardInterrupt, SystemExit, GeneratorExit)


def redact(text: str, secrets: Sequence[str]) -> str:
    """Replace every non-empty *secret* in *text* with ``<redacted>``.

    Deterministic and caller-order-independent: at the leftmost position
    where any secret matches, the longest complete match is replaced with
    exactly one marker.
    """
    return redact_text(text, secrets)


def redact_docker_argv(
    argv: Sequence[str], secrets: Sequence[str]
) -> tuple[str, ...]:
    """Return a display-safe copy of *argv* with every secret redacted."""
    return tuple(redact(token, secrets) for token in argv)


def redact_run_vector(
    vector: DockerRunVector, secrets: Sequence[str]
) -> DockerRunVector:
    """Return a display-safe copy of *vector* with every secret redacted."""
    env = tuple((key, redact(value, secrets)) for key, value in vector.env)
    mounts = tuple(
        Mount(redact(mount.host, secrets), mount.container, mount.mode)
        for mount in vector.mounts
    )
    return dataclasses.replace(vector, env=env, mounts=mounts)


@dataclass(frozen=True)
class ProcessResult:
    """Captured subprocess outcome."""

    argv: tuple[str, ...]
    return_code: int
    stdout: str = ""
    stderr: str = ""
    truncation_notice: str | None = None
    """Fixed redacted notice when live output was not fully delivered."""


class RunExecutor(Protocol):
    """Injected execution boundary for a rendered ``docker`` argument list."""

    def run(self, argv: tuple[str, ...]) -> ProcessResult:
        """Execute *argv* and return the captured result."""
        ...


def _default_container_user(
    uid: int | None, gid: int | None
) -> tuple[int, int]:
    """Return the invoking process UID/GID for unspecified identities."""
    return (os.getuid() if uid is None else uid, os.getgid() if gid is None else gid)


def _is_rootless_docker() -> bool:
    """Return whether ``docker info`` reports a rootless daemon.

    A missing ``docker`` binary or an unavailable daemon is treated as
    not-rootless; the subsequent ``docker run`` surfaces the real error
    with an actionable message.
    """
    try:
        proc = subprocess.run(
            ["docker", "info"], capture_output=True, text=True, check=False
        )
    except OSError:
        return False
    return proc.returncode == 0 and "rootless" in proc.stdout.lower()


def _resolve_container_user(
    executor: RunExecutor, uid: int | None, gid: int | None
) -> tuple[int, int]:
    """Resolve the numeric container identity for one assembler run.

    Explicit *uid*/*gid* values win.  A real :class:`DockerRunExecutor`
    resolves rootless Docker to container ``0:0`` (the invoking host user
    under rootless user namespaces); in-memory test executors that omit the
    optional ``resolve_user`` hook fall back to the invoking process UID/GID.
    """
    resolver = getattr(executor, "resolve_user", None)
    if resolver is not None:
        return resolver(uid, gid)
    return _default_container_user(uid, gid)


def _terminate_and_reap(proc: subprocess.Popen) -> None:
    """Terminate and reap a local docker client left writing to a failed pipe."""
    try:
        proc.terminate()
    except OSError:
        pass
    try:
        proc.wait(timeout=5.0)
    except subprocess.TimeoutExpired:
        try:
            proc.kill()
        except OSError:
            pass
        proc.wait()


def _close_stream_pipes(pipes: Sequence[IO[bytes]]) -> list[Exception]:
    """Close every pipe independently, returning any close failures.

    Each pipe is closed in its own try/except so one close failure cannot
    skip another pipe's close; failures are collected, never raised here, so
    the caller can guarantee downstream cleanup (process reaping) first.
    """
    close_errors: list[Exception] = []
    for pipe in pipes:
        try:
            pipe.close()
        except Exception as exc:
            close_errors.append(exc)
    return close_errors


def _render_close_failure(exc: Exception, secrets: Sequence[str]) -> str:
    """Render a close failure as a bounded, redacted message."""
    return redact_tail(
        str(exc) or repr(exc),
        secrets,
        tail_bytes=READER_FAILURE_DETAIL_BYTES,
    )


def _attach_close_failure_notes(
    target: BaseException,
    close_errors: Sequence[Exception],
    secrets: Sequence[str],
) -> None:
    """Attach bounded, redacted close failures to *target* as notes."""
    for exc in close_errors:
        target.add_note(
            f"pipe close failed ({type(exc).__name__}): "
            f"{_render_close_failure(exc, secrets)}"
        )


def _raise_close_failures(
    close_errors: Sequence[Exception], secrets: Sequence[str]
) -> None:
    """Raise the first close failure, redacted; note any further ones."""
    primary = close_errors[0]
    message = _render_close_failure(primary, secrets)
    try:
        raised: Exception = type(primary)(message)
    except Exception:
        raised = RuntimeError(message)
    for exc in close_errors[1:]:
        raised.add_note(
            f"also ({type(exc).__name__}): {_render_close_failure(exc, secrets)}"
        )
    raise raised


class DockerRunExecutor:
    """Real executor backed by the ``docker`` binary on ``PATH``."""

    def run(self, argv: tuple[str, ...]) -> ProcessResult:
        proc = subprocess.run(argv, capture_output=True, text=True)
        return ProcessResult(argv, proc.returncode, proc.stdout, proc.stderr)

    def run_streaming(
        self,
        argv: tuple[str, ...],
        *,
        secrets: Sequence[str] = (),
        sink: DiagnosticSink | None = None,
    ) -> ProcessResult:
        """Run *argv*, draining stdout/stderr concurrently with redaction.

        Both pipes are drained without waiting for newlines; safe redacted
        prefixes reach *sink* (when provided) before process exit; retained
        stdout/stderr are bounded redacted tails.  A pipe-reader failure is
        reported immediately: the failed pipe is closed and the local docker
        client is terminated and reaped, which lets the sibling reader reach
        EOF and drain its remaining data; both readers are then joined and
        the sink dispatcher finalized before :class:`StreamReaderFailure` is
        raised.  The named daemon-side container stays owned by ``assemble``'s
        cleanup.
        """
        proc = subprocess.Popen(
            argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE
        )
        assert proc.stdout is not None and proc.stderr is not None
        stdout_pipe = proc.stdout
        stderr_pipe = proc.stderr

        def react_to_reader_failure(failed_stream: str) -> None:
            # Attempt every cleanup step independently so a failure in one
            # (e.g. closing the failed pipe) cannot skip the others (e.g.
            # terminating the client, which unblocks the sibling reader).
            # Collected errors are re-raised so collect_streams records them
            # as secondary context without masking the reader failure; the
            # run_streaming finally block still guarantees both pipes close.
            failed_pipe = (
                stdout_pipe if failed_stream == STREAM_STDOUT else stderr_pipe
            )
            cleanup_errors: list[Exception] = []
            try:
                failed_pipe.close()
            except Exception as exc:
                cleanup_errors.append(exc)
            try:
                _terminate_and_reap(proc)
            except Exception as exc:
                cleanup_errors.append(exc)
            if cleanup_errors:
                primary = cleanup_errors[0]
                for extra in cleanup_errors[1:]:
                    primary.add_note(
                        f"also ({type(extra).__name__}): "
                        f"{str(extra) or repr(extra)}"
                    )
                raise primary

        try:
            capture: StreamingCapture = collect_streams(
                stdout_read=stdout_pipe.read,
                stderr_read=stderr_pipe.read,
                secrets=secrets,
                sink=sink,
                on_reader_failure=react_to_reader_failure,
            )
        except BaseException as exc:
            # Close both pipes without letting a close failure replace the
            # in-flight exception; close failures become bounded, redacted
            # secondary notes on it.  The reader-failure callback already
            # terminated and reaped the client in this path.
            _attach_close_failure_notes(
                exc, _close_stream_pipes((stdout_pipe, stderr_pipe)), secrets
            )
            raise

        # Normal path: capture (do not raise) close failures so the
        # subprocess is always reaped before any deferred cleanup failure
        # surfaces.
        close_errors = _close_stream_pipes((stdout_pipe, stderr_pipe))
        try:
            return_code = proc.wait()
        except BaseException as wait_exc:
            # A reaping failure is primary; close failures are secondary.
            _attach_close_failure_notes(wait_exc, close_errors, secrets)
            raise
        if close_errors:
            _raise_close_failures(close_errors, secrets)
        return ProcessResult(
            argv,
            return_code,
            capture.stdout_tail,
            capture.stderr_tail,
            truncation_notice=capture.truncation_notice,
        )

    def resolve_user(self, uid: int | None, gid: int | None) -> tuple[int, int]:
        """Resolve the numeric container identity for the invoking host user.

        Explicit *uid*/*gid* win.  When both are unspecified and the Docker
        daemon is rootless, the invoking host user maps to container
        UID/GID ``0``, so ``0:0`` is returned to keep the owner-private host
        bind mounts writable; otherwise the invoking process UID/GID.
        """
        if uid is not None and gid is not None:
            return uid, gid
        if uid is None and gid is None and _is_rootless_docker():
            return 0, 0
        return _default_container_user(uid, gid)


@dataclass(frozen=True)
class AssemblyRun:
    """Structured result of one successful assembler container execution.

    The stored vector, argv, stdout, and stderr are redacted copies: every
    configured proxy endpoint and trust path (plus any caller-supplied
    secret) is replaced with ``<redacted>``.  The exact executable argv is
    never persisted in the result.
    """

    run_vector: DockerRunVector
    """Redacted run vector actually executed (secrets replaced)."""

    argv: tuple[str, ...]
    """Redacted ``docker run`` argument list executed (secrets replaced)."""

    staging: Path
    """The populated staging workspace (retained for later validation)."""

    stdout: str
    """Redacted container stdout."""

    stderr: str
    """Redacted container stderr (bounded diagnostic tail)."""

    truncation_notice: str | None = None
    """Fixed redacted notice when live output was not fully delivered."""


@dataclass(frozen=True)
class CleanupFailure:
    """Structured record of one cleanup operation that failed.

    Cleanup failures never replace the primary assembly exception; they are
    attached to it as notes so the original failure stays identifiable and
    every cleanup failure stays observable.
    """

    operation: str
    """``"container"`` or ``"staging"``."""

    reason: str
    """Machine-readable reason (``docker_rm_nonzero``,
    ``docker_rm_exception``, or the underlying staging error reason)."""

    detail: str
    """Redacted human-readable detail, including the staging path when
    mutable residue may remain."""


def _exit_failure(
    return_code: int,
    *,
    stderr: str,
    stdout: str,
    truncation_notice: str | None = None,
) -> LockedNpmError:
    """Build a structured nonzero-exit failure from already-redacted output."""
    if return_code == EXIT_NODE_VERSION_MISMATCH:
        reason = "node_version_mismatch"
    elif return_code == EXIT_NPM_VERSION_MISMATCH:
        reason = "npm_version_mismatch"
    else:
        reason = "npm_exit_nonzero"

    stderr = stderr.strip()
    stdout = stdout.strip()
    detail = f"assembler exited {return_code}"
    if stderr:
        detail += f": {stderr}"
    elif stdout:
        detail += f": {stdout}"
    if truncation_notice:
        detail += f" {truncation_notice}"
    return LockedNpmError(reason, detail)


def _write_lockfile(staging: Path, lockfile_bytes: bytes) -> None:
    """Write the exact lockfile bytes into the private staging workspace.

    The file is created ``0444`` with ``O_NOFOLLOW | O_EXCL`` so a symlink or
    pre-existing entry is never followed or overwritten.
    """
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    path = staging / "package-lock.json"
    try:
        fd = os.open(str(path), flags, 0o444)
    except OSError as exc:
        raise LockedNpmError(
            "unsafe_staging_path",
            f"cannot write lockfile input {path}: {exc}",
        ) from exc
    try:
        os.write(fd, lockfile_bytes)
    finally:
        os.close(fd)


def _cleanup_container(
    executor: RunExecutor, name: str, secrets: Sequence[str]
) -> CleanupFailure | None:
    """Force-remove the assembler container and return any cleanup failure.

    Returns ``None`` when removal succeeds.  A nonzero exit or a raised
    exception (including cancellation during cleanup) is reported as a
    structured :class:`CleanupFailure` rather than being swallowed.
    """
    try:
        result = executor.run(("docker", "rm", "-f", name))
    except BaseException as exc:
        return CleanupFailure(
            operation="container",
            reason="docker_rm_exception",
            detail=redact(f"{type(exc).__name__}: {exc}", secrets),
        )
    if result.return_code != 0:
        detail = (
            redact(result.stderr, secrets).strip()
            or redact(result.stdout, secrets).strip()
            or f"exit {result.return_code}"
        )
        return CleanupFailure(
            operation="container",
            reason="docker_rm_nonzero",
            detail=f"container cleanup failed (exit {result.return_code}): {detail}",
        )
    return None


def _remove_staging_safely(
    namespace: AssemblerNamespace,
    name: str,
    staging_path: Path,
    secrets: Sequence[str],
) -> CleanupFailure | None:
    """Remove one staging workspace and return any cleanup failure.

    Returns ``None`` on success.  Any raised failure (including
    cancellation during cleanup) is reported as a structured
    :class:`CleanupFailure` naming the staging path and noting that mutable
    residue may remain.  Prior committed environments are never touched.
    """
    try:
        remove_staging_workspace(namespace, name)
        return None
    except BaseException as exc:
        if isinstance(exc, LockedNpmError):
            reason = exc.reason
            detail = redact(exc.detail, secrets)
        else:
            reason = type(exc).__name__
            detail = redact(str(exc) or repr(exc), secrets)
        return CleanupFailure(
            operation="staging",
            reason=reason,
            detail=f"mutable staging residue may remain at {staging_path}: {detail}",
        )


def _attach_cleanup_notes(
    exc: BaseException, failures: Sequence[CleanupFailure]
) -> None:
    """Attach every cleanup failure as a note on the primary exception."""
    for failure in failures:
        exc.add_note(
            f"cleanup failure ({failure.operation}): "
            f"{failure.reason}: {failure.detail}"
        )


def assemble(
    *,
    validated: ValidatedAssemblyInput,
    assembler: AssemblerIdentity,
    cache_root: str | Path,
    executor: RunExecutor,
    uid: int | None = None,
    gid: int | None = None,
    secrets: Sequence[str] = (),
    corporate_network: CorporateNetworkPolicy | None = None,
    sink: DiagnosticSink | None = None,
) -> AssemblyRun:
    """Run one standalone pinned assembler container.

    Rejects a mutable or malformed image reference, changed lock bytes,
    roots, platform, reviewed tool versions, or script/policy digests before
    any effect.  On success the populated staging workspace is returned; on
    any failure the container is force-removed and the staging workspace is
    removed, and any cleanup failure is attached as a note on the original
    error before it is re-raised.

    *corporate_network* carries the caller-resolved credential-free proxy
    and corporate trust policy.  Its values are automatically added to the
    redaction secrets, so the successful result and every raised or attached
    failure are free of the configured proxy endpoint and trust path.

    *sink* is an optional constructor-owned prompt-returning diagnostic
    callback.  Executors that support streaming deliver redacted output to
    it before process exit; an absent *sink* produces no live output and
    only bounded diagnostics are retained.
    """
    recheck_assembler_bindings(assembler)
    input_identity = compute_assembler_input_identity(validated, assembler)

    policy_secrets = (
        corporate_network.secrets() if corporate_network is not None else ()
    )
    effective_secrets = tuple(secrets) + policy_secrets

    uid, gid = _resolve_container_user(executor, uid, gid)

    namespace = prepare_assembler_namespace(cache_root, assembler.digest)
    staging_name = input_identity.digest
    container_name = f"npm-assembler-{input_identity.digest[:16]}"

    staging: Path | None = None
    container_started = False
    try:
        staging = prepare_staging_workspace(namespace, staging_name)
        _write_lockfile(staging, validated.lockfile_bytes)
        vector = render_run_vector(
            validated=validated,
            assembler=assembler,
            staging=staging,
            npm_cache=namespace.npm_cache,
            uid=uid,
            gid=gid,
            name=container_name,
            corporate_network=corporate_network,
        )
        argv = render_docker_argv(vector)
        container_started = True
        executor_failure_detail: str | None = None
        truncation_notice: str | None = None
        streaming_runner = getattr(executor, "run_streaming", None)
        try:
            if streaming_runner is not None:
                result = streaming_runner(
                    argv, secrets=effective_secrets, sink=sink
                )
                stdout = result.stdout
                stderr = result.stderr
                truncation_notice = getattr(result, "truncation_notice", None)
            else:
                result = executor.run(argv)
                stdout = redact_tail(result.stdout, effective_secrets)
                stderr = redact_tail(result.stderr, effective_secrets)
        except _CONTROL_FLOW_EXCEPTIONS:
            raise
        except BaseException as exc:
            # Capture only the sanitized detail here.  The structured error
            # is raised after leaving the except block so Python does not
            # assign the original exception to __context__.
            executor_failure_detail = redact(
                f"{type(exc).__name__}: {str(exc) or repr(exc)}",
                effective_secrets,
            )

        if executor_failure_detail is not None:
            raise LockedNpmError(
                "executor_failure",
                executor_failure_detail,
            ) from None
        if result.return_code != 0:
            raise _exit_failure(
                result.return_code,
                stderr=stderr,
                stdout=stdout,
                truncation_notice=truncation_notice,
            )
        return AssemblyRun(
            run_vector=redact_run_vector(vector, effective_secrets),
            argv=redact_docker_argv(argv, effective_secrets),
            staging=staging,
            stdout=stdout,
            stderr=stderr,
            truncation_notice=truncation_notice,
        )
    except BaseException as exc:
        failures: list[CleanupFailure] = []
        if container_started:
            container_failure = _cleanup_container(
                executor, container_name, effective_secrets
            )
            if container_failure is not None:
                failures.append(container_failure)
        if staging is not None:
            staging_failure = _remove_staging_safely(
                namespace, staging_name, staging, effective_secrets
            )
            if staging_failure is not None:
                failures.append(staging_failure)
        _attach_cleanup_notes(exc, failures)
        raise
