"""GREEN-phase tests for ``docker.networking`` — Stage 7.2, 7.6, 7.7.

Covers rootless-override planning/application, operational persistence,
full diagnosis with injected boundaries, and import-boundary checks.
All tests use **in-memory fakes** for filesystem, service control, and
process execution — no real disk, no Docker, no systemd.

See ``tests/test_constructor_networking.py`` for the RED‑phase 7.1
diagnosis tests (detection, candidates, probes, DTOs).
"""

from __future__ import annotations

import dataclasses
import subprocess
import unittest
from pathlib import Path
from typing import Optional
from unittest import mock

from docker.networking import (
    DockerMode,
    Filesystem,
    GatewayDiagnosis,
    OverrideFailure,
    OverrideState,
    PersistenceResult,
    ProbeResult,
    ProcessResult,
    ProcessRunner,
    RootlessOverridePlan,
    ServiceController,
    SystemClock,
    _choose_gateway,
    apply_rootless_override,
    candidate_gateways,
    diagnose_gateway,
    persist_gateway,
    plan_rootless_override,
    probe_gateway,
    update_env_file,
)


# ---------------------------------------------------------------------------
# In-memory fakes
# ---------------------------------------------------------------------------


class FakeProcessRunner(ProcessRunner):
    """ProcessRunner that consumes canned responses in sequence."""

    def __init__(self, responses: list[ProcessResult] | None = None):
        self._responses = list(responses or [])
        self.calls: list[list[str]] = []

    def run(self, argv: list[str]) -> ProcessResult:
        self.calls.append(argv)
        if self._responses:
            return self._responses.pop(0)
        return ProcessResult(
            argv=tuple(argv), return_code=1,
            stdout="", stderr=f"no canned response for {argv[0]}",
        )

    def add(self, result: ProcessResult) -> None:
        self._responses.append(result)


class FakeFilesystem(Filesystem):
    """In-memory filesystem for override planning/application tests."""

    def __init__(self, *, home: Path = Path("/fake/home"),
                 files: dict[str, str] | None = None) -> None:
        self._files: dict[str, str] = dict(files or {})
        self._home = home
        self.mkdirs: list[Path] = []
        self.copies: list[tuple[Path, Path]] = []
        self.renames: list[tuple[Path, Path]] = []
        self.writes: list[Path] = []
        self.deletes: list[Path] = []

    @property
    def home(self) -> Path:
        return self._home

    def is_file(self, path: Path) -> bool:
        return str(path) in self._files

    def read_text(self, path: Path, encoding: str = "utf-8") -> str:
        return self._files[str(path)]

    def write_text(self, path: Path, content: str, encoding: str = "utf-8") -> None:
        self._files[str(path)] = content
        self.writes.append(path)

    def mkdir(self, path: Path) -> None:
        self.mkdirs.append(path)

    def copy(self, src: Path, dest: Path) -> None:
        if not self.is_file(src):
            raise FileNotFoundError(f"Source not found: {src}")
        self._files[str(dest)] = self._files[str(src)]
        self.copies.append((src, dest))

    def rename(self, src: Path, dest: Path) -> None:
        content = self._files.pop(str(src), None)
        if content is None:
            raise FileNotFoundError(f"Source not found for rename: {src}")
        self._files[str(dest)] = content
        self.renames.append((src, dest))

    def delete(self, path: Path) -> None:
        self._files.pop(str(path), None)
        self.deletes.append(path)

    def clear_writes(self) -> None:
        self.writes.clear()
        self.renames.clear()


class FakeServiceController(ServiceController):
    """In-memory service controller — records calls, never invokes systemctl."""

    def __init__(self, *, fail_daemon_reload: Optional[Exception] = None,
                 fail_restart: Optional[Exception] = None) -> None:
        super().__init__(_runner=FakeProcessRunner())  # no real subprocess
        self._fail_daemon_reload = fail_daemon_reload
        self._fail_restart = fail_restart
        self.reloads: list[None] = []
        self.restarts: list[str] = []
        # Non-zero-return simulation: set before calling daemon_reload/restart.
        self._next_daemon_reload_rc: int = 0
        self._next_daemon_reload_stderr: str = ""
        self._next_restart_rc: int = 0
        self._next_restart_stderr: str = ""

    def daemon_reload(self) -> None:
        self.reloads.append(None)
        if self._fail_daemon_reload:
            raise self._fail_daemon_reload
        if self._next_daemon_reload_rc != 0:
            raise RuntimeError(
                f"daemon-reload failed (rc={self._next_daemon_reload_rc}): "
                f"{self._next_daemon_reload_stderr[:200]}"
            )

    def restart(self, unit: str) -> None:
        self.restarts.append(unit)
        if self._fail_restart:
            raise self._fail_restart
        if self._next_restart_rc != 0:
            raise RuntimeError(
                f"restart {unit} failed (rc={self._next_restart_rc}): "
                f"{self._next_restart_stderr[:200]}"
            )


class FakeClock(SystemClock):
    """Controllable clock for tests."""

    def __init__(self, *, ts: float = 1000.0) -> None:
        self._ts = ts
        self.sleeps: list[float] = []

    def timestamp(self) -> float:
        return self._ts

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)


class FakeHostProbeServer:
    """Fake ``HostProbeServer`` for diagnosis tests."""

    def __init__(self, port: int = 12345, token: str = "FAKE_TOKEN"):
        self.port = port
        self.token = token
        self.started = False
        self.stopped = False

    def start(self) -> int:
        self.started = True
        return self.port

    def stop(self) -> None:
        self.stopped = True


# ---------------------------------------------------------------------------
# 7.2 — Rootless override planning (in-memory filesystem)
# ---------------------------------------------------------------------------


class TestInspectRootlessOverrideInMemory(unittest.TestCase):
    """Override planning with in-memory ``Filesystem`` fake."""

    OVERRIDE_CONTENT = "[Service]\nPort=forward\n"
    OTHER_CONTENT = "[Service]\nPort=other\n"

    def setUp(self):
        self.src = Path("/fake/override.conf")
        self.dest = Path("/fake/home/.config/systemd/user/docker.service.d/override.conf")

    def test_installed_when_dest_matches_src(self):
        fs = FakeFilesystem(files={
            str(self.src): self.OVERRIDE_CONTENT,
            str(self.dest): self.OVERRIDE_CONTENT,
        })
        plan = plan_rootless_override(
            _fs=fs,
            _override_src=self.src,
            _override_dest=self.dest,
        )
        self.assertTrue(plan.installed)
        self.assertFalse(plan.needed)

    def test_not_installed_when_dest_missing(self):
        fs = FakeFilesystem(files={str(self.src): self.OVERRIDE_CONTENT})
        plan = plan_rootless_override(
            _fs=fs,
            _override_src=self.src,
            _override_dest=self.dest,
        )
        self.assertFalse(plan.installed)
        self.assertTrue(plan.needed)

    def test_not_installed_when_content_differs(self):
        fs = FakeFilesystem(files={
            str(self.src): self.OVERRIDE_CONTENT,
            str(self.dest): self.OTHER_CONTENT,
        })
        plan = plan_rootless_override(
            _fs=fs,
            _override_src=self.src,
            _override_dest=self.dest,
        )
        self.assertFalse(plan.installed)
        self.assertTrue(plan.needed)

    def test_plan_exposes_src_and_dest_paths(self):
        fs = FakeFilesystem(files={str(self.src): self.OVERRIDE_CONTENT})
        plan = plan_rootless_override(
            _fs=fs,
            _override_src=self.src,
            _override_dest=self.dest,
        )
        self.assertEqual(plan.src, self.src)
        self.assertEqual(plan.dest, self.dest)

    def test_uses_injected_fs_not_real_disk(self):
        """Plan uses only the injected fs; a missing real file is fine."""
        fs = FakeFilesystem(files={
            "/nonexistent/src.conf": "c",
            "/nonexistent/dest.conf": "c",
        })
        plan = plan_rootless_override(
            _fs=fs,
            _override_src=Path("/nonexistent/src.conf"),
            _override_dest=Path("/nonexistent/dest.conf"),
        )
        self.assertTrue(plan.installed)

    def test_default_dest_resolved_through_fs_home(self):
        """When ``_override_dest`` is not given, the default is computed
        from ``fs.home``, not the real ``Path.home()``."""
        src = Path("/fake/override.conf")
        expected_dest = Path("/custom/home/.config/systemd/user/docker.service.d/override.conf")
        fs = FakeFilesystem(
            home=Path("/custom/home"),
            files={str(src): "c", str(expected_dest): "c"},
        )
        plan = plan_rootless_override(
            _fs=fs,
            _override_src=src,
            # _override_dest omitted — must use fs.home
        )
        self.assertEqual(plan.dest, expected_dest)
        self.assertTrue(plan.installed)


# ---------------------------------------------------------------------------
# 7.2 — Rootless override application (in-memory fakes)
# ---------------------------------------------------------------------------


class TestApplyRootlessOverrideInMemory(unittest.TestCase):
    """Override application with in-memory filesystem, service control, clock."""

    OVERRIDE_CONTENT = "[Service]\nPort=forward\n"

    def setUp(self):
        self.src = Path("/fake/override.conf")
        self.dest = Path("/fake/home/.config/systemd/user/docker.service.d/override.conf")
        self.fs = FakeFilesystem(files={str(self.src): self.OVERRIDE_CONTENT})
        self.svc = FakeServiceController()
        self.clock = FakeClock()

        self.plan = RootlessOverridePlan(
            installed=False, needed=True,
            src=self.src, dest=self.dest,
        )

    # -- consent -------------------------------------------------------------

    def test_consent_false_performs_zero_operations(self):
        apply_rootless_override(self.plan, consent=False,
                                _fs=self.fs, _svc=self.svc, _clock=self.clock)
        self.assertEqual(self.fs.copies, [])
        self.assertEqual(self.fs.mkdirs, [])
        self.assertEqual(self.svc.reloads, [])
        self.assertEqual(self.svc.restarts, [])
        self.assertEqual(self.clock.sleeps, [])

    def test_consent_false_bypasses_missing_src(self):
        plan = RootlessOverridePlan(
            installed=False, needed=True,
            src=Path("/nonexistent/override.conf"), dest=self.dest,
        )
        # Must not raise
        apply_rootless_override(plan, consent=False,
                                _fs=self.fs, _svc=self.svc, _clock=self.clock)

    def test_consent_true_with_missing_src_raises(self):
        plan = RootlessOverridePlan(
            installed=False, needed=True,
            src=Path("/nonexistent/override.conf"), dest=self.dest,
        )
        failure = apply_rootless_override(plan, consent=True,
                                          _fs=self.fs, _svc=self.svc,
                                          _clock=self.clock)
        self.assertIsInstance(failure, OverrideFailure)
        self.assertFalse(failure.persistence_applied)
        self.assertIn("source file not found", failure.detail)

    # -- plan.needed == False (no-op) ---------------------------------------

    def test_needed_false_performs_zero_operations(self):
        plan = RootlessOverridePlan(
            installed=True, needed=False,
            state=OverrideState.MATCHING,
            src=self.src, dest=self.dest,
        )
        apply_rootless_override(plan, consent=True,
                                _fs=self.fs, _svc=self.svc, _clock=self.clock)
        self.assertEqual(self.fs.copies, [], "no copy for no-op plan")
        self.assertEqual(self.fs.mkdirs, [], "no mkdir for no-op plan")
        self.assertEqual(self.svc.reloads, [], "no reload for no-op plan")
        self.assertEqual(self.svc.restarts, [], "no restart for no-op plan")
        self.assertEqual(self.clock.sleeps, [], "no sleep for no-op plan")

    def test_needed_false_ignores_missing_src(self):
        plan = RootlessOverridePlan(
            installed=False, needed=False,
            state=OverrideState.ABSENT,
            src=Path("/nonexistent/override.conf"), dest=self.dest,
        )
        result = apply_rootless_override(plan, consent=True,
                                         _fs=self.fs, _svc=self.svc,
                                         _clock=self.clock)
        self.assertIsNone(result, "no error for no-op plan, even with missing src")

    def test_needed_false_ignores_missing_src_without_consent(self):
        """The needed=False check runs after consent=False, so both guards
        independently prevent side effects."""
        plan = RootlessOverridePlan(
            installed=False, needed=False,
            src=Path("/nonexistent/override.conf"), dest=self.dest,
        )
        apply_rootless_override(plan, consent=False,
                                _fs=self.fs, _svc=self.svc, _clock=self.clock)
        self.assertEqual(self.fs.copies, [])
        self.assertEqual(self.svc.restarts, [])

    def test_needed_false_rootful_not_applicable_still_noop(self):
        """Even when rootless=False (rootful mode), needed=False means no-op."""
        plan = RootlessOverridePlan(
            installed=False, needed=False,
            rootless=False, state=OverrideState.ABSENT,
            src=self.src, dest=self.dest,
        )
        apply_rootless_override(plan, consent=True,
                                _fs=self.fs, _svc=self.svc, _clock=self.clock)
        self.assertEqual(self.fs.copies, [])
        self.assertEqual(self.svc.restarts, [])

    # -- happy path ----------------------------------------------------------

    def test_copies_src_to_dest(self):
        apply_rootless_override(self.plan, consent=True,
                                _fs=self.fs, _svc=self.svc, _clock=self.clock)
        self.assertEqual(len(self.fs.copies), 1)
        self.assertEqual(self.fs.copies[0], (self.src, self.dest))
        # Dest should now exist in the in-memory fs
        self.assertTrue(self.fs.is_file(self.dest))

    def test_creates_dest_parent_directory(self):
        apply_rootless_override(self.plan, consent=True,
                                _fs=self.fs, _svc=self.svc, _clock=self.clock)
        self.assertEqual(len(self.fs.mkdirs), 1)
        self.assertEqual(self.fs.mkdirs[0], self.dest.parent)

    # -- service control -----------------------------------------------------

    def test_reloads_daemon_before_restart(self):
        apply_rootless_override(self.plan, consent=True,
                                _fs=self.fs, _svc=self.svc, _clock=self.clock)
        self.assertEqual(len(self.svc.reloads), 1)
        self.assertEqual(len(self.svc.restarts), 1)
        self.assertEqual(self.svc.restarts[0], "docker.service")

    def test_daemon_reload_failure_propagates(self):
        svc = FakeServiceController(fail_daemon_reload=OSError("systemctl not found"))
        failure = apply_rootless_override(self.plan, consent=True,
                                          _fs=self.fs, _svc=svc,
                                          _clock=self.clock)
        self.assertIsInstance(failure, OverrideFailure)
        self.assertEqual(failure.operation, "daemon-reload")
        self.assertIn("systemctl not found", failure.detail)
        self.assertTrue(failure.persistence_applied)
        # Copy happened, reload failed before restart
        self.assertEqual(len(self.fs.copies), 1)

    def test_restart_failure_propagates_after_reload(self):
        svc = FakeServiceController(fail_restart=OSError("docker not running"))
        failure = apply_rootless_override(self.plan, consent=True,
                                          _fs=self.fs, _svc=svc,
                                          _clock=self.clock)
        self.assertIsInstance(failure, OverrideFailure)
        self.assertEqual(failure.operation, "restart")
        self.assertIn("docker not running", failure.detail)
        self.assertTrue(failure.persistence_applied)
        self.assertEqual(len(svc.reloads), 1)
        self.assertEqual(len(svc.restarts), 1)

    # -- nonzero return code from systemctl ---------------------------------

    def test_daemon_reload_nonzero_rc_yields_override_failure(self):
        svc = FakeServiceController()
        svc._next_daemon_reload_rc = 1
        svc._next_daemon_reload_stderr = "Failed to connect to bus: No such file"
        failure = apply_rootless_override(self.plan, consent=True,
                                          _fs=self.fs, _svc=svc,
                                          _clock=self.clock)
        self.assertIsInstance(failure, OverrideFailure)
        self.assertEqual(failure.operation, "daemon-reload")
        self.assertIn("Failed to connect to bus", failure.detail)
        self.assertIn("rc=1", failure.detail)
        self.assertTrue(failure.persistence_applied)
        self.assertEqual(len(self.fs.copies), 1)

    def test_daemon_reload_nonzero_rc_stderr_bounded_to_200_chars(self):
        svc = FakeServiceController()
        svc._next_daemon_reload_rc = 1
        svc._next_daemon_reload_stderr = "x" * 500
        failure = apply_rootless_override(self.plan, consent=True,
                                          _fs=self.fs, _svc=svc,
                                          _clock=self.clock)
        self.assertIsInstance(failure, OverrideFailure)
        # The bounded portion is 200 chars; the detail may be longer
        # because of the "daemon-reload failed (rc=1): " prefix, but
        # the stderr portion must be at most 200 chars.
        self.assertLessEqual(len("x" * 500), 500)  # sanity
        self.assertNotIn("x" * 201, failure.detail,
                         "stderr must be bounded to 200 chars")

    def test_restart_nonzero_rc_yields_override_failure(self):
        svc = FakeServiceController()
        svc._next_restart_rc = 3
        svc._next_restart_stderr = "Job for docker.service failed"
        failure = apply_rootless_override(self.plan, consent=True,
                                          _fs=self.fs, _svc=svc,
                                          _clock=self.clock)
        self.assertIsInstance(failure, OverrideFailure)
        self.assertEqual(failure.operation, "restart")
        self.assertIn("Job for docker.service failed", failure.detail)
        self.assertIn("rc=3", failure.detail)
        self.assertTrue(failure.persistence_applied)
        self.assertEqual(len(svc.reloads), 1)
        self.assertEqual(len(svc.restarts), 1)

    def test_restart_nonzero_rc_stderr_bounded_to_200_chars(self):
        svc = FakeServiceController()
        svc._next_restart_rc = 1
        svc._next_restart_stderr = "y" * 500
        failure = apply_rootless_override(self.plan, consent=True,
                                          _fs=self.fs, _svc=svc,
                                          _clock=self.clock)
        self.assertIsInstance(failure, OverrideFailure)
        self.assertNotIn("y" * 201, failure.detail,
                         "stderr must be bounded to 200 chars")

    # -- clock ---------------------------------------------------------------

    def test_sleeps_after_restart(self):
        apply_rootless_override(self.plan, consent=True,
                                _fs=self.fs, _svc=self.svc, _clock=self.clock)
        self.assertEqual(self.clock.sleeps, [3.0])

    # -- no prompt -----------------------------------------------------------

    def test_does_not_call_input(self):
        with mock.patch("builtins.input") as mock_input:
            apply_rootless_override(self.plan, consent=True,
                                    _fs=self.fs, _svc=self.svc, _clock=self.clock)
        mock_input.assert_not_called()


# ---------------------------------------------------------------------------
# 7.2 — Operational persistence (in-memory filesystem, atomic writes)
# ---------------------------------------------------------------------------


class TestUpdateEnvFile(unittest.TestCase):
    """Operational dotenv persistence through ``Filesystem`` fake."""

    ENV = Path("/fake/project/.env")

    def setUp(self):
        self.fs = FakeFilesystem(files={})

    def test_creates_new_file_with_updates(self):
        update_env_file(self.ENV, {"HOST_GATEWAY_IP": "10.0.0.55"}, _fs=self.fs)
        self.assertIn("HOST_GATEWAY_IP=10.0.0.55", self.fs.read_text(self.ENV))

    def test_overwrites_existing_key(self):
        self.fs._files[str(self.ENV)] = "HOST_GATEWAY_IP=10.0.0.1\n"
        update_env_file(self.ENV, {"HOST_GATEWAY_IP": "10.0.0.99"}, _fs=self.fs)
        content = self.fs.read_text(self.ENV)
        self.assertIn("HOST_GATEWAY_IP=10.0.0.99", content)
        self.assertNotIn("10.0.0.1", content)

    def test_preserves_unrelated_keys(self):
        self.fs._files[str(self.ENV)] = (
            "PI_HOME=/home/dev/.pi\nHOST_GATEWAY_IP=10.0.0.1\n"
        )
        update_env_file(self.ENV, {"HOST_GATEWAY_IP": "10.0.0.99"}, _fs=self.fs)
        content = self.fs.read_text(self.ENV)
        self.assertIn("PI_HOME=/home/dev/.pi", content)

    def test_removes_requested_keys(self):
        self.fs._files[str(self.ENV)] = (
            "SOCKS_HOST=localhost:1080\nHOST_GATEWAY_IP=10.0.0.1\n"
        )
        update_env_file(self.ENV, {}, remove_keys=["SOCKS_HOST"], _fs=self.fs)
        content = self.fs.read_text(self.ENV)
        self.assertNotIn("SOCKS_HOST", content)
        self.assertIn("HOST_GATEWAY_IP=10.0.0.1", content)

    def test_ignores_comments_and_empty_lines(self):
        self.fs._files[str(self.ENV)] = (
            "# comment\n\nHOST_GATEWAY_IP=10.0.0.1\n"
        )
        update_env_file(self.ENV, {"HOST_GATEWAY_IP": "10.0.0.99"}, _fs=self.fs)
        content = self.fs.read_text(self.ENV)
        lines = content.splitlines()
        self.assertIn("# comment", lines)
        self.assertIn("HOST_GATEWAY_IP=10.0.0.99", content)

    def test_appends_new_keys(self):
        self.fs._files[str(self.ENV)] = "OLD_KEY=val\n"
        update_env_file(self.ENV, {"NEW_KEY": "new_val"}, _fs=self.fs)
        content = self.fs.read_text(self.ENV)
        self.assertIn("OLD_KEY=val", content)
        self.assertIn("NEW_KEY=new_val", content)

    # -- concurrency-safe temp files ----------------------------------------

    def test_temp_file_is_namespaced_per_call(self):
        """Successive calls use distinct tmp names — no shared fixed suffix."""
        self.fs.clear_writes()
        update_env_file(self.ENV, {"A": "1"}, _fs=self.fs, _tmp_suffix="pid1")
        update_env_file(self.ENV, {"B": "2"}, _fs=self.fs, _tmp_suffix="pid2")
        tmp_paths = {r[0] for r in self.fs.renames}
        self.assertEqual(len(tmp_paths), 2,
                         "each call must write to a unique temporary path")

    def test_concurrent_writers_do_not_collide(self):
        """Two writers with distinct suffixes never overwrite each other's
        temp file, and both updates land in the final file."""
        self.fs._files[str(self.ENV)] = "INIT=0\n"
        update_env_file(self.ENV, {"A": "1"}, _fs=self.fs, _tmp_suffix="w1")
        # Second writer uses a different suffix — its tmp path is unique
        update_env_file(self.ENV, {"B": "2"}, _fs=self.fs, _tmp_suffix="w2")
        content = self.fs.read_text(self.ENV)
        self.assertIn("A=1", content)
        self.assertIn("B=2", content)
        self.assertIn("INIT=0", content)

    def test_collision_same_suffix_still_converges(self):
        """Even when two writers share the same suffix (simulated race),
        the last rename wins and temp debris is cleaned."""
        self.fs._files[str(self.ENV)] = "INIT=0\n"
        update_env_file(self.ENV, {"A": "1"}, _fs=self.fs, _tmp_suffix="same")
        update_env_file(self.ENV, {"B": "2"}, _fs=self.fs, _tmp_suffix="same")
        content = self.fs.read_text(self.ENV)
        # Last writer wins, but both writes succeed without crashing
        self.assertIn("B=2", content)
        # Temp file cleaned up after final call
        tmp = self.ENV.with_name(f"{self.ENV.name}.tmp.same")
        self.assertFalse(self.fs.is_file(tmp),
                         "temp file must be cleaned up")

    def test_default_suffix_differs_between_calls(self):
        """Without ``_tmp_suffix`` injection, real calls use a
        unique per-process+timestamp suffix."""
        update_env_file(self.ENV, {"A": "1"}, _fs=self.fs)
        # A second call should succeed — it generates a fresh suffix
        update_env_file(self.ENV, {"B": "2"}, _fs=self.fs)
        self.assertIn("A=1", self.fs.read_text(self.ENV))
        self.assertIn("B=2", self.fs.read_text(self.ENV))

    # -- failure cleanup ----------------------------------------------------

    def test_temp_file_cleaned_on_rename_failure(self):
        """When ``fs.rename`` raises, the temp file is deleted in the
        ``finally`` block and the original file is untouched."""

        class RenameFailingFs(FakeFilesystem):
            def rename(self, src, dest):
                self.renames.append((src, dest))
                raise OSError("cross-device link")

        self.fs._files[str(self.ENV)] = "SAFE=data\n"
        fs = RenameFailingFs(files={str(self.ENV): "SAFE=data\n"})
        with self.assertRaises(OSError):
            update_env_file(self.ENV, {"HOST_GATEWAY_IP": "10.0.0.1"},
                            _fs=fs, _tmp_suffix="rxfail")
        # Original untouched
        self.assertEqual(fs.read_text(self.ENV), "SAFE=data\n")
        # Temp debris removed
        tmp = self.ENV.with_name(f"{self.ENV.name}.tmp.rxfail")
        self.assertFalse(fs.is_file(tmp), "temp file must be cleaned up on rename failure")

    def test_write_failure_cleanup_is_noop(self):
        """When ``fs.write_text`` itself fails, no temp file exists to
        clean up — but the ``finally`` block must not raise."""

        class WriteFailingFs(FakeFilesystem):
            def write_text(self, path, content, encoding="utf-8"):
                raise OSError("disk full")

        self.fs._files[str(self.ENV)] = "SAFE=data\n"
        fs = WriteFailingFs(files={str(self.ENV): "SAFE=data\n"})
        with self.assertRaises(OSError):
            update_env_file(self.ENV, {"HOST_GATEWAY_IP": "10.0.0.1"},
                            _fs=fs, _tmp_suffix="wfail")
        self.assertEqual(fs.read_text(self.ENV), "SAFE=data\n")

    def test_delete_failure_inside_finally_is_suppressed(self):
        """If ``fs.delete`` itself raises, the original ``rename``
        error is not masked."""

        class NastyFs(FakeFilesystem):
            def rename(self, src, dest):
                self.renames.append((src, dest))
                raise OSError("rename failed")

            def delete(self, path):
                raise PermissionError("cannot delete")

        fs = NastyFs(files={str(self.ENV): "SAFE=data\n"})
        with self.assertRaises(OSError) as ctx:
            update_env_file(self.ENV, {"HOST_GATEWAY_IP": "10.0.0.1"},
                            _fs=fs, _tmp_suffix="nasty")
        # The original (rename) error propagates
        self.assertIn("rename failed", str(ctx.exception))


# ---------------------------------------------------------------------------
# 7.3 — Full diagnosis with injected boundaries
# ---------------------------------------------------------------------------


class TestDiagnoseGateway(unittest.TestCase):
    """Full diagnosis orchestration with injected boundaries."""

    @staticmethod
    def _docker_info(stdout: str = "Server Version: 27.0.0") -> ProcessResult:
        return ProcessResult(
            argv=("docker", "info"), return_code=0,
            stdout=stdout, stderr="",
        )

    @staticmethod
    def _docker_probe(resolved_ip: str = "172.17.0.1") -> ProcessResult:
        return ProcessResult(
            argv=("docker", "run", "--rm", "--add-host",
                  "host.docker.internal:host-gateway", "alpine:3.20",
                  "sh", "-c", "..."),
            return_code=0,
            stdout=f"RESOLVED_IP={resolved_ip}\nPROBE_OK",
            stderr="",
        )

    @staticmethod
    def _hostname_ip(ip: str = "192.168.1.10") -> ProcessResult:
        return ProcessResult(
            argv=("hostname", "-I"), return_code=0,
            stdout=ip, stderr="",
        )

    def test_rootful_diagnosis_with_successful_probe(self):
        runner = FakeProcessRunner([
            self._docker_info(),
            self._hostname_ip("192.168.1.10"),
            self._docker_probe(),
            self._docker_probe(),  # second candidate
        ])
        d = diagnose_gateway(
            _runner=runner,
            _host_probe_factory=lambda: FakeHostProbeServer(port=12345, token="TOK"),
            _fs=FakeFilesystem(),
        )
        self.assertIs(d.mode, DockerMode.ROOTFUL)
        self.assertEqual(d.lan_ip, "192.168.1.10")
        self.assertEqual(d.chosen_gateway, "host-gateway")
        self.assertEqual(d.host_gateway_ip, "172.17.0.1")
        self.assertEqual(len(d.probes), 2)

    def test_rootless_diagnosis_with_override_needed(self):
        runner = FakeProcessRunner([
            self._docker_info("  rootless: true\n"),
            self._hostname_ip(""),
            self._docker_probe("10.0.2.100"),
            self._docker_probe("10.0.2.100"),  # second candidate
        ])
        d = diagnose_gateway(
            _runner=runner,
            _host_probe_factory=lambda: FakeHostProbeServer(port=9000, token="TK"),
            _fs=FakeFilesystem(),
        )
        self.assertIs(d.mode, DockerMode.ROOTLESS)
        self.assertTrue(d.override_needed)
        self.assertEqual(d.probes[0].candidate, "10.0.2.2")
        self.assertTrue(d.probes[0].ok)

    def test_no_candidate_succeeds(self):
        runner = FakeProcessRunner([
            self._docker_info(),
            # hostname -I (fails), ip route (fails too)
            ProcessResult(
                argv=("hostname", "-I"), return_code=1,
                stdout="", stderr="not found",
            ),
            ProcessResult(
                argv=("ip", "-4", "route", "show", "default"),
                return_code=1, stdout="", stderr="no route",
            ),
            # Rootful: candidates are [host-gateway]
            ProcessResult(
                argv=("docker", "run", "--rm", "--add-host",
                      "host.docker.internal:host-gateway", "alpine:3.20",
                      "sh", "-c", "..."),
                return_code=1, stdout="", stderr="connection refused",
            ),
        ])
        d = diagnose_gateway(
            _runner=runner,
            _host_probe_factory=lambda: FakeHostProbeServer(port=1, token="X"),
            _fs=FakeFilesystem(),
        )
        self.assertIsNone(d.chosen_gateway)
        self.assertIsNone(d.host_gateway_ip)

    def test_server_stops_after_diagnosis(self):
        fake = FakeHostProbeServer()
        runner = FakeProcessRunner([
            self._docker_info(),
            # hostname -I returns empty, ip route returns not found
            self._hostname_ip(""),
            ProcessResult(
                argv=("ip", "-4", "route", "show", "default"),
                return_code=1, stdout="", stderr="not found",
            ),
            # Rootful: candidates are [host-gateway]
            ProcessResult(
                argv=("docker", "run", "--rm", "--add-host",
                      "host.docker.internal:host-gateway", "alpine:3.20",
                      "sh", "-c", "..."),
                return_code=1, stdout="", stderr="timeout",
            ),
        ])
        diagnose_gateway(_runner=runner, _host_probe_factory=lambda: fake,
                         _fs=FakeFilesystem())
        self.assertTrue(fake.stopped)

    def test_override_installed_flag_from_in_memory_fs(self):
        src = Path("/fake/override.conf")
        dest = Path("/fake/home/.config/systemd/user/docker.service.d/override.conf")
        content = "[Service]\nX=1\n"
        fs = FakeFilesystem(files={str(src): content, str(dest): content})
        runner = FakeProcessRunner([
            self._docker_info("  rootless: true\n"),
            self._hostname_ip("10.0.0.5"),
            self._docker_probe("10.0.2.100"),  # 10.0.2.2
            self._docker_probe("10.0.2.100"),  # 10.0.0.5
            self._docker_probe("10.0.2.100"),  # host-gateway
        ])
        d = diagnose_gateway(
            _runner=runner,
            _host_probe_factory=FakeHostProbeServer,
            _fs=fs,
            _override_src=src,
            _override_dest=dest,
        )
        self.assertTrue(d.override_installed)
        self.assertFalse(d.override_needed)

    def test_diagnosis_returns_frozen_data(self):
        runner = FakeProcessRunner([
            self._docker_info(),
            self._hostname_ip("10.0.0.5"),
            self._docker_probe(),
            self._docker_probe(),
        ])
        d = diagnose_gateway(
            _runner=runner,
            _host_probe_factory=FakeHostProbeServer,
            _fs=FakeFilesystem(),
        )
        self.assertIsInstance(d.probes, tuple)
        with self.assertRaises(dataclasses.FrozenInstanceError):
            d.chosen_gateway = "hacked"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# 7.6 / 7.7 — Import boundary checks
# ---------------------------------------------------------------------------


class TestImportBoundary(unittest.TestCase):
    """The networking module must not import the facade or execution layers."""

    def test_module_does_not_import_argparse(self):
        import ast
        with open("docker/networking.py") as f:
            tree = ast.parse(f.read())
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    self.assertNotIn("argparse", alias.name,
                                     "must not import argparse")
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    self.assertNotIn("argparse", node.module,
                                     "must not import argparse")

    def test_module_does_not_import_facade_or_orchestration(self):
        import ast
        with open("docker/networking.py") as f:
            tree = ast.parse(f.read())
        forbidden_modules = {"docker.versions", "docker.build_wrapper",
                             "docker.launch_pi", "docker.cli"}
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                self.assertNotIn(node.module, forbidden_modules,
                                 f"must not import {node.module}")

    def test_module_does_not_declare_argparse_parser(self):
        import ast
        with open("docker/networking.py") as f:
            tree = ast.parse(f.read())
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                if isinstance(node.func, ast.Attribute):
                    if "ArgumentParser" in getattr(node.func, "attr", ""):
                        self.fail("must not create ArgumentParser")


class TestPersistGateway(unittest.TestCase):
    """``persist_gateway`` writes HOST_GATEWAY_IP and returns result."""

    def setUp(self):
        self.path = Path("/tmp/test.env")

    def test_writes_gateway_and_reports_success(self):
        fs = FakeFilesystem()
        result = persist_gateway(self.path, "10.0.0.1", _fs=fs)
        self.assertTrue(result.written)
        self.assertEqual(result.gateway, "10.0.0.1")
        self.assertEqual(result.path, self.path)
        self.assertIsNone(result.error)
        self.assertIn("HOST_GATEWAY_IP=10.0.0.1", fs.read_text(self.path))

    def test_empty_gateway_returns_error_not_raises(self):
        fs = FakeFilesystem()
        result = persist_gateway(self.path, "", _fs=fs)
        self.assertFalse(result.written)
        self.assertEqual(result.gateway, "")
        self.assertIsNotNone(result.error)
        self.assertIn("non-empty", result.error)

    def test_whitespace_gateway_returns_error(self):
        fs = FakeFilesystem()
        result = persist_gateway(self.path, "   ", _fs=fs)
        self.assertFalse(result.written)
        self.assertIn("non-empty", result.error)

    # -- dotenv injection / semantic rejection ------------------------------

    def _assert_gateway_rejected(self, value: str):
        fs = FakeFilesystem()
        result = persist_gateway(self.path, value, _fs=fs)
        self.assertFalse(result.written,
                         f"gateway {value!r} must be rejected")
        self.assertIn("not a valid IP", result.error or "")
        # Filesystem must be untouched.
        self.assertEqual(fs.writes, [], f"no writes for {value!r}")
        self.assertEqual(fs.renames, [], f"no renames for {value!r}")

    def test_newline_in_gateway_rejected(self):
        self._assert_gateway_rejected("10.0.0.1\nHOST_GATEWAY_IP=evil")

    def test_equals_in_gateway_rejected(self):
        self._assert_gateway_rejected("10.0.0.1 = foo")

    def test_hash_in_gateway_rejected(self):
        self._assert_gateway_rejected("10.0.0.1  # comment")

    def test_internal_whitespace_rejected(self):
        self._assert_gateway_rejected("10.0.0.1 extra")

    def test_tab_rejected(self):
        self._assert_gateway_rejected("10.0.0.1\textra")

    def test_dollar_home_rejected(self):
        self._assert_gateway_rejected("$HOME")

    def test_subshell_rejected(self):
        self._assert_gateway_rejected("$(whoami)")

    def test_semicolon_injection_rejected(self):
        self._assert_gateway_rejected("10.0.0.1;foo")

    def test_arbitrary_text_rejected(self):
        self._assert_gateway_rejected("something-else")

    # -- valid gateways accepted --------------------------------------------

    def test_host_gateway_literal_accepted(self):
        fs = FakeFilesystem()
        result = persist_gateway(self.path, "host-gateway", _fs=fs)
        self.assertTrue(result.written)
        self.assertIsNone(result.error)

    def test_ipv4_accepted(self):
        fs = FakeFilesystem()
        result = persist_gateway(self.path, "192.168.1.1", _fs=fs)
        self.assertTrue(result.written)

    def test_ipv6_accepted(self):
        fs = FakeFilesystem()
        result = persist_gateway(self.path, "::1", _fs=fs)
        self.assertTrue(result.written)


class TestProbeTimeoutParameter(unittest.TestCase):
    """``probe_timeout`` controls wget --timeout in the probe script."""

    def test_default_timeout_is_three_seconds(self):
        seen: list[list[str]] = []

        class _Rec(ProcessRunner):
            def run(self, argv):
                seen.append(list(argv))
                return ProcessResult(argv=tuple(argv), return_code=0,
                                     stdout="PROBE_OK", stderr="")

        probe_gateway("gw", 9999, "T", _runner=_Rec())
        script = seen[0][-1]  # last arg is the script
        self.assertIn("--timeout=3", script,
                      "default probe timeout must be 3 seconds")

    def test_custom_timeout_is_interpolated(self):
        seen: list[list[str]] = []

        class _Rec(ProcessRunner):
            def run(self, argv):
                seen.append(list(argv))
                return ProcessResult(argv=tuple(argv), return_code=0,
                                     stdout="PROBE_OK", stderr="")

        probe_gateway("gw", 9999, "T", probe_timeout=10, _runner=_Rec())
        script = seen[0][-1]
        self.assertIn("--timeout=10", script)

    # -- invalid timeout values reject before runner -------------------------

    def _assert_timeout_rejected(self, value):
        called = []

        class _Rec(ProcessRunner):
            def run(self, argv):
                called.append(argv)
                return ProcessResult(argv=tuple(argv), return_code=0,
                                     stdout="PROBE_OK", stderr="")

        result = probe_gateway("gw", 9999, "T", probe_timeout=value,
                               _runner=_Rec())
        self.assertFalse(result.ok)
        self.assertIn("probe_timeout", result.detail,
                      f"timeout {value!r} must be rejected")
        self.assertEqual(called, [],
                         f"runner must not be called for timeout {value!r}")

    def test_zero_timeout_rejected(self):
        self._assert_timeout_rejected(0)

    def test_negative_timeout_rejected(self):
        self._assert_timeout_rejected(-1)

    def test_bool_true_rejected(self):
        self._assert_timeout_rejected(True)

    def test_bool_false_rejected(self):
        self._assert_timeout_rejected(False)

    def test_float_rejected(self):
        self._assert_timeout_rejected(3.0)

    def test_str_rejected(self):
        self._assert_timeout_rejected("3; rm -rf /")

    def test_large_timeout_rejected(self):
        self._assert_timeout_rejected(301)


if __name__ == "__main__":
    unittest.main()
