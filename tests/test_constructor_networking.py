"""RED-phase tests for ``docker.networking`` — Stage 7.1 diagnosis.

Covers rootful/rootless detection, candidate ordering, LAN-IP
discovery, probe results, diagnosis orchestration, and DTO
immutability.  All tests use injected fakes — no Docker daemon, no
systemd, no network access.

Requirements: 7.1 (detection, candidates, probes, diagnosis).

See ``tests/test_networking.py`` for the full GREEN‑phase suite
(override planning/application, persistence, import boundaries).
"""

from __future__ import annotations

import dataclasses
import subprocess
import unittest
from typing import Optional

from docker.networking import (
    DockerDetectionError,
    DockerMode,
    GatewayDiagnosis,
    ProbeResult,
    candidate_gateways,
    detect_docker_mode,
    detect_lan_ip,
    diagnose_gateway,
    probe_gateway,
)


# ---------------------------------------------------------------------------
# Deterministic fakes (requirement 7)
# ---------------------------------------------------------------------------

def _completed(
    rc: int = 0,
    stdout: str = "",
    stderr: str = "",
) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess([], rc, stdout=stdout, stderr=stderr)


def _fake_run(
    *,
    docker_info_stdout: str = "Server Version: 27.0.0\n",
    docker_info_rc: int = 0,
    docker_info_raises: Optional[Exception] = None,
    hostname_stdout: str = "192.168.1.10",
    hostname_raises: Optional[Exception] = None,
    ip_route_stdout: str = "",
    ip_route_raises: Optional[Exception] = None,
    probe_stdouts: Optional[list[str]] = None,
    probe_rcs: Optional[list[int]] = None,
    probe_raises: Optional[list[Optional[Exception]]] = None,
) -> callable:
    """Build a fake subprocess runner with per-command behaviour."""

    _call = [0]  # mutable counter for probe sequencing

    def run(cmd: list[str]) -> subprocess.CompletedProcess[str]:
        key = cmd[0] if cmd else ""

        if key == "docker" and len(cmd) >= 2 and cmd[1] == "info":
            if docker_info_raises:
                raise docker_info_raises
            return _completed(docker_info_rc,
                              stdout=docker_info_stdout,
                              stderr="" if docker_info_rc == 0 else "permission denied")

        if key == "docker" and len(cmd) >= 2 and cmd[1] == "run":
            idx = _call[0]
            _call[0] += 1
            if probe_raises and idx < len(probe_raises) and probe_raises[idx]:
                raise probe_raises[idx]  # type: ignore[operator]
            stdout = ""
            if probe_stdouts and idx < len(probe_stdouts):
                stdout = probe_stdouts[idx]
            rc = 0
            if probe_rcs and idx < len(probe_rcs):
                rc = probe_rcs[idx]
            return _completed(rc, stdout=stdout, stderr="")

        if key == "hostname":
            if hostname_raises:
                raise hostname_raises
            return _completed(0, stdout=hostname_stdout)

        if key == "ip":
            if ip_route_raises:
                raise ip_route_raises
            return _completed(0, stdout=ip_route_stdout)

        return _completed(0, stdout="")

    return run


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
# 8. Rootless-detection tests
# ---------------------------------------------------------------------------


class TestDetectDockerMode(unittest.TestCase):
    """Requirement 8 — detection returns ``DockerMode`` or raises a
    structured domain error.  Does not print or select an exit code."""

    # -- rootless recognised -------------------------------------------------

    def test_rootless_recognised(self):
        run = _fake_run(docker_info_stdout="  rootless: true\n  other: val")
        self.assertIs(detect_docker_mode(_run=run), DockerMode.ROOTLESS)

    def test_rootless_case_insensitive(self):
        run = _fake_run(docker_info_stdout="  RootLess: True\n")
        self.assertIs(detect_docker_mode(_run=run), DockerMode.ROOTLESS)

    # -- rootful when absent -------------------------------------------------

    def test_rootful_when_absent(self):
        run = _fake_run(docker_info_stdout="  Server Version: 27.0.1\n  OSType: linux\n")
        self.assertIs(detect_docker_mode(_run=run), DockerMode.ROOTFUL)

    # -- command failure → domain error --------------------------------------

    def test_nonzero_exit_raises_detection_error(self):
        run = _fake_run(docker_info_stdout="", docker_info_rc=1)
        with self.assertRaises(DockerDetectionError) as ctx:
            detect_docker_mode(_run=run)
        self.assertIn("permission denied", str(ctx.exception))

    def test_docker_not_found_raises_detection_error(self):
        run = _fake_run(docker_info_raises=FileNotFoundError("docker"))
        with self.assertRaises(DockerDetectionError) as ctx:
            detect_docker_mode(_run=run)
        self.assertIn("not found", str(ctx.exception))

    # -- does not print ------------------------------------------------------

    def test_detection_does_not_print(self):
        import io, sys
        run = _fake_run(docker_info_stdout="Server: 27.0.0\n")
        buf = io.StringIO()
        old = sys.stderr
        try:
            sys.stderr = buf
            detect_docker_mode(_run=run)
        finally:
            sys.stderr = old
        self.assertEqual(buf.getvalue(), "")

    def test_detection_failure_does_not_print(self):
        import io, sys
        run = _fake_run(docker_info_stdout="", docker_info_rc=1)
        buf = io.StringIO()
        old = sys.stderr
        try:
            sys.stderr = buf
            with self.assertRaises(DockerDetectionError):
                detect_docker_mode(_run=run)
        finally:
            sys.stderr = old
        self.assertEqual(buf.getvalue(), "")

    # -- no exit code --------------------------------------------------------

    def test_detection_does_not_select_exit_code(self):
        """Failure raises an exception — callers map to exit codes."""
        run = _fake_run(docker_info_stdout="", docker_info_rc=1)
        try:
            detect_docker_mode(_run=run)
        except DockerDetectionError:
            pass  # exception, not sys.exit


# ---------------------------------------------------------------------------
# 9. Candidate-order tests
# ---------------------------------------------------------------------------


class TestCandidateGateways(unittest.TestCase):
    """Requirement 9 — ordered candidate lists, deduplication, absent
    LAN IP."""

    def test_rootful_host_gateway_then_lan(self):
        got = candidate_gateways(DockerMode.ROOTFUL, lan_ip="192.168.1.5")
        self.assertEqual(got, ("host-gateway", "192.168.1.5"))

    def test_rootful_without_lan(self):
        got = candidate_gateways(DockerMode.ROOTFUL, lan_ip=None)
        self.assertEqual(got, ("host-gateway",))

    def test_rootless_10_0_2_2_then_lan_then_host_gateway(self):
        got = candidate_gateways(DockerMode.ROOTLESS, lan_ip="192.168.1.5")
        self.assertEqual(got, ("10.0.2.2", "192.168.1.5", "host-gateway"))

    def test_rootless_without_lan(self):
        got = candidate_gateways(DockerMode.ROOTLESS, lan_ip=None)
        self.assertEqual(got, ("10.0.2.2", "host-gateway"))

    # -- deduplication -------------------------------------------------------

    def test_dedup_rootless_lan_equals_10_0_2_2(self):
        got = candidate_gateways(DockerMode.ROOTLESS, lan_ip="10.0.2.2")
        self.assertEqual(got, ("10.0.2.2", "host-gateway"))

    def test_dedup_rootful_lan_equals_host_gateway(self):
        got = candidate_gateways(DockerMode.ROOTFUL, lan_ip="host-gateway")
        self.assertEqual(got, ("host-gateway",))

    def test_dedup_rootless_lan_equals_host_gateway(self):
        got = candidate_gateways(DockerMode.ROOTLESS, lan_ip="host-gateway")
        self.assertEqual(got, ("10.0.2.2", "host-gateway"))

    # -- returns tuple -------------------------------------------------------

    def test_always_returns_tuple(self):
        for mode in DockerMode:
            for ip in (None, "10.0.0.1"):
                self.assertIsInstance(candidate_gateways(mode, ip), tuple)


# ---------------------------------------------------------------------------
# 10. LAN-IP detection tests
# ---------------------------------------------------------------------------


class TestDetectLanIp(unittest.TestCase):
    """Requirement 10 — hostname -I first, ip route fallback, graceful
    failure."""

    def test_first_word_from_hostname_i(self):
        run = _fake_run(hostname_stdout="192.168.1.10 172.17.0.1")
        self.assertEqual(detect_lan_ip(_run=run), "192.168.1.10")

    def test_hostname_empty_falls_back_to_ip_route(self):
        run = _fake_run(
            hostname_stdout=" \n",
            ip_route_stdout="default via 10.0.0.1 dev eth0 src 10.0.0.55",
        )
        self.assertEqual(detect_lan_ip(_run=run), "10.0.0.55")

    def test_hostname_not_found_falls_back(self):
        run = _fake_run(
            hostname_raises=FileNotFoundError("hostname"),
            ip_route_stdout="default via 10.0.0.1 dev eth0 src 10.0.0.55",
        )
        self.assertEqual(detect_lan_ip(_run=run), "10.0.0.55")

    def test_both_fail_returns_none(self):
        run = _fake_run(
            hostname_raises=FileNotFoundError("hostname"),
            ip_route_raises=FileNotFoundError("ip"),
        )
        self.assertIsNone(detect_lan_ip(_run=run))

    def test_no_src_in_ip_route_returns_none(self):
        run = _fake_run(
            hostname_stdout="",
            ip_route_stdout="default via 10.0.0.1 dev eth0\n",
        )
        self.assertIsNone(detect_lan_ip(_run=run))

    def test_process_failure_remains_structured(self):
        """detect_lan_ip never raises regardless of process state."""
        run = _fake_run(
            hostname_raises=OSError("broken pipe"),
            ip_route_raises=OSError("broken pipe"),
        )
        # Must not raise
        result = detect_lan_ip(_run=run)
        self.assertIsNone(result)


# ---------------------------------------------------------------------------
# 11. Probe-result tests
# ---------------------------------------------------------------------------


class TestProbeResultDto(unittest.TestCase):
    """Requirement 11 & 13 — ProbeResult immutability, field integrity."""

    def test_rejects_empty_candidate(self):
        with self.assertRaises(ValueError):
            ProbeResult(candidate="", ok=True, resolved_ip=None, detail="ok")

    def test_frozen(self):
        p = ProbeResult("gw", True, "1.2.3.4", "ok")
        with self.assertRaises(dataclasses.FrozenInstanceError):
            p.ok = False  # type: ignore[misc]

    def test_candidate_and_resolved_ip_distinct(self):
        """candidate is the probe target, resolved_ip is what the
        container resolved host.docker.internal to."""
        p = ProbeResult("10.0.2.2", True, "172.17.0.1", "ok")
        self.assertNotEqual(p.candidate, p.resolved_ip,
                            "candidate and resolved_ip must be distinct")


class TestProbeGateway(unittest.TestCase):
    """Requirement 11 — successful/failed probes, edge cases."""

    def test_successful_token_match(self):
        run = _fake_run(probe_stdouts=["RESOLVED_IP=172.17.0.1\nPROBE_OK"])
        result = probe_gateway("10.0.2.2", 9999, "OK_1", _run=run)
        self.assertTrue(result.ok)
        self.assertEqual(result.candidate, "10.0.2.2")
        self.assertEqual(result.resolved_ip, "172.17.0.1")

    def test_missing_token_not_ok(self):
        run = _fake_run(probe_stdouts=["RESOLVED_IP=172.17.0.1\n"], probe_rcs=[0])
        result = probe_gateway("10.0.2.2", 9999, "OK_1", _run=run)
        self.assertFalse(result.ok)

    def test_nonzero_process_status_not_ok(self):
        run = _fake_run(probe_stdouts=[""], probe_rcs=[1])
        result = probe_gateway("host-gateway", 9999, "T", _run=run)
        self.assertFalse(result.ok)
        self.assertIn("exit 1", result.detail)

    def test_missing_resolved_ip_with_ok_probe(self):
        """Successful probe without RESOLVED_IP still returns ok."""
        run = _fake_run(probe_stdouts=["PROBE_OK"])
        result = probe_gateway("host-gateway", 9999, "T", _run=run)
        self.assertTrue(result.ok)
        self.assertIsNone(result.resolved_ip)

    def test_detail_bounded(self):
        """Detail should not grow unbounded from a noisy container."""
        long_output = "x" * 500
        run = _fake_run(probe_stdouts=[long_output])
        result = probe_gateway("host-gateway", 9999, "T", _run=run)
        self.assertLessEqual(len(result.detail), 200)

    def test_resolved_ip_in_stderr(self):
        """RESOLVED_IP can appear on stderr."""
        def run(cmd):
            return _completed(0, stdout="", stderr="RESOLVED_IP=10.8.0.1\nPROBE_OK")
        result = probe_gateway("host-gateway", 9999, "T", _run=run)
        self.assertTrue(result.ok)
        self.assertEqual(result.resolved_ip, "10.8.0.1")

    def test_exception_during_probe(self):
        def run(_cmd):
            raise OSError("no space left on device")
        result = probe_gateway("gw", 9999, "T", _run=run)
        self.assertFalse(result.ok)
        self.assertIn("no space", result.detail)

    def test_uses_add_host_argument(self):
        seen: list[list[str]] = []
        def run(cmd):
            seen.append(cmd)
            return _completed(0, stdout="PROBE_OK")
        probe_gateway("192.168.1.1", 9999, "T", _run=run)
        self.assertTrue(any("host.docker.internal:192.168.1.1" in arg
                            for arg in seen[0]))


# ---------------------------------------------------------------------------
# 12. Diagnosis orchestration tests
# ---------------------------------------------------------------------------


class TestDiagnosisOrchestration(unittest.TestCase):
    """Requirement 12 — full diagnosis lifecycle."""

    def test_probe_server_starts_before_candidates(self):
        """Server must be started before any probe is attempted."""
        started_before_probe = []
        def run(cmd):
            if cmd[0] == "docker" and cmd[1] == "run":
                # Record that this is a probe call — server must already be started
                return _completed(0, stdout="PROBE_OK")
            if cmd[0] == "docker" and cmd[1] == "info":
                return _completed(0, stdout="Server: 27\n")
            if cmd[0] == "hostname":
                return _completed(0, stdout="10.0.0.5")
            return _completed(0)

        class TrackingServer:
            def __init__(self):
                self.started = False
                self.stopped = False
                self.token = "T"
                self.port = 9999
            def start(self):
                self.started = True
                started_before_probe.append(True)
                return self.port
            def stop(self):
                self.stopped = True

        server = TrackingServer()
        diagnose_gateway(_run=run, _host_probe_factory=lambda: server)
        self.assertTrue(server.started, "server must be started")
        self.assertTrue(any(started_before_probe))

    def test_every_candidate_tested_in_order(self):
        probed: list[str] = []
        def run(cmd):
            if cmd[0] == "docker" and cmd[1] == "run":
                # Extract candidate from --add-host
                for i, arg in enumerate(cmd):
                    if arg == "--add-host" and i + 1 < len(cmd):
                        hostdef = cmd[i + 1]
                        cand = hostdef.split(":")[-1] if ":" in hostdef else hostdef
                        probed.append(cand)
                        break
                return _completed(0, stdout="PROBE_OK")
            if cmd[0] == "docker" and cmd[1] == "info":
                return _completed(0, stdout="Server: 27\n")
            if cmd[0] == "hostname":
                return _completed(0, stdout="192.168.1.99")
            return _completed(0)

        diagnose_gateway(
            _run=run,
            _host_probe_factory=lambda: FakeHostProbeServer(token="X"),
        )
        # Rootful: host-gateway first, then LAN IP
        self.assertGreaterEqual(len(probed), 2)
        self.assertEqual(probed[0], "host-gateway")
        self.assertEqual(probed[1], "192.168.1.99")

    def test_first_successful_candidate_selected(self):
        """Second candidate succeeds, first fails."""
        def run(cmd):
            if cmd[0] == "docker" and cmd[1] == "run":
                for i, arg in enumerate(cmd):
                    if arg == "--add-host" and i + 1 < len(cmd):
                        hostdef = cmd[i + 1]
                        cand = hostdef.split(":")[-1]
                        if cand == "host-gateway":
                            return _completed(1, stderr="timeout")
                        return _completed(0, stdout="RESOLVED_IP=10.9.9.9\nPROBE_OK")
            if cmd[0] == "docker" and cmd[1] == "info":
                return _completed(0, stdout="Server: 27\n")
            if cmd[0] == "hostname":
                return _completed(0, stdout="192.168.1.5")
            return _completed(0)

        d = diagnose_gateway(
            _run=run,
            _host_probe_factory=lambda: FakeHostProbeServer(token="X"),
        )
        self.assertEqual(d.chosen_gateway, "192.168.1.5")
        self.assertEqual(d.host_gateway_ip, "10.9.9.9")

    def test_all_fail_yields_no_gateway(self):
        def run(cmd):
            if cmd[0] == "docker" and cmd[1] == "run":
                return _completed(1, stderr="connection refused")
            if cmd[0] == "docker" and cmd[1] == "info":
                return _completed(0, stdout="Server: 27\n")
            if cmd[0] == "hostname":
                return _completed(0, stdout="10.0.0.5")
            return _completed(0)

        d = diagnose_gateway(
            _run=run,
            _host_probe_factory=lambda: FakeHostProbeServer(token="X"),
        )
        self.assertIsNone(d.chosen_gateway)
        self.assertIsNone(d.host_gateway_ip)
        self.assertEqual(len(d.probes), 2)
        self.assertFalse(d.probes[0].ok)
        self.assertFalse(d.probes[1].ok)

    def test_server_stops_after_success(self):
        fake = FakeHostProbeServer()
        def run(cmd):
            if cmd[0] == "docker" and cmd[1] == "run":
                return _completed(0, stdout="PROBE_OK")
            if cmd[0] == "docker" and cmd[1] == "info":
                return _completed(0, stdout="Server: 27\n")
            if cmd[0] == "hostname":
                return _completed(0, stdout="10.0.0.5")
            return _completed(0)
        diagnose_gateway(_run=run, _host_probe_factory=lambda: fake)
        self.assertTrue(fake.stopped)

    def test_server_stops_after_failure(self):
        fake = FakeHostProbeServer()
        def run(cmd):
            if cmd[0] == "docker" and cmd[1] == "run":
                return _completed(1, stderr="timeout")
            if cmd[0] == "docker" and cmd[1] == "info":
                return _completed(0, stdout="Server: 27\n")
            if cmd[0] == "hostname":
                return _completed(0, stdout="")
            return _completed(0)
        diagnose_gateway(_run=run, _host_probe_factory=lambda: fake)
        self.assertTrue(fake.stopped)

    def test_diagnosis_does_not_install_override(self):
        """Diagnosis must not mutate filesystem or run systemctl."""
        ran_systemctl = []
        def run(cmd):
            if "systemctl" in (cmd[0] if cmd else ""):
                ran_systemctl.append(cmd)
            if cmd[0] == "docker" and cmd[1] == "run":
                return _completed(0, stdout="PROBE_OK")
            if cmd[0] == "docker" and cmd[1] == "info":
                return _completed(0, stdout="Server: 27\n")
            if cmd[0] == "hostname":
                return _completed(0, stdout="10.0.0.5")
            return _completed(0)

        d = diagnose_gateway(
            _run=run,
            _host_probe_factory=lambda: FakeHostProbeServer(token="X"),
        )
        self.assertEqual(ran_systemctl, [],
                         "diagnose_gateway must not invoke systemctl")
        # It should report that an override is NOT needed (rootful)
        self.assertFalse(d.override_needed)

    def test_rootless_mode_flows_to_diagnosis(self):
        def run(cmd):
            if cmd[0] == "docker" and cmd[1] == "run":
                return _completed(0, stdout="PROBE_OK")
            if cmd[0] == "docker" and cmd[1] == "info":
                return _completed(0, stdout="  rootless: true\n")
            if cmd[0] == "hostname":
                return _completed(0, stdout="")
            return _completed(0)

        d = diagnose_gateway(
            _run=run,
            _host_probe_factory=lambda: FakeHostProbeServer(token="X"),
        )
        self.assertIs(d.mode, DockerMode.ROOTLESS)
        self.assertTrue(d.rootless)  # convenience property
        # Rootless without override → override_needed
        self.assertTrue(d.override_needed)
        self.assertFalse(d.override_installed)


# ---------------------------------------------------------------------------
# 13. Immutable DTOs
# ---------------------------------------------------------------------------


class TestImmutableDtos(unittest.TestCase):
    """Requirement 13 — DockerMode, ProbeResult, GatewayDiagnosis immutability."""

    def test_docker_mode_is_enum(self):
        self.assertIsInstance(DockerMode.ROOTFUL, DockerMode)
        self.assertIsInstance(DockerMode.ROOTLESS, DockerMode)

    def test_probe_result_frozen(self):
        p = ProbeResult("g", True, "1.2.3.4", "ok")
        with self.assertRaises(dataclasses.FrozenInstanceError):
            p.ok = False  # type: ignore[misc]

    def test_gateway_diagnosis_frozen(self):
        d = GatewayDiagnosis(
            mode=DockerMode.ROOTFUL,
            probe_port=9000, probe_token="T", lan_ip=None,
            probes=(),
            chosen_gateway=None,
            override_installed=False, override_needed=False,
        )
        with self.assertRaises(dataclasses.FrozenInstanceError):
            d.chosen_gateway = "hacked"  # type: ignore[misc]

    def test_detection_error_is_domain_error(self):
        err = DockerDetectionError("test")
        self.assertIsInstance(err, RuntimeError)
        self.assertEqual(str(err), "test")


# ---------------------------------------------------------------------------
# 14. host_gateway_ip resolution
# ---------------------------------------------------------------------------


class TestHostGatewayIpResolution(unittest.TestCase):
    """Requirement 14 — host_gateway_ip precedence chain."""

    def test_resolved_ip_when_available(self):
        d = GatewayDiagnosis(
            mode=DockerMode.ROOTFUL,
            probe_port=9000, probe_token="T", lan_ip=None,
            probes=(ProbeResult("host-gateway", True, "10.0.0.1", "ok"),),
            chosen_gateway="host-gateway",
            override_installed=False, override_needed=False,
        )
        self.assertEqual(d.host_gateway_ip, "10.0.0.1")

    def test_fallback_to_candidate(self):
        d = GatewayDiagnosis(
            mode=DockerMode.ROOTFUL,
            probe_port=9000, probe_token="T", lan_ip=None,
            probes=(ProbeResult("host-gateway", True, None, "ok"),),
            chosen_gateway="host-gateway",
            override_installed=False, override_needed=False,
        )
        self.assertEqual(d.host_gateway_ip, "host-gateway")

    def test_none_when_no_candidate_succeeds(self):
        d = GatewayDiagnosis(
            mode=DockerMode.ROOTFUL,
            probe_port=9000, probe_token="T", lan_ip=None,
            probes=(ProbeResult("10.0.2.2", False, None, "timeout"),),
            chosen_gateway=None,
            override_installed=False, override_needed=False,
        )
        self.assertIsNone(d.host_gateway_ip)

    def test_none_when_chosen_but_not_ok(self):
        """Edge case: chosen_gateway is set but its ProbeResult is not ok."""
        d = GatewayDiagnosis(
            mode=DockerMode.ROOTFUL,
            probe_port=9000, probe_token="T", lan_ip=None,
            probes=(ProbeResult("host-gateway", False, "1.2.3.4", "refused"),),
            chosen_gateway="host-gateway",
            override_installed=False, override_needed=False,
        )
        self.assertIsNone(d.host_gateway_ip)

    def test_chosen_probe_matches(self):
        d = GatewayDiagnosis(
            mode=DockerMode.ROOTFUL,
            probe_port=9000, probe_token="T", lan_ip=None,
            probes=(
                ProbeResult("host-gateway", True, "10.0.0.1", "ok"),
                ProbeResult("192.168.1.1", False, None, "fail"),
            ),
            chosen_gateway="host-gateway",
            override_installed=False, override_needed=False,
        )
        cp = d.chosen_probe()
        self.assertIsNotNone(cp)
        assert cp is not None
        self.assertEqual(cp.candidate, "host-gateway")
        self.assertTrue(cp.ok)

    def test_chosen_probe_none_when_no_choice(self):
        d = GatewayDiagnosis(
            mode=DockerMode.ROOTFUL,
            probe_port=9000, probe_token="T", lan_ip=None,
            probes=(),
            chosen_gateway=None,
            override_installed=False, override_needed=False,
        )
        self.assertIsNone(d.chosen_probe())


if __name__ == "__main__":
    unittest.main()
