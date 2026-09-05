"""Compatibility boundaries for reusable subprocess lifecycle primitives."""

from __future__ import annotations

import io
import os
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest import mock

from docker.npm_environment.lifecycle import LifecyclePolicy, reap_process, run_captured


class _Pipe(io.StringIO):
    def __init__(self, value: str = "") -> None:
        super().__init__(value)
        self.close_calls = 0

    def close(self) -> None:
        self.close_calls += 1
        super().close()


class _Process:
    def __init__(
        self,
        *,
        never_exit: bool = False,
        return_code: int = 0,
        wait_failure: BaseException | None = None,
    ) -> None:
        self.never_exit = never_exit
        self.return_code = return_code
        self.wait_failure = wait_failure
        self._wait_failed = False
        self.terminated = False
        self.killed = False
        self.stdout = _Pipe("captured stdout")
        self.stderr = _Pipe("captured stderr")

    def wait(self, timeout: float | None = None) -> int:
        if self.wait_failure is not None and not self._wait_failed:
            self._wait_failed = True
            raise self.wait_failure
        if self.never_exit and timeout is not None:
            raise subprocess.TimeoutExpired(("client",), timeout)
        return self.return_code

    def terminate(self) -> None:
        self.terminated = True

    def kill(self) -> None:
        self.killed = True


class TestLifecyclePrimitives(unittest.TestCase):
    def test_reap_closes_descriptors_for_unreapable_client(self) -> None:
        proc = _Process(never_exit=True)

        outcome = reap_process(
            proc,
            policy=LifecyclePolicy(0.01),
            pipes=(proc.stdout, proc.stderr),
        )

        self.assertTrue(proc.killed)
        self.assertEqual(proc.stdout.close_calls, 1)
        self.assertEqual(proc.stderr.close_calls, 1)
        self.assertTrue(any(isinstance(error, TimeoutError) for error in outcome.errors))

    def test_captured_runner_reuses_bounded_lifecycle_and_closes_pipes(self) -> None:
        proc = _Process(never_exit=True)
        with mock.patch("docker.npm_environment.lifecycle.subprocess.Popen", return_value=proc):
            _, outcome = run_captured(
                ("docker", "rm", "-f", "named-container"),
                policy=LifecyclePolicy(0.01, process_label="docker rm -f client"),
            )

        self.assertIsNone(outcome.return_code)
        self.assertTrue(proc.terminated)
        self.assertTrue(proc.killed)
        self.assertEqual(proc.stdout.close_calls, 1)
        self.assertEqual(proc.stderr.close_calls, 1)
        self.assertEqual(outcome.stdout, "captured stdout")
        self.assertEqual(outcome.stderr, "captured stderr")
        self.assertIn("docker rm -f client", str(outcome.errors[0]))

    def test_captured_runner_drains_large_dual_stream_output_without_timeout(self) -> None:
        # 256 KiB per stream exceeds common pipe capacities.  Sequential
        # post-exit reads would let this child block before it can exit.
        program = (
            "import os; data=b'x'*262144; "
            "os.write(1, data); os.write(2, data)"
        )
        proc, outcome = run_captured(
            (sys.executable, "-c", program),
            policy=LifecyclePolicy(2.0, captured_output_bytes=1024),
        )

        self.assertIsNotNone(proc)
        self.assertEqual(outcome.return_code, 0)
        self.assertEqual(outcome.errors, [])
        self.assertLessEqual(len(outcome.stdout.encode()), 1024)
        self.assertLessEqual(len(outcome.stderr.encode()), 1024)
        self.assertTrue(proc.stdout.closed)
        self.assertTrue(proc.stderr.closed)
        self.assertFalse(
            any(thread.name.startswith("captured-") for thread in threading.enumerate())
        )

    def test_parent_exit_with_descendant_holding_pipes_is_bounded(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            pid_path = os.path.join(directory, "descendant.pid")
            program = (
                "import subprocess, sys; "
                "child = subprocess.Popen([sys.executable, '-c', "
                "'import time; time.sleep(30)']); "
                f"open({pid_path!r}, 'w').write(str(child.pid))"
            )
            started = time.monotonic()
            proc, outcome = run_captured(
                (sys.executable, "-c", program),
                policy=LifecyclePolicy(0.1, captured_output_bytes=128),
            )
            elapsed = time.monotonic() - started
            try:
                with open(pid_path) as pid_file:
                    descendant_pid = int(pid_file.read())
                os.kill(descendant_pid, 15)
            except (FileNotFoundError, ProcessLookupError):
                pass

        self.assertIsNotNone(proc)
        self.assertEqual(outcome.return_code, 0)
        self.assertLess(elapsed, 0.5)
        self.assertTrue(proc.stdout.closed)
        self.assertTrue(proc.stderr.closed)
        self.assertLessEqual(len(outcome.stdout.encode()), 128)
        self.assertLessEqual(len(outcome.stderr.encode()), 128)
        self.assertFalse(
            any(
                thread.name in {"captured-stdout-reader", "captured-stderr-reader"}
                for thread in threading.enumerate()
            )
        )

    def test_small_grace_repeated_runs_do_not_affect_unrelated_descriptors(self) -> None:
        read_fd, write_fd = os.pipe()
        try:
            for _ in range(20):
                proc, outcome = run_captured(
                    (sys.executable, "-c", "print('ok')"),
                    policy=LifecyclePolicy(0.1, captured_output_bytes=16),
                )
                self.assertIsNotNone(proc)
                self.assertEqual(outcome.return_code, 0)
                self.assertTrue(proc.stdout.closed)
                self.assertTrue(proc.stderr.closed)
                os.write(write_fd, b"x")
                self.assertEqual(os.read(read_fd, 1), b"x")
                self.assertFalse(
                    any(
                        thread.name
                        in {"captured-stdout-reader", "captured-stderr-reader"}
                        for thread in threading.enumerate()
                    )
                )
        finally:
            os.close(read_fd)
            os.close(write_fd)

    def test_wrappers_close_once_after_descriptor_readers_stop(self) -> None:
        proc = _Process()
        with mock.patch("docker.npm_environment.lifecycle.subprocess.Popen", return_value=proc):
            _, outcome = run_captured(("client",), policy=LifecyclePolicy(0.001))

        self.assertEqual(outcome.return_code, 0)
        self.assertEqual(proc.stdout.close_calls, 1)
        self.assertEqual(proc.stderr.close_calls, 1)
        self.assertFalse(
            any(thread.name.startswith("captured-") for thread in threading.enumerate())
        )

    def test_unexpected_wait_failure_is_primary_and_still_reaps(self) -> None:
        wait_error = RuntimeError("unexpected wait failure")
        proc = _Process(wait_failure=wait_error)
        with mock.patch("docker.npm_environment.lifecycle.subprocess.Popen", return_value=proc):
            _, outcome = run_captured(
                ("client",), policy=LifecyclePolicy(0.01)
            )

        self.assertIs(outcome.errors[0], wait_error)
        self.assertTrue(proc.terminated)
        self.assertTrue(proc.stdout.closed)
        self.assertTrue(proc.stderr.closed)
        self.assertFalse(
            any(thread.name.startswith("captured-") for thread in threading.enumerate())
        )


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
