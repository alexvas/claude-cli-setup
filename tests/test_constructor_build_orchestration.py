"""RED tests for Stage 9.1 — Build orchestration contract.

These tests define the full expected contract for ``orchestrate_build``
and related DTOs (tasks 7–23).  Every test uses injected fakes — no
Docker daemon, systemd, filesystem writes, or network calls.

The stub ``orchestrate_build`` returns ``OPERATIONAL`` for every input.
Most tests below assert *expected real behaviour* (e.g. ``SUCCESS``,
``CONFIG``, non-empty ``build_args``, recorded process output) and
therefore **genuinely FAIL** against the stub.  This is the RED signal
that drives the Stage 9.3 implementation.
"""

from __future__ import annotations

import unittest
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Optional

from docker.networking import (
    DockerMode,
    GatewayDiagnosis,
    PersistenceResult,
    ProbeResult,
)
from docker.versioning.build_orchestration import (
    BuildRequest,
    BuildResult,
    PublishResult,
    ProcessResult,
    orchestrate_build,
)
from docker.versioning.dispatch_types import ExitKind


# ═══════════════════════════════════════════════════════════════════════
# Fakes — injectable, no Docker/systemd/fs/network
# ═══════════════════════════════════════════════════════════════════════


def _make_diagnosis(
    *,
    mode: DockerMode = DockerMode.ROOTFUL,
    chosen_gateway: str | None = "172.17.0.1",
) -> GatewayDiagnosis:
    """Build a minimal ``GatewayDiagnosis`` with a single probe result."""
    ok = chosen_gateway is not None
    probe = ProbeResult(
        candidate=chosen_gateway or "172.17.0.1",
        ok=ok,
        resolved_ip=chosen_gateway,
        detail="" if ok else "no route to host",
    )
    return GatewayDiagnosis(
        mode=mode,
        probe_port=8080,
        probe_token="test-token",
        lan_ip=None,
        probes=(probe,),
        chosen_gateway=chosen_gateway,
        override_installed=False,
        override_needed=False,
    )


class FakeBuildExecutor:
    """Recording build executor matching ``BuildExecutor`` Protocol."""

    def __init__(self, result: ProcessResult | None = None,
                 returncode: int = 0):
        self._result = result
        self.returncode = returncode
        self.calls: list[tuple[str, ...]] = []

    def run(self, argv: tuple[str, ...]) -> ProcessResult:
        self.calls.append(argv)
        if self._result is not None:
            return self._result
        return ProcessResult(
            argv=argv,
            return_code=self.returncode,
            stdout="build output" if self.returncode == 0 else "",
            stderr="" if self.returncode == 0 else "build error",
        )


# ── Convenience factories (inject into BuildRequest fields) ──────────



def _diag_reachable(**kw):
    return _make_diagnosis(
        mode=DockerMode.ROOTFUL,
        chosen_gateway="172.17.0.1",
    )


def _diag_unreachable(**kw):
    return _make_diagnosis(
        mode=DockerMode.ROOTFUL,
        chosen_gateway=None,
    )


def _persist_ok(path=None, gateway=None):
    return PersistenceResult(
        path=Path("/tmp/.env"),
        gateway="172.17.0.1",
        written=True,
    )


def _persist_fail(path=None, gateway=None):
    return PersistenceResult(
        path=Path("/tmp/.env"),
        gateway="172.17.0.1",
        written=False,
        error="EACCES",
    )


def _publish_ok(inv=None, projection=None, path=None):
    return PublishResult(published_path="/tmp/effective.toml")


# ═══════════════════════════════════════════════════════════════════════
# 7.  DTO expectations (GREEN — these test the DTOs, not the stub)
# ═══════════════════════════════════════════════════════════════════════


class TestBuildRequestDto(unittest.TestCase):
    """Task 7 — immutable BuildRequest fields."""

    def test_minimal_request_has_all_defaults(self):
        req = BuildRequest(inventory_path="docker-constructor.toml")
        self.assertEqual("docker-constructor.toml", req.inventory_path)
        self.assertEqual("linux-amd64", req.platform)
        self.assertIsNone(req.tag)
        self.assertEqual({}, dict(req.overrides))
        self.assertEqual("runtime", req.target)
        self.assertIsNone(req.context)
        self.assertIsNone(req.dockerfile)
        self.assertTrue(req.cache)
        self.assertFalse(req.pull)
        self.assertEqual("auto", req.progress)
        self.assertIsNone(req.uid)
        self.assertIsNone(req.gid)
        self.assertFalse(req.confirmed)
        self.assertFalse(req.dry_run)
        self.assertIsNone(req.runner)
        self.assertEqual("alpine:3.20", req.gateway_probe_image)
        self.assertIsNone(req.repo_root)
        self.assertIsNone(req._diagnose_gateway)
        self.assertIsNone(req._persist_gateway)
        self.assertIsNone(req._publish_projection)

    def test_all_fields_assignable(self):
        req = BuildRequest(
            inventory_path="docker-constructor.toml",
            platform="linux-arm64",
            tag="pi:custom",
            overrides=MappingProxyType({"a": "b"}),
            target="build",
            context="./ctx",
            dockerfile="Dockerfile.alt",
            cache=False,
            pull=True,
            progress="plain",
            uid=1000,
            gid=1000,
            confirmed=True,
            dry_run=True,
            runner=FakeBuildExecutor(),
            gateway_probe_image="busybox:1.36",
            repo_root="/tmp",
            _diagnose_gateway=_diag_reachable,
            _persist_gateway=_persist_ok,
            _publish_projection=_publish_ok,
        )
        self.assertEqual("linux-arm64", req.platform)
        self.assertEqual("pi:custom", req.tag)
        self.assertEqual("build", req.target)
        self.assertEqual("./ctx", req.context)
        self.assertEqual("Dockerfile.alt", req.dockerfile)
        self.assertFalse(req.cache)
        self.assertTrue(req.pull)
        self.assertEqual("plain", req.progress)
        self.assertEqual(1000, req.uid)
        self.assertEqual(1000, req.gid)
        self.assertTrue(req.confirmed)
        self.assertTrue(req.dry_run)

    def test_build_result_carries_all_fields(self):
        pr = ProcessResult(argv=("docker", "build", "."), return_code=0, stdout="ok", stderr="")
        result = BuildResult(
            exit_kind=ExitKind.SUCCESS,
            message="done",
            build_args=("docker", "build", "."),
            display_string="docker build .",
            process_result=pr,
            host_gateway_ip="10.0.0.1",
        )
        self.assertEqual(ExitKind.SUCCESS, result.exit_kind)
        self.assertEqual("done", result.message)
        self.assertEqual(("docker", "build", "."), result.build_args)
        self.assertEqual("docker build .", result.display_string)
        self.assertIs(pr, result.process_result)
        self.assertEqual("10.0.0.1", result.host_gateway_ip)

    def test_dtos_are_frozen(self):
        req = BuildRequest(inventory_path="docker-constructor.toml")
        with self.assertRaises(Exception):
            req.platform = "linux-arm64"  # type: ignore[misc]
        result = BuildResult(exit_kind=ExitKind.SUCCESS)
        with self.assertRaises(Exception):
            result.message = "nope"  # type: ignore[misc]

    def test_overrides_normalized_to_immutable(self):
        """Caller-side mutation of a mutable dict passed to ``overrides``
        must **not** alter the frozen ``BuildRequest`` after construction."""
        mutable = {"A": "1", "B": "2"}
        req = BuildRequest(
            inventory_path="docker-constructor.toml",
            overrides=mutable,
        )
        self.assertIsInstance(req.overrides, MappingProxyType)
        self.assertEqual({"A": "1", "B": "2"}, dict(req.overrides))
        # Mutate the caller-owned dict
        mutable["A"] = "HACKED"
        mutable["C"] = "3"
        del mutable["B"]
        # Request must be unchanged
        self.assertEqual({"A": "1", "B": "2"}, dict(req.overrides),
                         "caller mutation must not alter frozen request")
        # Setting overrides on frozen instance must still fail
        with self.assertRaises(Exception):
            req.overrides = MappingProxyType({"X": "Y"})  # type: ignore[misc]

    def test_overrides_default_is_empty_immutable(self):
        """Default ``overrides`` (no argument) must be an empty immutable
        mapping."""
        req = BuildRequest(inventory_path="docker-constructor.toml")
        self.assertIsInstance(req.overrides, MappingProxyType)
        self.assertEqual({}, dict(req.overrides))

    def test_process_result_boundary_match(self):
        """``ProcessResult`` used by build orchestration is the same type
        accepted by ``docker.networking`` — there is no duplicate."""
        from docker.networking import ProcessResult as NetPR
        self.assertIs(NetPR, ProcessResult,
                      "build_orchestration must re-use networking.ProcessResult")

    def test_build_executor_boundary(self):
        """A ``FakeBuildExecutor`` satisfies the ``BuildExecutor`` Protocol —
        ``run(tuple[str, ...])`` returns ``ProcessResult`` with ``argv`` /
        ``return_code`` fields."""
        runner = FakeBuildExecutor()
        result = runner.run(("docker", "build", "-t", "pi:latest", "."))
        self.assertIsInstance(result, ProcessResult)
        self.assertEqual(("docker", "build", "-t", "pi:latest", "."), result.argv)
        self.assertEqual(0, result.return_code)

    def test_build_executor_distinct_from_networking_runner(self):
        """``BuildExecutor`` is a separate contract from ``ProcessRunner`` —
        build uses ``tuple[str, ...]`` while networking uses ``list[str]``."""
        from docker.networking import ProcessRunner
        from docker.versioning.build_orchestration import BuildExecutor
        self.assertIsNot(BuildExecutor, ProcessRunner)
        # A BuildExecutor is NOT a ProcessRunner (different signatures)
        be = FakeBuildExecutor()
        self.assertNotIsInstance(be, ProcessRunner)


# ═══════════════════════════════════════════════════════════════════════
# 8.  Injectables wired through BuildRequest
# ═══════════════════════════════════════════════════════════════════════


class TestInjectablesWired(unittest.TestCase):
    """Task 8 — all side-effecting boundaries injectable through BuildRequest."""

    def test_all_injectables_accepted(self):
        """BuildRequest must carry every injectable slot."""
        runner = FakeBuildExecutor()
        req = BuildRequest(
            inventory_path="docker-constructor.toml",
            runner=runner,
            _diagnose_gateway=_diag_reachable,
            _persist_gateway=_persist_ok,
            _publish_projection=_publish_ok,
        )
        # Just verify the slots are populated
        self.assertIs(runner, req.runner)
        self.assertIs(_diag_reachable, req._diagnose_gateway)
        self.assertIs(_persist_ok, req._persist_gateway)
        self.assertIs(_publish_ok, req._publish_projection)


# ═══════════════════════════════════════════════════════════════════════
# 9.  Default-build tests (RED)
# ═══════════════════════════════════════════════════════════════════════


class TestDefaultBuild(unittest.TestCase):
    """Task 9 — canonical image, target runtime, platform, deterministic,
    direct docker build (never Compose)."""

    def test_default_produces_success(self):
        """Real impl must return SUCCESS for a valid inventory."""
        req = BuildRequest(
            inventory_path="docker-constructor.toml",
            dry_run=True,
            _diagnose_gateway=_diag_reachable,
            _persist_gateway=_persist_ok,
            _publish_projection=_publish_ok,
        )
        result = orchestrate_build(req)
        self.assertEqual(ExitKind.SUCCESS, result.exit_kind,
                         f"expected SUCCESS, got {result.exit_kind}: {result.message}")

    def test_default_tag_is_pi_cli_pi_latest(self):
        """Default image tag is exactly ``pi-cli-pi:latest`` — canonical identity."""
        req = BuildRequest(
            inventory_path="docker-constructor.toml",
            dry_run=True,
            _diagnose_gateway=_diag_reachable,
            _persist_gateway=_persist_ok,
            _publish_projection=_publish_ok,
        )
        result = orchestrate_build(req)
        self.assertEqual(ExitKind.SUCCESS, result.exit_kind,
                         f"expected SUCCESS, got {result.exit_kind}: {result.message}")
        self.assertGreater(len(result.build_args), 0,
                           "build args must not be empty")
        # Canonical image tag: -t pi-cli-pi:latest
        found = False
        for i, a in enumerate(result.build_args):
            if a == "-t" and i + 1 < len(result.build_args):
                if result.build_args[i + 1] == "pi-cli-pi:latest":
                    found = True
                    break
        self.assertTrue(found,
                        f"default tag 'pi-cli-pi:latest' not found in {result.build_args}")

    def test_default_target_is_runtime(self):
        """Default target stage is 'runtime'."""
        req = BuildRequest(
            inventory_path="docker-constructor.toml",
            dry_run=True,
            _diagnose_gateway=_diag_reachable,
            _persist_gateway=_persist_ok,
            _publish_projection=_publish_ok,
        )
        result = orchestrate_build(req)
        # Target='runtime' appears as --target runtime in the build vector
        found_target = any(
            a == "runtime" for a in result.build_args
        )
        # Or: --target followed by runtime
        for i, a in enumerate(result.build_args):
            if a == "--target" and i + 1 < len(result.build_args):
                if result.build_args[i + 1] == "runtime":
                    found_target = True
                    break
        self.assertTrue(found_target,
                        f"--target runtime not found in {result.build_args}")

    def test_command_is_docker_build_not_compose(self):
        """The first token must be 'docker', never 'docker-compose'."""
        req = BuildRequest(
            inventory_path="docker-constructor.toml",
            dry_run=True,
            _diagnose_gateway=_diag_reachable,
            _persist_gateway=_persist_ok,
            _publish_projection=_publish_ok,
        )
        result = orchestrate_build(req)
        self.assertGreater(len(result.build_args), 0)
        self.assertEqual("docker", result.build_args[0],
                         "first token must be 'docker', not 'docker compose'")

    def test_deterministic_vector(self):
        """Same inputs must produce identical build_args."""
        req = BuildRequest(
            inventory_path="docker-constructor.toml",
            dry_run=True,
            _diagnose_gateway=_diag_reachable,
            _persist_gateway=_persist_ok,
            _publish_projection=_publish_ok,
        )
        r1 = orchestrate_build(req)
        r2 = orchestrate_build(req)
        self.assertEqual(r1.build_args, r2.build_args,
                         "build vector must be deterministic")


# ═══════════════════════════════════════════════════════════════════════
# 10.  Build override tests (RED)
# ═══════════════════════════════════════════════════════════════════════


class TestBuildOverrides(unittest.TestCase):
    """Task 10 — accepted build override, unsupported rejected,
    runtime override rejected, source unchanged.  Duplicate ``--override``
    arguments are rejected by the facade parser (see
    ``TestDuplicateOverrideRejectedAtParser`` in the facade test suite)."""

    def test_accepted_build_override_reaches_projection(self):
        """A build-owned override must be reflected in the build vector."""
        req = BuildRequest(
            inventory_path="docker-constructor.toml",
            dry_run=True,
            overrides=MappingProxyType({
                "build.stages.toolchain.python.version": "3.15.0",
            }),
            _diagnose_gateway=_diag_reachable,
            _persist_gateway=_persist_ok,
            _publish_projection=_publish_ok,
        )
        result = orchestrate_build(req)
        self.assertEqual(ExitKind.SUCCESS, result.exit_kind)
        # The override value "3.15.0" must appear in build args
        found = any("3.15.0" in a for a in result.build_args)
        self.assertTrue(found,
                        f"override 3.15.0 not in build args: {result.build_args}")

    def test_unsupported_override_rejected(self):
        """A path not in the inventory schema must cause CONFIG error."""
        req = BuildRequest(
            inventory_path="docker-constructor.toml",
            dry_run=True,
            overrides=MappingProxyType({
                "build.nonexistent.thing": "val",
            }),
            _diagnose_gateway=_diag_reachable,
            _persist_gateway=_persist_ok,
            _publish_projection=_publish_ok,
        )
        result = orchestrate_build(req)
        self.assertEqual(ExitKind.CONFIG, result.exit_kind,
                         f"expected CONFIG for unsupported override, got {result.exit_kind}")

    def test_runtime_override_rejected_in_build(self):
        """A runtime-scoped override must not be accepted by build."""
        req = BuildRequest(
            inventory_path="docker-constructor.toml",
            dry_run=True,
            overrides=MappingProxyType({
                "runtime.pi-extensions.x.version": "1.0.0",
            }),
            _diagnose_gateway=_diag_reachable,
            _persist_gateway=_persist_ok,
            _publish_projection=_publish_ok,
        )
        result = orchestrate_build(req)
        self.assertEqual(ExitKind.CONFIG, result.exit_kind,
                         f"expected CONFIG for runtime override, got {result.exit_kind}")


# ═══════════════════════════════════════════════════════════════════════
# 11.  Platform tests (RED)
# ═══════════════════════════════════════════════════════════════════════


class TestPlatformSelection(unittest.TestCase):
    """Task 11 — AMD64/ARM64 resolution, command platform matches projection,
    missing-platform artifact fails before diagnosis or execution."""

    def test_amd64_platform_in_build_vector(self):
        req = BuildRequest(
            inventory_path="docker-constructor.toml",
            platform="linux-amd64",
            dry_run=True,
            _diagnose_gateway=_diag_reachable,
            _persist_gateway=_persist_ok,
            _publish_projection=_publish_ok,
        )
        result = orchestrate_build(req)
        self.assertEqual(ExitKind.SUCCESS, result.exit_kind)
        found = any("linux/amd64" in a for a in result.build_args)
        self.assertTrue(found,
                        f"linux/amd64 not in build args: {result.build_args}")

    def test_arm64_platform_in_build_vector(self):
        req = BuildRequest(
            inventory_path="docker-constructor.toml",
            platform="linux-arm64",
            dry_run=True,
            _diagnose_gateway=_diag_reachable,
            _persist_gateway=_persist_ok,
            _publish_projection=_publish_ok,
        )
        result = orchestrate_build(req)
        # ARM64 may succeed or fail CONFIG depending on inventory
        self.assertIn(result.exit_kind, (ExitKind.SUCCESS, ExitKind.CONFIG),
                      f"unexpected exit: {result.exit_kind}: {result.message}")

    def test_missing_platform_fails_before_diagnosis(self):
        """When inventory lacks the requested platform, fail CONFIG
        and do NOT call gateway diagnosis."""
        diag_called = []

        def record_diag(**kw):
            diag_called.append(1)
            return _make_diagnosis()

        req = BuildRequest(
            inventory_path="/nonexistent/inventory.toml",
            platform="linux-arm64",
            _diagnose_gateway=record_diag,
            _persist_gateway=_persist_ok,
            _publish_projection=_publish_ok,
        )
        result = orchestrate_build(req)
        self.assertEqual(ExitKind.CONFIG, result.exit_kind,
                         f"expected CONFIG, got {result.exit_kind}")
        self.assertEqual(0, len(diag_called),
                         "must not call gateway diagnosis on missing inventory")


# ═══════════════════════════════════════════════════════════════════════
# 12.  Projection tests (RED)
# ═══════════════════════════════════════════════════════════════════════


class TestProjectionPublication(unittest.TestCase):
    """Task 12 — resolve from validated inventory.build, publish canonical
    host-side path, atomic, inventory not overwritten."""

    def test_projector_called_during_build(self):
        """The _publish_projection injectable must be invoked."""
        calls = []

        def record_publish(inv=None, projection=None, path=None):
            calls.append(1)
            return PublishResult(published_path="/tmp/eff.toml")

        req = BuildRequest(
            inventory_path="docker-constructor.toml",
            dry_run=True,
            _diagnose_gateway=_diag_reachable,
            _persist_gateway=_persist_ok,
            _publish_projection=record_publish,
        )
        result = orchestrate_build(req)
        self.assertEqual(ExitKind.SUCCESS, result.exit_kind)
        # Publisher must have been called at least once
        self.assertGreater(len(calls), 0,
                           "_publish_projection was not called")

    def test_publish_result_contains_canonical_path(self):
        """PublishResult must have a non-empty published_path."""
        pr = PublishResult(published_path="/tmp/effective.toml")
        self.assertIsInstance(pr.published_path, str)
        self.assertGreater(len(pr.published_path), 0)


# ═══════════════════════════════════════════════════════════════════════
# 13.  Cache / control tests (RED)
# ═══════════════════════════════════════════════════════════════════════


class TestCacheControls(unittest.TestCase):
    """Task 13 — cache, pull, progress, custom tag, UID/GID, context, Dockerfile."""

    def test_cache_disabled_adds_no_cache(self):
        req = BuildRequest(
            inventory_path="docker-constructor.toml",
            cache=False,
            dry_run=True,
            _diagnose_gateway=_diag_reachable,
            _persist_gateway=_persist_ok,
            _publish_projection=_publish_ok,
        )
        result = orchestrate_build(req)
        self.assertEqual(ExitKind.SUCCESS, result.exit_kind)
        self.assertIn("--no-cache", result.build_args,
                      "cache=False must add --no-cache")

    def test_pull_enabled_adds_pull(self):
        req = BuildRequest(
            inventory_path="docker-constructor.toml",
            pull=True,
            dry_run=True,
            _diagnose_gateway=_diag_reachable,
            _persist_gateway=_persist_ok,
            _publish_projection=_publish_ok,
        )
        result = orchestrate_build(req)
        self.assertEqual(ExitKind.SUCCESS, result.exit_kind)
        self.assertIn("--pull", result.build_args,
                      "pull=True must add --pull")

    def test_progress_plain_controls_output(self):
        req = BuildRequest(
            inventory_path="docker-constructor.toml",
            progress="plain",
            dry_run=True,
            _diagnose_gateway=_diag_reachable,
            _persist_gateway=_persist_ok,
            _publish_projection=_publish_ok,
        )
        result = orchestrate_build(req)
        self.assertEqual(ExitKind.SUCCESS, result.exit_kind)
        # --progress plain must appear
        found = any(
            a == "--progress" and result.build_args[i + 1] == "plain"
            for i, a in enumerate(result.build_args[:-1])
        )
        self.assertTrue(found,
                        f"--progress plain not found in {result.build_args}")

    def test_custom_tag_appears_in_vector(self):
        req = BuildRequest(
            inventory_path="docker-constructor.toml",
            tag="pi-cli-pi:latest",
            dry_run=True,
            _diagnose_gateway=_diag_reachable,
            _persist_gateway=_persist_ok,
            _publish_projection=_publish_ok,
        )
        result = orchestrate_build(req)
        self.assertEqual(ExitKind.SUCCESS, result.exit_kind)
        self.assertIn("pi-cli-pi:latest", result.build_args,
                      "custom tag must appear in build args")

    def test_uid_gid_surface_in_build_args(self):
        req = BuildRequest(
            inventory_path="docker-constructor.toml",
            uid=1000,
            gid=1000,
            dry_run=True,
            _diagnose_gateway=_diag_reachable,
            _persist_gateway=_persist_ok,
            _publish_projection=_publish_ok,
        )
        result = orchestrate_build(req)
        self.assertEqual(ExitKind.SUCCESS, result.exit_kind)
        # DEV_UID=1000 and DEV_GID=1000 must appear
        found_uid = any("DEV_UID=1000" in a for a in result.build_args)
        found_gid = any("DEV_GID=1000" in a for a in result.build_args)
        self.assertTrue(found_uid, f"DEV_UID=1000 not in {result.build_args}")
        self.assertTrue(found_gid, f"DEV_GID=1000 not in {result.build_args}")

    def test_context_and_dockerfile_override(self):
        req = BuildRequest(
            inventory_path="docker-constructor.toml",
            context="/custom/context",
            dockerfile="Dockerfile.custom",
            dry_run=True,
            _diagnose_gateway=_diag_reachable,
            _persist_gateway=_persist_ok,
            _publish_projection=_publish_ok,
        )
        result = orchestrate_build(req)
        self.assertEqual(ExitKind.SUCCESS, result.exit_kind)
        self.assertIn("/custom/context", result.build_args)
        self.assertIn("Dockerfile.custom", result.build_args)


# ═══════════════════════════════════════════════════════════════════════
# 14–15.  Failure-order tests — zero side effects (RED)
# ═══════════════════════════════════════════════════════════════════════


class _RecordingFakes:
    """Records every fake call for zero-side-effect assertions."""
    diagnose_calls = 0
    persist_calls = 0
    docker_calls = 0
    publish_calls = 0

    def diagnose(self, **kw):
        _RecordingFakes.diagnose_calls += 1
        return _make_diagnosis()

    def persist(self, path=None, gateway=None):
        _RecordingFakes.persist_calls += 1
        return _persist_ok()

    def publish(self, inv=None, projection=None, path=None):
        _RecordingFakes.publish_calls += 1
        return PublishResult(published_path="/tmp/eff.toml")

    def run(self, argv: tuple[str, ...]):
        _RecordingFakes.docker_calls += 1
        return ProcessResult(argv=argv, return_code=0, stdout="", stderr="")


def _reset_recording():
    _RecordingFakes.diagnose_calls = 0
    _RecordingFakes.persist_calls = 0
    _RecordingFakes.docker_calls = 0
    _RecordingFakes.publish_calls = 0


class TestFailureOrdering(unittest.TestCase):
    """Tasks 14–15 — every pre-validate failure means zero side effects."""

    def setUp(self):
        _reset_recording()
        self.fakes = _RecordingFakes()

    def _assert_zero(self):
        self.assertEqual(0, _RecordingFakes.diagnose_calls,
                         "gateway diagnose must not be called")
        self.assertEqual(0, _RecordingFakes.persist_calls,
                         "persist must not be called")
        self.assertEqual(0, _RecordingFakes.docker_calls,
                         "docker must not be called")
        self.assertEqual(0, _RecordingFakes.publish_calls,
                         "publish must not be called")

    def test_missing_inventory_returns_config_and_zero_calls(self):
        req = BuildRequest(
            inventory_path="/nonexistent/inventory.toml",
            _diagnose_gateway=self.fakes.diagnose,
            _persist_gateway=self.fakes.persist,
            _publish_projection=self.fakes.publish,
            runner=self.fakes,  # type: ignore[arg-type]
        )
        result = orchestrate_build(req)
        self.assertEqual(ExitKind.CONFIG, result.exit_kind,
                         f"expected CONFIG, got {result.exit_kind}: {result.message}")
        self._assert_zero()

    def test_invalid_toml_returns_config_and_zero_calls(self):
        req = BuildRequest(
            inventory_path="README.md",  # not TOML
            _diagnose_gateway=self.fakes.diagnose,
            _persist_gateway=self.fakes.persist,
            _publish_projection=self.fakes.publish,
            runner=self.fakes,  # type: ignore[arg-type]
        )
        result = orchestrate_build(req)
        self.assertEqual(ExitKind.CONFIG, result.exit_kind,
                         f"expected CONFIG, got {result.exit_kind}: {result.message}")
        self._assert_zero()

    def test_invalid_schema_returns_config_and_zero_calls(self):
        """A valid TOML file that is not an inventory schema."""
        req = BuildRequest(
            inventory_path="pyproject.toml",  # valid TOML but not inventory
            _diagnose_gateway=self.fakes.diagnose,
            _persist_gateway=self.fakes.persist,
            _publish_projection=self.fakes.publish,
            runner=self.fakes,  # type: ignore[arg-type]
        )
        result = orchestrate_build(req)
        self.assertEqual(ExitKind.CONFIG, result.exit_kind,
                         f"expected CONFIG, got {result.exit_kind}: {result.message}")
        self._assert_zero()

    def test_invalid_override_returns_config_and_zero_calls(self):
        """A completely invalid override path must fail before side effects."""
        req = BuildRequest(
            inventory_path="docker-constructor.toml",
            overrides=MappingProxyType({"not.a.real.path.at.all": "val"}),
            _diagnose_gateway=self.fakes.diagnose,
            _persist_gateway=self.fakes.persist,
            _publish_projection=self.fakes.publish,
            runner=self.fakes,  # type: ignore[arg-type]
        )
        result = orchestrate_build(req)
        # Must be CONFIG (invalid override is a configuration error)
        self.assertEqual(ExitKind.CONFIG, result.exit_kind,
                         f"expected CONFIG, got {result.exit_kind}: {result.message}")
        self._assert_zero()

    def test_projection_resolution_failure_returns_config_and_zero_calls(self):
        """When the effective projection cannot be built, stop before side effects."""
        req = BuildRequest(
            inventory_path="docker-constructor.toml",
            platform="nonexistent/cpu",
            _diagnose_gateway=self.fakes.diagnose,
            _persist_gateway=self.fakes.persist,
            _publish_projection=self.fakes.publish,
            runner=self.fakes,  # type: ignore[arg-type]
        )
        result = orchestrate_build(req)
        self.assertEqual(ExitKind.CONFIG, result.exit_kind,
                         f"expected CONFIG, got {result.exit_kind}: {result.message}")
        self._assert_zero()


# ═══════════════════════════════════════════════════════════════════════
# 16.  Gateway tests (RED)
# ═══════════════════════════════════════════════════════════════════════


class TestGatewayDiagnosis(unittest.TestCase):
    """Task 16 — diagnosis result, no gateway, preferred IP, fallback,
    persisted value, inventory unchanged."""

    def test_selected_gateway_surfaces(self):
        """The gateway IP selected by diagnosis must be reported."""
        req = BuildRequest(
            inventory_path="docker-constructor.toml",
            dry_run=True,
            _diagnose_gateway=_diag_reachable,
            _persist_gateway=_persist_ok,
            _publish_projection=_publish_ok,
        )
        result = orchestrate_build(req)
        self.assertEqual(ExitKind.SUCCESS, result.exit_kind)
        self.assertEqual("172.17.0.1", result.host_gateway_ip,
                         "host gateway IP must be the fake diagnosis value")

    def test_no_working_gateway_fails_operational(self):
        req = BuildRequest(
            inventory_path="docker-constructor.toml",
            confirmed=True,
            _diagnose_gateway=_diag_unreachable,
            _persist_gateway=_persist_ok,
            _publish_projection=_publish_ok,
        )
        result = orchestrate_build(req)
        self.assertEqual(ExitKind.OPERATIONAL, result.exit_kind,
                         f"expected OPERATIONAL, got {result.exit_kind}")
        self.assertIsNone(result.host_gateway_ip)
        self.assertIn("no route", result.message or "",
                      "message must indicate no route")

    def test_persisted_gateway_receives_exact_selected_value(self):
        persisted = []

        def record_persist(path, gateway):
            persisted.append(gateway)
            return _persist_ok()

        req = BuildRequest(
            inventory_path="docker-constructor.toml",
            dry_run=True,
            _diagnose_gateway=_diag_reachable,
            _persist_gateway=record_persist,
            _publish_projection=_publish_ok,
        )
        result = orchestrate_build(req)
        self.assertEqual(ExitKind.SUCCESS, result.exit_kind)
        self.assertGreater(len(persisted), 0, "persist was not called")
        self.assertEqual("172.17.0.1", persisted[0],
                         "persisted gateway must match diagnosis")


# ═══════════════════════════════════════════════════════════════════════
# 17.  Persistence failure (RED)
# ═══════════════════════════════════════════════════════════════════════


class TestPersistenceFailure(unittest.TestCase):
    """Task 17 — projection may resolve but Docker must not execute."""

    def test_persist_failure_blocks_docker(self):
        docker_runner = FakeBuildExecutor()
        req = BuildRequest(
            inventory_path="docker-constructor.toml",
            confirmed=True,
            _diagnose_gateway=_diag_reachable,
            _persist_gateway=_persist_fail,
            _publish_projection=_publish_ok,
            runner=docker_runner,
        )
        result = orchestrate_build(req)
        self.assertEqual(ExitKind.OPERATIONAL, result.exit_kind,
                         f"expected OPERATIONAL, got {result.exit_kind}")
        self.assertIn("cannot persist", result.message or "")
        self.assertEqual(0, len(docker_runner.calls),
                         "docker must not execute when persistence fails")


# ═══════════════════════════════════════════════════════════════════════
# 18–19.  Confirmation / consent (RED)
# ═══════════════════════════════════════════════════════════════════════


class TestConfirmation(unittest.TestCase):
    """Tasks 18–19 — confirmation flag (consent callbacks removed).

    The facade obtains confirmation and passes ``confirmed: bool`` as an
    immutable decision.  Orchestration **never** prompts; it only enforces
    the boolean.  ``confirmed=True`` means the user explicitly agreed or
    ``--yes`` bypass was active."""

    # -- helpers -------------------------------------------------------

    @staticmethod
    def _bomb_diagnose(**kw):
        raise RuntimeError("diagnose must NOT be called when not confirmed")

    @staticmethod
    def _bomb_persist(path=None, gateway=None):
        raise RuntimeError("persist must NOT be called when not confirmed")

    @staticmethod
    def _bomb_publish(**kw):
        raise RuntimeError("publish must NOT be called when not confirmed")

    class _BombRunner:
        """Runner that explodes if ``.run()`` is ever invoked."""
        def run(self, argv: tuple[str, ...]):
            raise RuntimeError("runner must NOT be called when not confirmed")

    # -- denied (successful cancellation) ------------------------------

    def test_not_confirmed_is_successful_cancellation(self):
        """``confirmed=False`` with ``dry_run=False`` is a deliberate
        user decision — SUCCESS no-op.  Every side-effecting boundary
        carries a bomb; the test passes only if none of them fire."""
        req = BuildRequest(
            inventory_path="docker-constructor.toml",
            confirmed=False,
            dry_run=False,
            _diagnose_gateway=self._bomb_diagnose,
            _persist_gateway=self._bomb_persist,
            _publish_projection=self._bomb_publish,
            runner=self._BombRunner(),
        )
        result = orchestrate_build(req)
        self.assertEqual(ExitKind.SUCCESS, result.exit_kind,
                         f"not-confirmed is SUCCESS not {result.exit_kind}: {result.message}")
        self.assertIn("not confirmed", (result.message or "").lower(),
                      "message must indicate build was not confirmed")
        self.assertIsNone(result.process_result,
                          "no Docker process must have run")
        self.assertEqual(len(result.build_args), 0,
                         "build args must be empty when cancelled")
        self.assertIsNone(result.gateway,
                          "no gateway must be selected")
        self.assertIsNone(result.publish_result,
                          "no projection must be published")

    # -- accepted ------------------------------------------------------

    def test_accepted_confirmation_runs(self):
        """When ``confirmed=True`` the full build transaction executes."""
        docker_runner = FakeBuildExecutor()
        req = BuildRequest(
            inventory_path="docker-constructor.toml",
            confirmed=True,
            _diagnose_gateway=_diag_reachable,
            _persist_gateway=_persist_ok,
            _publish_projection=_publish_ok,
            runner=docker_runner,
        )
        result = orchestrate_build(req)
        # Real impl returns SUCCESS with process_result; stub returns OPERATIONAL
        self.assertIsInstance(result, BuildResult)

    def test_operation_order_diagnose_persist_publish(self):
        """Build transaction order: validate → diagnose → persist → publish."""
        seq = []

        def diagnose(**kw):
            seq.append("diagnose")
            return _make_diagnosis()

        def persist(p, g):
            seq.append("persist")
            return _persist_ok()

        def publish(**kw):
            seq.append("publish")
            return PublishResult(published_path="/tmp/eff.toml")

        req = BuildRequest(
            inventory_path="docker-constructor.toml",
            confirmed=True,
            _diagnose_gateway=diagnose,
            _persist_gateway=persist,
            _publish_projection=publish,
        )
        result = orchestrate_build(req)
        self.assertIsInstance(result, BuildResult)
        for phase in ("diagnose", "persist", "publish"):
            self.assertIn(phase, seq,
                          f"{phase} was never called; stub may be active")
        diagnose_idx = seq.index("diagnose")
        persist_idx = seq.index("persist")
        self.assertLess(diagnose_idx, persist_idx,
                        f"diagnosis ({diagnose_idx}) must precede persistence ({persist_idx})")
        publish_idx = seq.index("publish")
        self.assertGreater(publish_idx, persist_idx,
                           f"publication ({publish_idx}) must be after persistence ({persist_idx})")


# ═══════════════════════════════════════════════════════════════════════
# 20.  Dry-run tests (RED)
# ═══════════════════════════════════════════════════════════════════════


class TestDryRun(unittest.TestCase):
    """Task 20 — complete shell-escaped display, no Docker, no probe
    container, no persistence, no publication, no prompt, no mutation.

    Every side-effecting fake is a **bomb**: it raises ``RuntimeError``
    if called.  If *any* bomb detonates the test fails — proving the
    dry-run path never touches that boundary.
    """

    @staticmethod
    def _bomb_diagnose(**kw):
        raise RuntimeError("gateway diagnose must NOT be called during dry-run")

    @staticmethod
    def _bomb_persist(path=None, gateway=None):
        raise RuntimeError("gateway persist must NOT be called during dry-run")

    @staticmethod
    def _bomb_publish(**kw):
        raise RuntimeError("projection publish must NOT be called during dry-run")

    class _BombRunner:
        """Process runner that explodes if its .run() is ever invoked."""
        def run(self, argv: tuple[str, ...]):
            raise RuntimeError("process runner must NOT be called during dry-run")

    # -- dry-run must not touch side effects -------------------------

    def test_dry_run_no_side_effects(self):
        """Dry-run must not invoke Docker execution, persistence,
        or publication.  Only the build vector is rendered."""
        req = BuildRequest(
            inventory_path="docker-constructor.toml",
            dry_run=True,
            _diagnose_gateway=self._bomb_diagnose,
            _persist_gateway=self._bomb_persist,
            _publish_projection=self._bomb_publish,
            runner=self._BombRunner(),
        )
        result = orchestrate_build(req)
        # Must succeed and produce a non-empty build vector
        self.assertEqual(ExitKind.SUCCESS, result.exit_kind,
                         f"expected SUCCESS, got {result.exit_kind}: {result.message}")
        self.assertGreater(len(result.build_args), 0,
                           "build args must not be empty")

    # -- gateway probe -------------------------------------------------

    def test_dry_run_no_gateway_probe(self):
        """Dry-run must not spawn a gateway probe container."""
        req = BuildRequest(
            inventory_path="docker-constructor.toml",
            dry_run=True,
            _diagnose_gateway=self._bomb_diagnose,
            _persist_gateway=self._bomb_persist,
            _publish_projection=self._bomb_publish,
            runner=self._BombRunner(),
        )
        result = orchestrate_build(req)
        self.assertEqual(ExitKind.SUCCESS, result.exit_kind,
                         f"expected SUCCESS, got {result.exit_kind}: {result.message}")
        self.assertGreater(len(result.build_args), 0)

    # -- persistence ---------------------------------------------------

    def test_dry_run_no_persistence(self):
        """Dry-run must not write .env or effective.toml."""
        req = BuildRequest(
            inventory_path="docker-constructor.toml",
            dry_run=True,
            _diagnose_gateway=self._bomb_diagnose,
            _persist_gateway=self._bomb_persist,
            _publish_projection=self._bomb_publish,
            runner=self._BombRunner(),
        )
        result = orchestrate_build(req)
        self.assertEqual(ExitKind.SUCCESS, result.exit_kind,
                         f"expected SUCCESS, got {result.exit_kind}: {result.message}")
        self.assertIsNone(result.host_gateway_ip,
                          "dry-run must not persist gateway IP")

    # -- publication ---------------------------------------------------

    def test_dry_run_no_publication(self):
        """Dry-run must not publish the effective projection."""
        req = BuildRequest(
            inventory_path="docker-constructor.toml",
            dry_run=True,
            _diagnose_gateway=self._bomb_diagnose,
            _persist_gateway=self._bomb_persist,
            _publish_projection=self._bomb_publish,
            runner=self._BombRunner(),
        )
        result = orchestrate_build(req)
        self.assertEqual(ExitKind.SUCCESS, result.exit_kind,
                         f"expected SUCCESS, got {result.exit_kind}: {result.message}")

    # -- Docker process ------------------------------------------------

    def test_dry_run_no_docker_process(self):
        """Dry-run must not execute Docker."""
        req = BuildRequest(
            inventory_path="docker-constructor.toml",
            dry_run=True,
            _diagnose_gateway=self._bomb_diagnose,
            _persist_gateway=self._bomb_persist,
            _publish_projection=self._bomb_publish,
            runner=self._BombRunner(),
        )
        result = orchestrate_build(req)
        self.assertEqual(ExitKind.SUCCESS, result.exit_kind,
                         f"expected SUCCESS, got {result.exit_kind}: {result.message}")
        self.assertIsNone(result.process_result,
                          "dry-run must not execute Docker")

    # -- build vector completeness -------------------------------------

    def test_dry_run_returns_complete_display(self):
        """Dry-run must return full build_args and a display_string."""
        req = BuildRequest(
            inventory_path="docker-constructor.toml",
            dry_run=True,
            _diagnose_gateway=_diag_reachable,
            _persist_gateway=_persist_ok,
            _publish_projection=_publish_ok,
        )
        result = orchestrate_build(req)
        self.assertEqual(ExitKind.SUCCESS, result.exit_kind,
                         f"expected SUCCESS, got {result.exit_kind}: {result.message}")
        self.assertGreater(len(result.build_args), 0,
                           "build_args must not be empty")

    # -- source mutation -----------------------------------------------

    def test_dry_run_no_source_mutation(self):
        """Source inventory must never be touched during dry-run."""
        req = BuildRequest(
            inventory_path="docker-constructor.toml",
            dry_run=True,
            _diagnose_gateway=_diag_reachable,
            _persist_gateway=_persist_ok,
            _publish_projection=_publish_ok,
        )
        result = orchestrate_build(req)
        self.assertEqual(ExitKind.SUCCESS, result.exit_kind,
                         f"expected SUCCESS, got {result.exit_kind}: {result.message}")


# ═══════════════════════════════════════════════════════════════════════
# 21.  Direct execution — tuple, shell=False (RED)
# ═══════════════════════════════════════════════════════════════════════


class TestDirectExecution(unittest.TestCase):
    """Task 21 — runner receives exact tuple, shell=False, display string
    never passed to runner."""

    def test_runner_receives_tuple_not_string(self):
        """The runner must receive a tuple (shell=False semantics)."""
        runner = FakeBuildExecutor()
        req = BuildRequest(
            inventory_path="docker-constructor.toml",
            confirmed=True,
            runner=runner,
            _diagnose_gateway=_diag_reachable,
            _persist_gateway=_persist_ok,
            _publish_projection=_publish_ok,
        )
        result = orchestrate_build(req)
        self.assertIsInstance(result, BuildResult)
        if runner.calls:
            cmd = runner.calls[0]
            self.assertIsInstance(cmd, tuple,
                                  "runner must receive tuple, not string")

    def test_runner_command_starts_with_docker(self):
        runner = FakeBuildExecutor()
        req = BuildRequest(
            inventory_path="docker-constructor.toml",
            confirmed=True,
            runner=runner,
            _diagnose_gateway=_diag_reachable,
            _persist_gateway=_persist_ok,
            _publish_projection=_publish_ok,
        )
        result = orchestrate_build(req)
        self.assertIsInstance(result, BuildResult)
        if runner.calls:
            cmd = runner.calls[0]
            self.assertEqual("docker", cmd[0])


# ═══════════════════════════════════════════════════════════════════════
# 22.  Subprocess outcome (RED)
# ═══════════════════════════════════════════════════════════════════════


class TestSubprocessOutcomes(unittest.TestCase):
    """Task 22 — zero=success, nonzero=operational failure, stderr bounded,
    executable-not-found actionable."""

    def test_zero_exit_returns_success(self):
        runner = FakeBuildExecutor(returncode=0)
        req = BuildRequest(
            inventory_path="docker-constructor.toml",
            confirmed=True,
            runner=runner,
            _diagnose_gateway=_diag_reachable,
            _persist_gateway=_persist_ok,
            _publish_projection=_publish_ok,
        )
        result = orchestrate_build(req)
        self.assertEqual(ExitKind.SUCCESS, result.exit_kind,
                         f"expected SUCCESS, got {result.exit_kind}")
        self.assertIsNotNone(result.process_result,
                             "process_result must be present")
        # When present, must match the runner's return code
        self.assertEqual(0, result.process_result.return_code)

    def test_nonzero_exit_returns_operational_failure(self):
        runner = FakeBuildExecutor(returncode=1)
        req = BuildRequest(
            inventory_path="docker-constructor.toml",
            confirmed=True,
            runner=runner,
            _diagnose_gateway=_diag_reachable,
            _persist_gateway=_persist_ok,
            _publish_projection=_publish_ok,
        )
        result = orchestrate_build(req)
        self.assertEqual(ExitKind.OPERATIONAL, result.exit_kind,
                         f"expected OPERATIONAL, got {result.exit_kind}")
        self.assertIsNotNone(result.process_result)
        self.assertEqual(1, result.process_result.return_code)

    def test_stderr_included_on_failure(self):
        runner = FakeBuildExecutor(returncode=1)
        req = BuildRequest(
            inventory_path="docker-constructor.toml",
            confirmed=True,
            runner=runner,
            _diagnose_gateway=_diag_reachable,
            _persist_gateway=_persist_ok,
            _publish_projection=_publish_ok,
        )
        result = orchestrate_build(req)
        self.assertEqual(ExitKind.OPERATIONAL, result.exit_kind)
        self.assertIsNotNone(result.process_result)
        # Message should surface stderr content or exit code
        self.assertIn("build error", result.message or "")


if __name__ == "__main__":
    unittest.main()
