"""RED tests for Phase 4: policy-aware runtime verification.

Proves that ``verify_runtime`` respects the reviewed host-access
policy instead of unconditionally checking ``host.docker.internal``
against a legacy ``.env`` value.

All tests use fake process runners — no Docker required.
"""
from __future__ import annotations

import unittest
from pathlib import Path
from typing import Any

from docker.versioning.model import HostAccessPolicy
from docker.versioning.runtime_verification import (
    RuntimeCheck,
    RuntimeVerificationResult,
    VerifyRuntimeRequest,
    verify_runtime,
)


# ═══════════════════════════════════════════════════════════════════════
# Minimal fake runner
# ═══════════════════════════════════════════════════════════════════════

def _rf(argv: tuple[str, ...], rc: int = 0, stdout: str = "",
         stderr: str = "") -> Any:
    """Return a fake process result."""
    from docker.versioning.runtime_verification import ProcessResult
    return ProcessResult(argv=argv, return_code=rc,
                         stdout=stdout, stderr=stderr)


class _FakeRunner:
    """Callable that returns a canned response for each argv."""

    def __init__(self, responses: dict[tuple[str, ...], _rf]) -> None:
        self._responses = responses
        self.calls: list[tuple[str, ...]] = []

    def run(self, argv: tuple[str, ...]) -> Any:
        self.calls.append(argv)
        for pattern, result in self._responses.items():
            if all(p in argv for p in pattern):
                return result
        return _rf(argv, rc=0, stdout="")


# ═══════════════════════════════════════════════════════════════════════
# Canonical test helpers
# ═══════════════════════════════════════════════════════════════════════

def _make_projection(path: Path) -> Path:
    """Write a minimal effective runtime projection file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        '[extensions]\n'
        '[project_paths]\n'
        'paths = []\n'
        '[pi_home]\n'
        'path = "/home/dev/.pi"\n'
        '[gateway]\n'
        'address = "192.168.65.1"\n'
        '[integrity]\n'
        'sha256 = "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA="\n'
    )
    return path


def _projection_identity_response(proj_path: Path) -> Any:
    """Return responses to satisfy projection.identity and read-only checks."""
    import hashlib
    h = hashlib.sha256(proj_path.read_bytes()).hexdigest()
    return _rf(("sha256sum",), rc=0, stdout=f"{h}  /run/pi-cli/docker-constructor.runtime.toml\n")


def _projection_readonly_responses() -> tuple[Any, Any]:
    """Return responses for /proc/mounts grep and test -w."""
    return (
        _rf(("grep",), rc=0,
            stdout="/dev/sda1 /run/pi-cli/docker-constructor.runtime.toml ext4 ro,nosuid,nodev,relatime 0 0\n"),
        _rf(("test", "-w", "/run/pi-cli/docker-constructor.runtime.toml"), rc=1),
    )


# ═══════════════════════════════════════════════════════════════════════
# 4.1  Enabled host-access verification (address + hostname)
# ═══════════════════════════════════════════════════════════════════════

class TestEnabledHostAccessVerificationRed(unittest.TestCase):
    """Enabled host access must verify exact ``host.docker.internal``
    resolution and exact ``HOST_ACCESS_ADDRESS`` equality."""

    def test_docker_gateway_verifies_hostname_and_env(self) -> None:
        """When host access is enabled in docker-gateway mode, the
        verifier must check that ``host.docker.internal`` resolves to
        the expected address AND that ``HOST_ACCESS_ADDRESS`` equals
        that address inside the container."""
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            proj = _make_projection(Path(tmp) / "proj.toml")

            runner = _FakeRunner({
                # projection.identity
                ("sha256sum", "/run/pi-cli/docker-constructor.runtime.toml"):
                    _projection_identity_response(proj),
                # projection.readonly
                ("grep", "docker-constructor.runtime.toml", "/proc/mounts"):
                    _projection_readonly_responses()[0],
                ("test", "-w", "/run/pi-cli/docker-constructor.runtime.toml"):
                    _projection_readonly_responses()[1],
                # ownership.dev, pi-home.setup
                ("stat", "-c", "%U:%G"): _rf(("stat",), rc=0, stdout="dev:dev\n"),
                ("test", "-d", "/home/dev/.pi"): _rf(("test",), rc=0),
                ("test", "-w", "/home/dev/.pi"): _rf(("test",), rc=0),
                # forbidden.paths
                ("test", "-f",): _rf(("test",), rc=1),
                # ---- host-access checks ----
                # gateway.mapping
                ("getent", "hosts", "host.docker.internal"):
                    _rf(("getent",), rc=0, stdout="10.0.2.2  host.docker.internal\n"),
                # HOST_ACCESS_ADDRESS env
                ("printenv", "HOST_ACCESS_ADDRESS"):
                    _rf(("printenv",), rc=0, stdout="10.0.2.2\n"),
            })

            request = VerifyRuntimeRequest(
                container="pi-test",
                runtime_projection_path=proj,
                project_paths=(),
                container_pi_home=Path("/home/dev/.pi"),
                expected_gateway="unused",  # still accepted but ignored
                runner=runner,
                host_access=HostAccessPolicy(
                    enabled=True, mode="docker-gateway", proxy_port=None,
                ),
                host_access_address="10.0.2.2",
            )

            result = verify_runtime(request)

            # gateway.mapping check must exist and pass
            gm = [c for c in result.checks if c.key == "gateway.mapping"]
            self.assertTrue(gm, "gateway.mapping check must be present")
            self.assertTrue(gm[0].ok, f"gateway.mapping must pass, got: {gm[0].detail}")

            # host-access.address check must exist and pass
            ha = [c for c in result.checks if c.key == "host-access.address"]
            self.assertTrue(ha, "host-access.address check must be present")
            self.assertTrue(ha[0].ok, f"host-access.address must pass, got: {ha[0].detail}")

    def test_docker_gateway_hostname_mismatch_fails(self) -> None:
        """When ``host.docker.internal`` resolves to a different address
        than expected, the gateway.mapping check must fail."""
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            proj = _make_projection(Path(tmp) / "proj.toml")

            runner = _FakeRunner({
                ("sha256sum", "/run/pi-cli/docker-constructor.runtime.toml"):
                    _projection_identity_response(proj),
                ("grep", "docker-constructor.runtime.toml", "/proc/mounts"):
                    _projection_readonly_responses()[0],
                ("test", "-w", "/run/pi-cli/docker-constructor.runtime.toml"):
                    _projection_readonly_responses()[1],
                ("stat", "-c", "%U:%G"): _rf(("stat",), rc=0, stdout="dev:dev\n"),
                ("test", "-d", "/home/dev/.pi"): _rf(("test",), rc=0),
                ("test", "-w", "/home/dev/.pi"): _rf(("test",), rc=0),
                ("test", "-f",): _rf(("test",), rc=1),
                # gateway.mapping — wrong address
                ("getent", "hosts", "host.docker.internal"):
                    _rf(("getent",), rc=0, stdout="192.168.99.1  host.docker.internal\n"),
                ("printenv", "HOST_ACCESS_ADDRESS"):
                    _rf(("printenv",), rc=0, stdout="10.0.2.2\n"),
            })

            request = VerifyRuntimeRequest(
                container="pi-test",
                runtime_projection_path=proj,
                project_paths=(),
                container_pi_home=Path("/home/dev/.pi"),
                expected_gateway="unused",
                runner=runner,
                host_access=HostAccessPolicy(
                    enabled=True, mode="docker-gateway", proxy_port=None,
                ),
                host_access_address="10.0.2.2",
            )

            result = verify_runtime(request)
            gm = [c for c in result.checks if c.key == "gateway.mapping"]
            self.assertTrue(gm, "gateway.mapping check must be present")
            self.assertFalse(gm[0].ok, "gateway.mapping must fail for mismatched address")

    def test_external_address_verifies_hostname_and_env(self) -> None:
        """External-address mode also verifies resolution and env."""
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            proj = _make_projection(Path(tmp) / "proj.toml")

            runner = _FakeRunner({
                ("sha256sum", "/run/pi-cli/docker-constructor.runtime.toml"):
                    _projection_identity_response(proj),
                ("grep", "docker-constructor.runtime.toml", "/proc/mounts"):
                    _projection_readonly_responses()[0],
                ("test", "-w", "/run/pi-cli/docker-constructor.runtime.toml"):
                    _projection_readonly_responses()[1],
                ("stat", "-c", "%U:%G"): _rf(("stat",), rc=0, stdout="dev:dev\n"),
                ("test", "-d", "/home/dev/.pi"): _rf(("test",), rc=0),
                ("test", "-w", "/home/dev/.pi"): _rf(("test",), rc=0),
                ("test", "-f",): _rf(("test",), rc=1),
                ("getent", "hosts", "host.docker.internal"):
                    _rf(("getent",), rc=0, stdout="203.0.113.5  host.docker.internal\n"),
                ("printenv", "HOST_ACCESS_ADDRESS"):
                    _rf(("printenv",), rc=0, stdout="203.0.113.5\n"),
            })

            request = VerifyRuntimeRequest(
                container="pi-test",
                runtime_projection_path=proj,
                project_paths=(),
                container_pi_home=Path("/home/dev/.pi"),
                expected_gateway="unused",
                runner=runner,
                host_access=HostAccessPolicy(
                    enabled=True, mode="external-address", proxy_port=None,
                ),
                host_access_address="203.0.113.5",
            )

            result = verify_runtime(request)
            gm = [c for c in result.checks if c.key == "gateway.mapping"]
            self.assertTrue(gm, "gateway.mapping check must be present")
            self.assertTrue(gm[0].ok, f"gateway.mapping must pass, got: {gm[0].detail}")
            ha = [c for c in result.checks if c.key == "host-access.address"]
            self.assertTrue(ha, "host-access.address check must be present")
            self.assertTrue(ha[0].ok, f"host-access.address must pass, got: {ha[0].detail}")


# ═══════════════════════════════════════════════════════════════════════
# 4.2  Proxy-port verification
# ═══════════════════════════════════════════════════════════════════════

class TestProxyPortVerificationRed(unittest.TestCase):
    """Configured proxy port must be verified; omitted proxy port
    must not create any positive port requirement."""

    def test_proxy_port_set_verifies_env(self) -> None:
        """When ``proxy-port`` is configured, the runtime check must
        verify that ``HOST_PROXY_PORT`` equals the configured value."""
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            proj = _make_projection(Path(tmp) / "proj.toml")

            runner = _FakeRunner({
                ("sha256sum", "/run/pi-cli/docker-constructor.runtime.toml"):
                    _projection_identity_response(proj),
                ("grep", "docker-constructor.runtime.toml", "/proc/mounts"):
                    _projection_readonly_responses()[0],
                ("test", "-w", "/run/pi-cli/docker-constructor.runtime.toml"):
                    _projection_readonly_responses()[1],
                ("stat", "-c", "%U:%G"): _rf(("stat",), rc=0, stdout="dev:dev\n"),
                ("test", "-d", "/home/dev/.pi"): _rf(("test",), rc=0),
                ("test", "-w", "/home/dev/.pi"): _rf(("test",), rc=0),
                ("test", "-f",): _rf(("test",), rc=1),
                ("getent", "hosts", "host.docker.internal"):
                    _rf(("getent",), rc=0, stdout="10.0.2.2  host.docker.internal\n"),
                ("printenv", "HOST_ACCESS_ADDRESS"):
                    _rf(("printenv",), rc=0, stdout="10.0.2.2\n"),
                ("printenv", "HOST_PROXY_PORT"):
                    _rf(("printenv",), rc=0, stdout="1080\n"),
            })

            request = VerifyRuntimeRequest(
                container="pi-test",
                runtime_projection_path=proj,
                project_paths=(),
                container_pi_home=Path("/home/dev/.pi"),
                expected_gateway="unused",
                runner=runner,
                host_access=HostAccessPolicy(
                    enabled=True, mode="docker-gateway", proxy_port=1080,
                ),
                host_access_address="10.0.2.2",
            )

            result = verify_runtime(request)
            pp = [c for c in result.checks if c.key == "host-access.proxy-port"]
            self.assertTrue(pp, "host-access.proxy-port check must be present")
            self.assertTrue(pp[0].ok, f"proxy-port check must pass, got: {pp[0].detail}")

    def test_proxy_port_mismatch_fails(self) -> None:
        """When ``HOST_PROXY_PORT`` does not match the configured value,
        the check must fail."""
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            proj = _make_projection(Path(tmp) / "proj.toml")

            runner = _FakeRunner({
                ("sha256sum", "/run/pi-cli/docker-constructor.runtime.toml"):
                    _projection_identity_response(proj),
                ("grep", "docker-constructor.runtime.toml", "/proc/mounts"):
                    _projection_readonly_responses()[0],
                ("test", "-w", "/run/pi-cli/docker-constructor.runtime.toml"):
                    _projection_readonly_responses()[1],
                ("stat", "-c", "%U:%G"): _rf(("stat",), rc=0, stdout="dev:dev\n"),
                ("test", "-d", "/home/dev/.pi"): _rf(("test",), rc=0),
                ("test", "-w", "/home/dev/.pi"): _rf(("test",), rc=0),
                ("test", "-f",): _rf(("test",), rc=1),
                ("getent", "hosts", "host.docker.internal"):
                    _rf(("getent",), rc=0, stdout="10.0.2.2  host.docker.internal\n"),
                ("printenv", "HOST_ACCESS_ADDRESS"):
                    _rf(("printenv",), rc=0, stdout="10.0.2.2\n"),
                ("printenv", "HOST_PROXY_PORT"):
                    _rf(("printenv",), rc=0, stdout="9999\n"),
            })

            request = VerifyRuntimeRequest(
                container="pi-test",
                runtime_projection_path=proj,
                project_paths=(),
                container_pi_home=Path("/home/dev/.pi"),
                expected_gateway="unused",
                runner=runner,
                host_access=HostAccessPolicy(
                    enabled=True, mode="docker-gateway", proxy_port=1080,
                ),
                host_access_address="10.0.2.2",
            )

            result = verify_runtime(request)
            pp = [c for c in result.checks if c.key == "host-access.proxy-port"]
            self.assertTrue(pp, "host-access.proxy-port check must be present")
            self.assertFalse(pp[0].ok, "proxy-port check must fail for mismatch")

    def test_no_proxy_port_no_positive_port_requirement(self) -> None:
        """When proxy-port is omitted from policy, the verifier must NOT
        check for HOST_PROXY_PORT at all — not even a negative check."""
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            proj = _make_projection(Path(tmp) / "proj.toml")

            printer = _rf(("printenv",), rc=1, stdout="")  # var not set
            runner = _FakeRunner({
                ("sha256sum", "/run/pi-cli/docker-constructor.runtime.toml"):
                    _projection_identity_response(proj),
                ("grep", "docker-constructor.runtime.toml", "/proc/mounts"):
                    _projection_readonly_responses()[0],
                ("test", "-w", "/run/pi-cli/docker-constructor.runtime.toml"):
                    _projection_readonly_responses()[1],
                ("stat", "-c", "%U:%G"): _rf(("stat",), rc=0, stdout="dev:dev\n"),
                ("test", "-d", "/home/dev/.pi"): _rf(("test",), rc=0),
                ("test", "-w", "/home/dev/.pi"): _rf(("test",), rc=0),
                ("test", "-f",): _rf(("test",), rc=1),
                ("getent", "hosts", "host.docker.internal"):
                    _rf(("getent",), rc=0, stdout="10.0.2.2  host.docker.internal\n"),
                ("printenv", "HOST_ACCESS_ADDRESS"):
                    _rf(("printenv",), rc=0, stdout="10.0.2.2\n"),
                ("printenv",): printer,
            })

            request = VerifyRuntimeRequest(
                container="pi-test",
                runtime_projection_path=proj,
                project_paths=(),
                container_pi_home=Path("/home/dev/.pi"),
                expected_gateway="unused",
                runner=runner,
                host_access=HostAccessPolicy(
                    enabled=True, mode="docker-gateway", proxy_port=None,
                ),
                host_access_address="10.0.2.2",
            )

            result = verify_runtime(request)
            pp_checks = [c for c in result.checks
                         if c.key == "host-access.proxy-port"]
            self.assertEqual(0, len(pp_checks),
                             "proxy-port check must be absent when proxy-port is None")

            # But host-access.address must still be present
            ha = [c for c in result.checks if c.key == "host-access.address"]
            self.assertTrue(ha, "host-access.address must still be present")


# ═══════════════════════════════════════════════════════════════════════
# 4.3  Disabled host-access verification
# ═══════════════════════════════════════════════════════════════════════

class TestDisabledHostAccessVerificationRed(unittest.TestCase):
    """Disabled host access must skip positive gateway resolution
    and fail if constructor-set HOST_ACCESS_ADDRESS or HOST_PROXY_PORT
    is present."""

    def test_disabled_skips_hostname_resolution(self) -> None:
        """When host access is disabled, the verifier must NOT run
        ``getent hosts host.docker.internal``."""
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            proj = _make_projection(Path(tmp) / "proj.toml")

            runner = _FakeRunner({
                ("sha256sum", "/run/pi-cli/docker-constructor.runtime.toml"):
                    _projection_identity_response(proj),
                ("grep", "docker-constructor.runtime.toml", "/proc/mounts"):
                    _projection_readonly_responses()[0],
                ("test", "-w", "/run/pi-cli/docker-constructor.runtime.toml"):
                    _projection_readonly_responses()[1],
                ("stat", "-c", "%U:%G"): _rf(("stat",), rc=0, stdout="dev:dev\n"),
                ("test", "-d", "/home/dev/.pi"): _rf(("test",), rc=0),
                ("test", "-w", "/home/dev/.pi"): _rf(("test",), rc=0),
                ("test", "-f",): _rf(("test",), rc=1),
            })

            request = VerifyRuntimeRequest(
                container="pi-test",
                runtime_projection_path=proj,
                project_paths=(),
                container_pi_home=Path("/home/dev/.pi"),
                expected_gateway="",  # legacy empty; should be ignored
                runner=runner,
                host_access=None,
                host_access_address=None,
            )

            result = verify_runtime(request)
            # No gateway.mapping check
            gm = [c for c in result.checks if c.key == "gateway.mapping"]
            self.assertEqual(0, len(gm),
                             "gateway.mapping must not be checked when disabled")
            # No getent call
            getent_calls = [a for a in runner.calls if "getent" in a]
            self.assertEqual(0, len(getent_calls),
                             "no getent call when host access is disabled")

    def test_disabled_fails_if_host_access_address_present(self) -> None:
        """When host access is disabled but HOST_ACCESS_ADDRESS is
        set in the container, verification must fail — the constructor
        should not have leaked environment variables."""
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            proj = _make_projection(Path(tmp) / "proj.toml")

            runner = _FakeRunner({
                ("sha256sum", "/run/pi-cli/docker-constructor.runtime.toml"):
                    _projection_identity_response(proj),
                ("grep", "docker-constructor.runtime.toml", "/proc/mounts"):
                    _projection_readonly_responses()[0],
                ("test", "-w", "/run/pi-cli/docker-constructor.runtime.toml"):
                    _projection_readonly_responses()[1],
                ("stat", "-c", "%U:%G"): _rf(("stat",), rc=0, stdout="dev:dev\n"),
                ("test", "-d", "/home/dev/.pi"): _rf(("test",), rc=0),
                ("test", "-w", "/home/dev/.pi"): _rf(("test",), rc=0),
                ("test", "-f",): _rf(("test",), rc=1),
                # HOST_ACCESS_ADDRESS is present — must be detected
                ("printenv", "HOST_ACCESS_ADDRESS"):
                    _rf(("printenv",), rc=0, stdout="10.0.2.2\n"),
            })

            request = VerifyRuntimeRequest(
                container="pi-test",
                runtime_projection_path=proj,
                project_paths=(),
                container_pi_home=Path("/home/dev/.pi"),
                expected_gateway="",
                runner=runner,
                host_access=None,
                host_access_address=None,
            )

            result = verify_runtime(request)
            leak_checks = [c for c in result.checks
                           if "host-access" in c.key and c.key != "host-access.proxy-port"]
            self.assertTrue(leak_checks,
                            "must report HOST_ACCESS_ADDRESS leak when disabled")
            self.assertTrue(
                any(not c.ok for c in leak_checks),
                f"at least one leak check must fail, got: "
                f"{[(c.key, c.ok) for c in leak_checks]}"
            )

    def test_disabled_fails_if_host_proxy_port_present(self) -> None:
        """When host access is disabled but HOST_PROXY_PORT is set
        in the container, verification must fail."""
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            proj = _make_projection(Path(tmp) / "proj.toml")

            runner = _FakeRunner({
                ("sha256sum", "/run/pi-cli/docker-constructor.runtime.toml"):
                    _projection_identity_response(proj),
                ("grep", "docker-constructor.runtime.toml", "/proc/mounts"):
                    _projection_readonly_responses()[0],
                ("test", "-w", "/run/pi-cli/docker-constructor.runtime.toml"):
                    _projection_readonly_responses()[1],
                ("stat", "-c", "%U:%G"): _rf(("stat",), rc=0, stdout="dev:dev\n"),
                ("test", "-d", "/home/dev/.pi"): _rf(("test",), rc=0),
                ("test", "-w", "/home/dev/.pi"): _rf(("test",), rc=0),
                ("test", "-f",): _rf(("test",), rc=1),
                ("printenv", "HOST_PROXY_PORT"):
                    _rf(("printenv",), rc=0, stdout="1080\n"),
            })

            request = VerifyRuntimeRequest(
                container="pi-test",
                runtime_projection_path=proj,
                project_paths=(),
                container_pi_home=Path("/home/dev/.pi"),
                expected_gateway="",
                runner=runner,
                host_access=None,
                host_access_address=None,
            )

            result = verify_runtime(request)
            pp_checks = [c for c in result.checks
                         if c.key == "host-access.proxy-port"]
            self.assertTrue(pp_checks,
                            "must report HOST_PROXY_PORT leak when disabled")
            self.assertFalse(pp_checks[0].ok,
                             "HOST_PROXY_PORT leak must fail verification")

    def test_disabled_passes_when_no_host_access_env_set(self) -> None:
        """When disabled and no constructor-set variables are present,
        verification passes for host-access checks."""
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            proj = _make_projection(Path(tmp) / "proj.toml")

            runner = _FakeRunner({
                ("sha256sum", "/run/pi-cli/docker-constructor.runtime.toml"):
                    _projection_identity_response(proj),
                ("grep", "docker-constructor.runtime.toml", "/proc/mounts"):
                    _projection_readonly_responses()[0],
                ("test", "-w", "/run/pi-cli/docker-constructor.runtime.toml"):
                    _projection_readonly_responses()[1],
                ("stat", "-c", "%U:%G"): _rf(("stat",), rc=0, stdout="dev:dev\n"),
                ("test", "-d", "/home/dev/.pi"): _rf(("test",), rc=0),
                ("test", "-w", "/home/dev/.pi"): _rf(("test",), rc=0),
                ("test", "-f",): _rf(("test",), rc=1),
                # HOST_ACCESS_ADDRESS is NOT set
                ("printenv", "HOST_ACCESS_ADDRESS"):
                    _rf(("printenv",), rc=1, stdout=""),
                # HOST_PROXY_PORT is NOT set
                ("printenv", "HOST_PROXY_PORT"):
                    _rf(("printenv",), rc=1, stdout=""),
            })

            request = VerifyRuntimeRequest(
                container="pi-test",
                runtime_projection_path=proj,
                project_paths=(),
                container_pi_home=Path("/home/dev/.pi"),
                expected_gateway="",
                runner=runner,
                host_access=None,
                host_access_address=None,
            )

            result = verify_runtime(request)
            leak_checks = [c for c in result.checks
                           if c.key.startswith("host-access.")]
            if leak_checks:
                self.assertTrue(all(c.ok for c in leak_checks),
                                f"all host-access checks must pass when vars absent: "
                                f"{[(c.key, c.ok) for c in leak_checks]}")


# ═══════════════════════════════════════════════════════════════════════
# 4.4  Facade verification expectations from inventory + companion
# ═══════════════════════════════════════════════════════════════════════

class TestFacadeVerifyHostAccessRed(unittest.TestCase):
    """The facade's ``verify --scope runtime`` command must derive
    host-access expectations from the selected reviewed inventory and
    its matching local companion."""

    @staticmethod
    def _load_mod() -> Any:
        from docker import constructor_cli
        return constructor_cli

    @staticmethod
    def _run_cli(
        mod: Any,
        argv: list[str],
        *,
        _process_runner: Any = None,
        _prompt_user: Any = None,
    ) -> tuple[int, str, str]:
        import io
        from contextlib import redirect_stderr, redirect_stdout
        out = io.StringIO()
        err = io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            rc = mod.main(
                argv,
                _process_runner=_process_runner,
                _prompt_user=_prompt_user,
            )
        return rc, out.getvalue(), err.getvalue()

    def test_facade_passes_host_access_from_inventory_and_companion(self) -> None:
        """When the verified inventory has docker-gateway host access
        and the local companion provides an address, the facade must
        construct a ``VerifyRuntimeRequest`` with the matching
        ``HostAccessPolicy`` and address."""
        import json as _json
        import tempfile
        from unittest import mock

        mod = self._load_mod()

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            # Reviewed inventory with docker-gateway host access
            inv = root / "docker-constructor.toml"
            inv.write_text(
                '[meta]\nversion = 1\n'
                '[environments.pi-local]\n'
                'provider = "docker"\n'
                'name = "pi-cli-pi"\n'
                'tag = "latest"\n'
                '[runtime.host-access]\n'
                'enabled = true\n'
                'mode = "docker-gateway"\n'
            )
            # Local companion with gateway address
            comp = root / "docker-constructor.local.toml"
            comp.write_text(
                '[host-access]\n'
                'address = "10.0.2.100"\n'
                '[cache]\n'
                'dir = "/tmp/custom-cache"\n'
            )
            # Effective projections
            gen = root / ".docker-generated"
            gen.mkdir(parents=True)
            bp = gen / "docker-constructor.build.effective.toml"
            bp.write_text(
                '[python]\nversion = "3.12.0"\n'
                '[node]\nimage = "node:20.11.0-bookworm-slim"\n'
            )
            rt_dir = gen / "runtime"
            rt_dir.mkdir(parents=True)
            rp = rt_dir / "a1b2c3d4.toml"
            rp.write_text(
                '[extensions]\n'
                '[project_paths]\n'
                'paths = []\n'
                '[pi_home]\n'
                'path = "/home/dev/.pi"\n'
                '[gateway]\n'
                'address = "10.0.2.100"\n'
                '[integrity]\n'
                'sha256 = "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA="\n'
            )

            from docker.launcher import ProcessResult

            captured_request = []

            def _fake_verify_runtime(req: Any) -> Any:
                captured_request.append(req)
                from docker.versioning.runtime_verification import (
                    RuntimeVerificationResult,
                )
                return RuntimeVerificationResult(
                    container=req.container,
                    checks=(),
                    all_ok=True,
                    errors=(),
                )

            def _fake_runner(argv: Any) -> ProcessResult:
                # container auto-detection
                if argv[0] == "docker" and argv[1] == "ps":
                    return ProcessResult(argv=tuple(argv), return_code=0,
                                         stdout="abc123\n", stderr="")
                # All other docker exec calls
                return ProcessResult(argv=tuple(argv), return_code=0,
                                     stdout="", stderr="")

            class _Rec:
                def run(self, argv: Any, **kwargs: Any) -> ProcessResult:
                    return _fake_runner(argv)

            with mock.patch(
                "docker.versioning.runtime_verification.verify_runtime",
                _fake_verify_runtime,
            ):
                from docker.constructor_cli import ExitKind
                rc, out, err = self._run_cli(
                    mod,
                    ["--inventory", str(inv),
                     "verify", "--scope", "runtime",
                     "--container", "pi-test",
                     "--project", "/home/dev/p1"],
                    _process_runner=_Rec(),
                    _prompt_user=lambda _: True,
                )

            self.assertTrue(captured_request, "verify_runtime must be called")
            req = captured_request[0]
            # Must have host_access=HostAccessPolicy(enabled=True, mode="docker-gateway")
            self.assertTrue(
                hasattr(req, "host_access"),
                "VerifyRuntimeRequest must have host_access field"
            )
            ha = req.host_access
            self.assertIsNotNone(ha, "host_access must not be None for enabled policy")
            self.assertTrue(ha.enabled)
            self.assertEqual("docker-gateway", ha.mode)
            self.assertEqual("10.0.2.100", req.host_access_address)

    def test_facade_disabled_passes_none_host_access(self) -> None:
        """When host access is disabled, the facade must pass
        ``host_access=None`` and no address to ``VerifyRuntimeRequest``."""
        import tempfile
        from unittest import mock

        mod = self._load_mod()

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            inv = root / "docker-constructor.toml"
            inv.write_text(
                '[meta]\nversion = 1\n'
                '[environments.pi-local]\n'
                'provider = "docker"\n'
                'name = "pi-cli-pi"\n'
                'tag = "latest"\n'
                # No [runtime.host-access] → disabled
            )
            gen = root / ".docker-generated"
            gen.mkdir(parents=True)
            bp = gen / "docker-constructor.build.effective.toml"
            bp.write_text('[python]\nversion = "3.12.0"\n')
            rt_dir = gen / "runtime"
            rt_dir.mkdir(parents=True)
            rp = rt_dir / "a1b2c3d4.toml"
            rp.write_text(
                '[extensions]\n'
                '[project_paths]\n'
                'paths = []\n'
                '[pi_home]\n'
                'path = "/home/dev/.pi"\n'
                '[gateway]\n'
                'address = ""\n'
                '[integrity]\n'
                'sha256 = "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA="\n'
            )

            from docker.launcher import ProcessResult

            captured_request = []

            def _fake_verify_runtime(req: Any) -> Any:
                captured_request.append(req)
                from docker.versioning.runtime_verification import (
                    RuntimeVerificationResult,
                )
                return RuntimeVerificationResult(
                    container=req.container, checks=(),
                    all_ok=True, errors=(),
                )

            class _Rec:
                def run(self, argv: Any, **kwargs: Any) -> ProcessResult:
                    if argv[0] == "docker" and argv[1] == "ps":
                        return ProcessResult(argv=tuple(argv),
                                             return_code=0,
                                             stdout="abc123\n", stderr="")
                    return ProcessResult(argv=tuple(argv),
                                         return_code=0,
                                         stdout="", stderr="")

            with mock.patch(
                "docker.versioning.runtime_verification.verify_runtime",
                _fake_verify_runtime,
            ):
                rc, out, err = self._run_cli(
                    mod,
                    ["--inventory", str(inv),
                     "verify", "--scope", "runtime",
                     "--container", "pi-test",
                     "--project", "/home/dev/p1"],
                    _process_runner=_Rec(),
                    _prompt_user=lambda _: True,
                )

            self.assertTrue(captured_request, "verify_runtime must be called")
            req = captured_request[0]
            self.assertIsNone(req.host_access,
                              "host_access must be None when disabled")
            self.assertIsNone(req.host_access_address,
                              "host_access_address must be None when disabled")

    def test_facade_custom_inventory_resolves_own_companion(self) -> None:
        """When ``--inventory /path/custom.toml`` is used, the facade
        must resolve ``/path/custom.local.toml`` — not the repository
        root companion."""
        import tempfile
        from unittest import mock

        mod = self._load_mod()

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            # Custom inventory path
            inv = root / "custom.toml"
            inv.write_text(
                '[meta]\nversion = 1\n'
                '[environments.pi-local]\n'
                'provider = "docker"\n'
                'name = "pi-cli-pi"\n'
                'tag = "latest"\n'
                '[runtime.host-access]\n'
                'enabled = true\n'
                'mode = "external-address"\n'
            )
            # Custom companion
            comp = root / "custom.local.toml"
            comp.write_text(
                '[host-access]\n'
                'address = "203.0.113.99"\n'
            )
            gen = root / ".docker-generated"
            gen.mkdir(parents=True)
            bp = gen / "docker-constructor.build.effective.toml"
            bp.write_text('[python]\nversion = "3.12.0"\n')
            rt_dir = gen / "runtime"
            rt_dir.mkdir(parents=True)
            rp = rt_dir / "a1b2c3d4.toml"
            rp.write_text(
                '[extensions]\n'
                '[project_paths]\n'
                'paths = []\n'
                '[pi_home]\n'
                'path = "/home/dev/.pi"\n'
                '[gateway]\n'
                'address = "203.0.113.99"\n'
                '[integrity]\n'
                'sha256 = "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA="\n'
            )

            from docker.launcher import ProcessResult

            captured_request = []

            def _fake_verify_runtime(req: Any) -> Any:
                captured_request.append(req)
                from docker.versioning.runtime_verification import (
                    RuntimeVerificationResult,
                )
                return RuntimeVerificationResult(
                    container=req.container, checks=(),
                    all_ok=True, errors=(),
                )

            class _Rec:
                def run(self, argv: Any, **kwargs: Any) -> ProcessResult:
                    if argv[0] == "docker" and argv[1] == "ps":
                        return ProcessResult(argv=tuple(argv),
                                             return_code=0,
                                             stdout="abc123\n", stderr="")
                    return ProcessResult(argv=tuple(argv),
                                         return_code=0,
                                         stdout="", stderr="")

            with mock.patch(
                "docker.versioning.runtime_verification.verify_runtime",
                _fake_verify_runtime,
            ):
                rc, out, err = self._run_cli(
                    mod,
                    ["--inventory", str(inv),
                     "verify", "--scope", "runtime",
                     "--container", "pi-test",
                     "--project", "/home/dev/p1"],
                    _process_runner=_Rec(),
                    _prompt_user=lambda _: True,
                )

            self.assertTrue(captured_request, "verify_runtime must be called")
            req = captured_request[0]
            self.assertIsNotNone(req.host_access)
            self.assertEqual("external-address", req.host_access.mode)
            self.assertEqual("203.0.113.99", req.host_access_address)
