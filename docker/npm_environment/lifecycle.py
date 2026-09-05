"""Domain-neutral bounded subprocess lifecycle primitives.

This module deliberately has no Docker, streaming, redaction, or assembler-error
knowledge.  Callers supply process and descriptor policy, then map the returned
outcome into their domain-specific cleanup and error reporting rules.
"""

from __future__ import annotations

import os
import select
import subprocess
import threading
import time
from dataclasses import dataclass, field
from typing import IO, Callable, Sequence

_CAPTURE_READ_BYTES = 16 * 1024
_CAPTURE_TAIL_BYTES = 64 * 1024


@dataclass(frozen=True)
class LifecyclePolicy:
    """Finite grace period applied to every terminate/reap lifecycle step."""

    grace_seconds: float
    process_label: str = "client"
    captured_output_bytes: int = _CAPTURE_TAIL_BYTES


@dataclass
class LifecycleOutcome:
    """Result of bounded process finalization without exception precedence."""

    return_code: int | None = None
    errors: list[BaseException] = field(default_factory=list)
    stdout: str = ""
    stderr: str = ""


@dataclass
class DeadlineOutcome:
    """Thread-safe publication state for one domain-neutral deadline."""

    fired: bool = False
    cleanup_started: bool = False
    wait_failure: BaseException | None = None
    cleanup_errors: list[BaseException] = field(default_factory=list)
    close_errors: list[BaseException] = field(default_factory=list)


class DeadlineSupervisor:
    """Reusable monotonic polling supervisor with atomic cleanup ownership.

    ``poll`` returns true once its child has exited.  ``cleanup`` is a domain
    hook that returns cleanup and descriptor errors; the supervisor itself
    has no Docker, streaming, redaction, or exception-mapping knowledge.
    """

    def __init__(
        self,
        *,
        deadline_seconds: float,
        poll: Callable[[], bool],
        cleanup: Callable[[], tuple[list[BaseException], list[BaseException]]],
        poll_seconds: float = 0.1,
        thread_name: str = "deadline-supervisor",
    ) -> None:
        self._deadline_seconds = deadline_seconds
        self._poll = poll
        self._cleanup = cleanup
        self._poll_seconds = poll_seconds
        self._cancel = threading.Event()
        self._lock = threading.Lock()
        self._deadline_at: float | None = None
        self.outcome = DeadlineOutcome()
        self.thread = threading.Thread(
            target=self._run, name=thread_name, daemon=True
        )

    def start(self) -> None:
        # Capture the deadline before scheduling the worker so thread-start
        # contention cannot extend the configured execution duration.
        self._deadline_at = time.monotonic() + self._deadline_seconds
        self.thread.start()

    def cancel(self) -> None:
        self._cancel.set()

    def claim_interruption(self) -> bool:
        """Cancel polling unless deadline cleanup already owns the process."""
        with self._lock:
            if self.outcome.cleanup_started:
                return True
            self._cancel.set()
            return False

    def snapshot(self) -> DeadlineOutcome:
        with self._lock:
            return DeadlineOutcome(
                fired=self.outcome.fired,
                cleanup_started=self.outcome.cleanup_started,
                wait_failure=self.outcome.wait_failure,
                cleanup_errors=list(self.outcome.cleanup_errors),
                close_errors=list(self.outcome.close_errors),
            )

    def join(self, timeout: float, *, cancel: bool = False) -> bool:
        if cancel:
            self.cancel()
        self.thread.join(timeout=timeout)
        return not self.thread.is_alive()

    def _run(self) -> None:
        # ``start`` sets this before the thread is scheduled.
        assert self._deadline_at is not None
        deadline_at = self._deadline_at
        wait_failure: BaseException | None = None
        while not self._cancel.is_set():
            try:
                if self._poll():
                    return
            except BaseException as exc:
                wait_failure = exc
                break
            remaining = max(0.0, deadline_at - time.monotonic())
            if remaining == 0.0:
                break
            # Polling must not delay deadline enforcement: cancellation waits
            # are capped by the remaining monotonic deadline.
            self._cancel.wait(timeout=min(self._poll_seconds, remaining))
        else:
            return
        with self._lock:
            # Preserve an unexpected poll failure even when interruption won
            # cleanup ownership in the narrow interval before publication.
            self.outcome.wait_failure = wait_failure
            if self._cancel.is_set():
                return
            self.outcome.cleanup_started = True
        try:
            cleanup_errors, close_errors = self._cleanup()
        except BaseException as exc:
            # A domain cleanup hook must not crash the supervisor and silently
            # lose its outcome; callers retain the hook failure as context.
            cleanup_errors, close_errors = [exc], []
        with self._lock:
            if wait_failure is None:
                self.outcome.fired = True
            self.outcome.cleanup_errors.extend(cleanup_errors)
            self.outcome.close_errors.extend(close_errors)


def close_descriptors(
    pipes: Sequence[IO[str] | IO[bytes] | None],
) -> list[BaseException]:
    """Close every descriptor independently and return all close failures."""
    errors: list[BaseException] = []
    for pipe in pipes:
        if pipe is None:
            continue
        try:
            pipe.close()
        except BaseException as exc:
            errors.append(exc)
    return errors


def reap_process(
    proc: subprocess.Popen,
    *,
    policy: LifecyclePolicy,
    pipes: Sequence[IO[str] | IO[bytes] | None] = (),
) -> LifecycleOutcome:
    """Boundedly reap, kill, final-reap, and close *pipes*.

    Callers that need domain-specific work between termination and reaping can
    terminate first and use this primitive.  A process surviving the final
    bounded wait is represented by a ``TimeoutError`` instead of blocking.
    """
    outcome = LifecycleOutcome()
    try:
        try:
            outcome.return_code = proc.wait(timeout=policy.grace_seconds)
        except subprocess.TimeoutExpired:
            try:
                proc.kill()
            except OSError as exc:
                outcome.errors.append(exc)
            try:
                outcome.return_code = proc.wait(timeout=policy.grace_seconds)
            except subprocess.TimeoutExpired:
                outcome.errors.append(
                    TimeoutError(
                        f"{policy.process_label} did not exit after SIGKILL within "
                        f"{policy.grace_seconds:g}s"
                    )
                )
            except BaseException as exc:
                outcome.errors.append(exc)
        except BaseException as exc:
            outcome.errors.append(exc)
    finally:
        outcome.errors.extend(close_descriptors(pipes))
    return outcome


def terminate_and_reap(
    proc: subprocess.Popen,
    *,
    policy: LifecyclePolicy,
    pipes: Sequence[IO[str] | IO[bytes] | None] = (),
) -> LifecycleOutcome:
    """Terminate then delegate bounded reaping and closure to one primitive."""
    errors: list[BaseException] = []
    try:
        proc.terminate()
    except OSError as exc:
        errors.append(exc)
    outcome = reap_process(proc, policy=policy, pipes=pipes)
    outcome.errors[:0] = errors
    return outcome


def run_captured(
    argv: Sequence[str],
    *,
    policy: LifecyclePolicy,
) -> tuple[subprocess.Popen | None, LifecycleOutcome]:
    """Run a captured client while draining both pipes concurrently.

    Draining begins before waiting for process exit, avoiding the pipe-capacity
    deadlock that a post-exit ``read()`` can create.  Each stream retains only
    its configured byte tail.  Lifecycle errors retain their ordering: an
    unexpected initial ``wait`` failure is primary, followed by cleanup,
    reader, and descriptor failures.
    """
    try:
        proc = subprocess.Popen(
            argv,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
    except BaseException as exc:
        return None, LifecycleOutcome(errors=[exc])

    tails: dict[str, bytearray] = {"stdout": bytearray(), "stderr": bytearray()}
    reader_errors: list[BaseException] = []
    stop_readers = threading.Event()
    pipes = (("stdout", proc.stdout), ("stderr", proc.stderr))
    raw_fds: dict[str, int] = {}
    for name, pipe in pipes:
        if pipe is None:
            continue
        try:
            fd = pipe.fileno()
            os.set_blocking(fd, False)
            raw_fds[name] = fd
        except (AttributeError, OSError):
            # In-memory injected test pipes have no descriptor.  Production
            # Popen pipes always use the non-blocking descriptor path below.
            pass

    def retain(name: str, data: bytes) -> None:
        tail = tails[name]
        tail.extend(data)
        if len(tail) > policy.captured_output_bytes:
            del tail[: len(tail) - policy.captured_output_bytes]

    poll_seconds = max(0.001, min(0.05, policy.grace_seconds))

    def drain(name: str, pipe: IO[bytes] | IO[str] | None) -> None:
        if pipe is None:
            return
        fd = raw_fds.get(name)
        try:
            if fd is None:
                # Compatibility seam for descriptor-less in-memory pipes.
                while not stop_readers.is_set():
                    chunk = pipe.read(_CAPTURE_READ_BYTES)
                    if not chunk:
                        return
                    retain(name, chunk.encode() if isinstance(chunk, str) else chunk)
            else:
                while True:
                    if stop_readers.is_set():
                        return
                    ready, _, _ = select.select((fd,), (), (), poll_seconds)
                    if not ready or stop_readers.is_set():
                        continue
                    try:
                        chunk = os.read(fd, _CAPTURE_READ_BYTES)
                    except BlockingIOError:
                        continue
                    except OSError as exc:
                        if stop_readers.is_set():
                            return
                        raise exc
                    if not chunk:
                        return
                    retain(name, chunk)
        except BaseException as exc:
            reader_errors.append(exc)

    readers = [
        threading.Thread(
            target=drain,
            args=(name, pipe),
            name=f"captured-{name}-reader",
            daemon=True,
        )
        for name, pipe in pipes
    ]
    for reader in readers:
        reader.start()

    outcome = LifecycleOutcome()
    allow_drain = False
    try:
        try:
            outcome.return_code = proc.wait(timeout=policy.grace_seconds)
            allow_drain = True
        except subprocess.TimeoutExpired:
            cleanup = terminate_and_reap(proc, policy=policy)
            outcome.return_code = cleanup.return_code
            outcome.errors.extend(cleanup.errors)
        except BaseException as exc:
            # Preserve the poll/wait failure as primary, but do not leave a
            # still-live child or readers behind merely because waiting failed.
            outcome.errors.append(exc)
            cleanup = terminate_and_reap(proc, policy=policy)
            outcome.return_code = cleanup.return_code
            outcome.errors.extend(cleanup.errors)
    finally:
        # A normally exited child may still have drainable output.  Bound that
        # drain because a descendant can inherit and keep either pipe open.
        if allow_drain:
            drain_deadline = time.monotonic() + policy.grace_seconds
            for reader in readers:
                reader.join(timeout=max(0.0, drain_deadline - time.monotonic()))
        stop_readers.set()
        # Never close raw fds independently of their wrappers: descriptor
        # numbers can be reused while a worker still observes the old number.
        # Descriptor workers see the stop event within ``poll_seconds``.
        join_deadline = time.monotonic() + policy.grace_seconds
        for reader in readers:
            if reader.is_alive():
                reader.join(timeout=max(0.0, join_deadline - time.monotonic()))
            if reader.is_alive():
                outcome.errors.append(
                    TimeoutError(
                        f"{reader.name} did not stop within "
                        f"{policy.grace_seconds:g}s"
                    )
                )
        if not any(reader.is_alive() for reader in readers):
            # Buffered wrappers are only closed after their readers released
            # them, avoiding cross-thread buffer-lock and fd-reuse hazards.
            outcome.errors.extend(close_descriptors((proc.stdout, proc.stderr)))
        # A descriptor-less injected reader that ignores shutdown is daemonized
        # so it cannot keep Python alive; it remains an explicit degraded path.
        outcome.errors.extend(reader_errors)
        outcome.stdout = bytes(tails["stdout"]).decode(errors="replace")
        outcome.stderr = bytes(tails["stderr"]).decode(errors="replace")
    return proc, outcome
