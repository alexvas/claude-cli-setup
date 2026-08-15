"""RED contracts for Phase 3 — runtime trust/proxy launch vector and
verification reporting.

These tests pin the Phase 3 launch contract before the GREEN
implementation exists:

* an enabled fixed bundle is mounted read-only at
  ``/etc/ssl/certs/ca-certificates.crt``, and disabled trust emits no such
  mount (task 3.1);
* a configured proxy is emitted under every uppercase/lowercase HTTP,
  HTTPS, and ALL proxy variable, with uppercase/lowercase NO_PROXY
  variables only for an explicitly configured bypass list (task 3.2);
* external and host-endpoint proxies are independent of host access: they
  require no host-access mapping, trigger no gateway diagnostics, and do
  not alter host-access mappings (task 3.3);
* runtime verification reports the configured trust/proxy launch contract
  without arbitrary environment dumps and without Docker client/daemon
  coverage claims (task 3.4).

The GREEN implementation (tasks 3.5–3.7) extends ``RunRenderInputs``,
``orchestrate_run``, and ``VerifyRuntimeRequest`` to satisfy these tests.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from docker.launcher import (
    ProjectSelection,
    RunRequest,
    RunResult,
    orchestrate_run,
)
from docker.versioning.dispatch_types import ExitKind
from docker.versioning.rendering import RunRenderInputs, render_run_vector
from docker.versioning.runtime_verification import _MOUNTS_PROBE

_REPO_ROOT = Path(__file__).resolve().parents[1]
_CANONICAL = (_REPO_ROOT / "docker-constructor.toml").read_text()

_SYSTEM_CA_BUNDLE = "/etc/ssl/certs/ca-certificates.crt"

_PROXY_URL_NAMES = (
    "HTTP_PROXY",
    "http_proxy",
    "HTTPS_PROXY",
    "https_proxy",
    "ALL_PROXY",
    "all_proxy",
)

_PROXY_BYPASS_NAMES = ("NO_PROXY", "no_proxy")

_VALID_BUNDLE = (
    "-----BEGIN CERTIFICATE-----\n"
    "AQIDBAU=\n"
    "-----END CERTIFICATE-----\n"
)


# ---------------------------------------------------------------------------
# Render-level helpers
# ---------------------------------------------------------------------------

def _render(
    *,
    corporate_trust_bundle: str | None = None,
    proxy_url: str | None = None,
    proxy_no_proxy: str | None = None,
) -> tuple[str, ...]:
    """Render a minimal run vector with the Phase 3 corporate inputs."""
    return render_run_vector(RunRenderInputs(
        image="pi-cli-pi:latest",
        container_name="pi-1",
        projection_host_path="/tmp/.docker-generated/runtime/projection.toml",
        projection_container_path="/run/pi-cli/docker-constructor.runtime.toml",
        pi_home_host="/home/user/.pi",
        main_project="/work/project",
        corporate_trust_bundle=corporate_trust_bundle,
        proxy_url=proxy_url,
        proxy_no_proxy=proxy_no_proxy,
    ))


def _collect_mounts(args: tuple[str, ...]) -> list[dict[str, str]]:
    """Extract all ``--mount`` key=value,... specs into dicts."""
    mounts: list[dict[str, str]] = []
    it = iter(args)
    for token in it:
        if token == "--mount":
            raw = next(it)
            kv: dict[str, str] = {}
            for pair in raw.split(","):
                k, _, v = pair.partition("=")
                kv[k] = v
            mounts.append(kv)
    return mounts


def _find_mount(
    mounts: list[dict[str, str]],
    dst: str,
) -> dict[str, str] | None:
    for m in mounts:
        if m.get("dst") == dst:
            return m
    return None


def _collect_env(args: tuple[str, ...]) -> dict[str, str]:
    """Extract all ``--env KEY=VALUE`` pairs into a dict."""
    env: dict[str, str] = {}
    it = iter(args)
    for token in it:
        if token == "--env":
            raw = next(it)
            k, _, v = raw.partition("=")
            env[k] = v
    return env


# ---------------------------------------------------------------------------
# Orchestration-level helpers
# ---------------------------------------------------------------------------

def _bomb_executor(effects: list[str]):
    class _Exec:
        def run(self, argv: tuple[str, ...], *, interactive: bool = False):
            del argv, interactive
            effects.append("execution")
            raise AssertionError("Docker run must not execute during dry-run")

    return _Exec()


def _bomb_inspector(effects: list[str]):
    class _Insp:
        def list_names(self) -> set[str]:
            effects.append("inspection")
            raise AssertionError("container inspection must not run")

    return _Insp()


def _bomb_projection(effects: list[str]):
    def _factory(*_args, **_kwargs):
        effects.append("projection")
        raise AssertionError("projection publication must not run")

    return _factory


def _bomb_artifact(effects: list[str]):
    def _fetcher(*_args, **_kwargs):
        effects.append("materialization")
        raise AssertionError("artifact materialization must not run")

    return _fetcher


class _RunOrchestrationRed(unittest.TestCase):
    """Runs ``orchestrate_run`` (dry-run) against a real inventory +
    local companion, mirroring the build-orchestration RED harness."""

    def run_with_local(
        self,
        companion: str | None,
        *,
        bundle: str | None = None,
        inventory_policy: str | None = None,
    ) -> RunResult:
        with tempfile.TemporaryDirectory() as root:
            root_path = Path(root)
            inventory = root_path / "inventory.toml"
            inventory.write_text(
                _CANONICAL + (inventory_policy or "")
            )
            if companion is not None:
                (root_path / "inventory.local.toml").write_text(companion)
            if bundle is not None:
                bundle_dir = root_path / ".docker-local"
                bundle_dir.mkdir()
                (bundle_dir / "corporate-ca-bundle.crt").write_text(bundle)
            effects: list[str] = []
            result = orchestrate_run(RunRequest(
                inventory_path=str(inventory),
                image="pi-cli-pi:latest",
                selection=ProjectSelection(main_project="/work/project"),
                pi_home_host="/home/user/.pi",
                repo_root=str(root_path),
                dry_run=True,
                executor=_bomb_executor(effects),
                inspector=_bomb_inspector(effects),
                _create_projection=_bomb_projection(effects),
                _artifact_fetcher=_bomb_artifact(effects),
            ))
            self.assertEqual([], effects)
            return result


# ---------------------------------------------------------------------------
# 3.1  Trust mount run-vector contract
# ---------------------------------------------------------------------------

class TestRunVectorTrustMountRed(unittest.TestCase):
    """Task 3.1: enabled bundle mounted read-only; disabled → no mount."""

    def test_enabled_trust_mounts_bundle_readonly_at_system_path(self) -> None:
        args = _render(
            corporate_trust_bundle=(
                "/repo/.docker-local/corporate-ca-bundle.crt"
            ),
        )
        mounts = _collect_mounts(args)
        mount = _find_mount(mounts, dst=_SYSTEM_CA_BUNDLE)
        self.assertIsNotNone(mount, "missing corporate trust mount")
        self.assertEqual(mount["type"], "bind")
        self.assertEqual(
            mount["src"],
            "/repo/.docker-local/corporate-ca-bundle.crt",
        )
        self.assertIn("readonly", mount,
                      "corporate trust mount must be read-only")

    def test_disabled_trust_emits_no_system_bundle_mount(self) -> None:
        args = _render()
        mounts = _collect_mounts(args)
        self.assertIsNone(
            _find_mount(mounts, dst=_SYSTEM_CA_BUNDLE),
            "disabled trust must not emit a system-bundle mount",
        )


class TestTrustMountOrchestrationRed(_RunOrchestrationRed):
    """Task 3.1 integration: ``orchestrate_run`` carries the mount."""

    def test_enabled_trust_orchestrates_readonly_mount(self) -> None:
        result = self.run_with_local(
            "[corporate-trust]\nenabled = true\n",
            bundle=_VALID_BUNDLE,
        )
        self.assertEqual(ExitKind.SUCCESS, result.exit_kind, result.message)
        mounts = _collect_mounts(result.run_args)
        mount = _find_mount(mounts, dst=_SYSTEM_CA_BUNDLE)
        self.assertIsNotNone(mount, "missing corporate trust mount")
        self.assertEqual(mount["type"], "bind")
        self.assertIn("readonly", mount)

    def test_disabled_trust_orchestrates_no_mount(self) -> None:
        for companion in (None, "[corporate-trust]\nenabled = false\n"):
            with self.subTest(companion=companion):
                result = self.run_with_local(companion)
                self.assertEqual(
                    ExitKind.SUCCESS, result.exit_kind, result.message,
                )
                mounts = _collect_mounts(result.run_args)
                self.assertIsNone(
                    _find_mount(mounts, dst=_SYSTEM_CA_BUNDLE),
                    "disabled trust must not emit a system-bundle mount",
                )


# ---------------------------------------------------------------------------
# 3.2  Proxy environment run-vector contract
# ---------------------------------------------------------------------------

class TestRunVectorProxyEnvRed(unittest.TestCase):
    """Task 3.2: proxy variables under every standard name; explicit-only
    bypass list."""

    def test_configured_proxy_emitted_under_all_standard_variables(self) -> None:
        args = _render(proxy_url="http://proxy.corp.example:3128")
        env = _collect_env(args)
        for name in _PROXY_URL_NAMES:
            self.assertEqual(
                "http://proxy.corp.example:3128",
                env.get(name),
                f"missing or wrong value for {name}",
            )
        for name in _PROXY_BYPASS_NAMES:
            self.assertNotIn(name, env,
                             f"{name} must be omitted without an explicit list")

    def test_no_proxy_emitted_only_when_explicitly_configured(self) -> None:
        configured = _render(
            proxy_url="http://proxy.corp.example:3128",
            proxy_no_proxy="localhost,.corp.example",
        )
        env = _collect_env(configured)
        self.assertEqual("localhost,.corp.example", env.get("NO_PROXY"))
        self.assertEqual("localhost,.corp.example", env.get("no_proxy"))

        unconfigured = _render(proxy_url="http://proxy.corp.example:3128")
        env2 = _collect_env(unconfigured)
        self.assertNotIn("NO_PROXY", env2)
        self.assertNotIn("no_proxy", env2)

    def test_disabled_proxy_emits_no_proxy_variables(self) -> None:
        args = _render()
        env = _collect_env(args)
        for name in _PROXY_URL_NAMES + _PROXY_BYPASS_NAMES:
            self.assertNotIn(name, env)


# ---------------------------------------------------------------------------
# 3.3  Proxy host-access independence
# ---------------------------------------------------------------------------

class TestProxyHostAccessIndependenceRed(_RunOrchestrationRed):
    """Task 3.3: proxies never require or alter host access."""

    def test_external_proxy_requires_no_host_access(self) -> None:
        result = self.run_with_local(
            '[network.proxy]\nurl = "http://proxy.corp.example:3128"\n',
        )
        self.assertEqual(ExitKind.SUCCESS, result.exit_kind, result.message)
        env = _collect_env(result.run_args)
        self.assertEqual(
            "http://proxy.corp.example:3128", env.get("HTTP_PROXY"),
        )
        self.assertNotIn("--add-host", result.run_args)
        self.assertNotIn("HOST_ACCESS_ADDRESS", env)
        self.assertNotIn("HOST_PROXY_PORT", env)

    def test_host_endpoint_proxy_requires_no_host_access_or_gateway(self) -> None:
        result = self.run_with_local(
            '[network.proxy]\nurl = "http://127.0.0.1:3128"\n',
        )
        self.assertEqual(ExitKind.SUCCESS, result.exit_kind, result.message)
        env = _collect_env(result.run_args)
        self.assertEqual("http://127.0.0.1:3128", env.get("http_proxy"))
        self.assertNotIn("--add-host", result.run_args)
        self.assertNotIn("HOST_ACCESS_ADDRESS", env)
        self.assertNotIn("HOST_PROXY_PORT", env)

    def test_proxy_does_not_alter_host_access_mappings(self) -> None:
        result = self.run_with_local(
            '[host-access]\naddress = "192.0.2.10"\n'
            '[network.proxy]\nurl = "http://proxy.corp.example:3128"\n',
            inventory_policy=(
                '[runtime.host-access]\n'
                'enabled = true\n'
                'mode = "external-address"\n'
            ),
        )
        self.assertEqual(ExitKind.SUCCESS, result.exit_kind, result.message)
        env = _collect_env(result.run_args)
        # Host-access mapping is preserved exactly as before.
        self.assertIn("host.docker.internal:192.0.2.10", result.run_args)
        self.assertEqual("192.0.2.10", env.get("HOST_ACCESS_ADDRESS"))
        # The proxy contract is layered independently alongside it.
        self.assertEqual(
            "http://proxy.corp.example:3128", env.get("HTTPS_PROXY"),
        )


# ---------------------------------------------------------------------------
# 3.4  Runtime verification / diagnostics contract
# ---------------------------------------------------------------------------

class _ContractRunner:
    """Answers the trust/proxy contract probes for a configured or
    disabled launch; any other command passes generically.

    The GREEN verification adds two targeted probes:

    * an exact-mountpoint ``awk`` probe over ``/proc/mounts`` → a
      read-only (``ro``) mount-options line (configured) or absent
      (disabled), with ``test -w`` confirming not writable on the
      configured path;
    * keyed ``printenv <NAME>`` per standard proxy variable.

    Every command still targets the container via ``docker exec``.
    """

    def __init__(
        self,
        *,
        configured: bool = True,
        overrides: dict[tuple[str, ...], tuple[int, str, str]] | None = None,
    ) -> None:
        self.calls: list[tuple[str, ...]] = []
        if configured:
            self._handlers: dict[tuple[str, ...], tuple[int, str, str]] = {
                _MOUNTS_PROBE:
                    (0, "ro,relatime\n", ""),
                ("test", "-w", _SYSTEM_CA_BUNDLE): (1, "", ""),
            }
            for name in _PROXY_URL_NAMES:
                self._handlers[("printenv", name)] = (
                    0, "http://proxy.corp.example:3128\n", "",
                )
            for name in _PROXY_BYPASS_NAMES:
                self._handlers[("printenv", name)] = (
                    0, "localhost,.corp.example\n", "",
                )
        else:
            self._handlers = {
                _MOUNTS_PROBE: (0, "", ""),
            }
            for name in _PROXY_URL_NAMES + _PROXY_BYPASS_NAMES:
                self._handlers[("printenv", name)] = (1, "", "")
        if overrides:
            self._handlers.update(overrides)

    def run(self, argv) -> object:
        t = tuple(argv)
        self.calls.append(t)
        cmd = t[3:]
        if cmd in self._handlers:
            rc, out, err = self._handlers[cmd]
            return _ProcessResult(argv=t, return_code=rc,
                                  stdout=out, stderr=err)
        return _ProcessResult(argv=t, return_code=0, stdout="", stderr="")


class _ProcessResult:
    def __init__(self, *, argv, return_code, stdout, stderr) -> None:
        self.argv = argv
        self.return_code = return_code
        self.stdout = stdout
        self.stderr = stderr


class TestRuntimeVerificationContractRed(unittest.TestCase):
    """Task 3.4: verification reports the launch contract, never dumps."""

    def _verify(
        self,
        *,
        corporate_trust_enabled: bool,
        proxy_url: str | None,
        proxy_no_proxy: str | None,
        runner: _ContractRunner | None = None,
    ):
        from docker.versioning.runtime_verification import (
            VerifyRuntimeRequest,
            verify_runtime,
        )
        with tempfile.TemporaryDirectory() as root:
            proj = Path(root) / "projection.toml"
            proj.write_text("[extensions]\n")
            if runner is None:
                runner = _ContractRunner(
                    configured=(
                        corporate_trust_enabled or proxy_url is not None
                    ),
                )
            result = verify_runtime(VerifyRuntimeRequest(
                container="pi-cli-pi-1",
                runtime_projection_path=proj,
                project_paths=(Path("/work/project"),),
                container_pi_home=Path("/home/dev/.pi"),
                runner=runner,
                host_access=None,
                corporate_trust_enabled=corporate_trust_enabled,
                proxy_url=proxy_url,
                proxy_no_proxy=proxy_no_proxy,
            ))
            return result, runner

    def test_verify_runtime_reports_enabled_trust_and_proxy_contract(self) -> None:
        result, _runner = self._verify(
            corporate_trust_enabled=True,
            proxy_url="http://proxy.corp.example:3128",
            proxy_no_proxy="localhost,.corp.example",
        )
        keys = {c.key for c in result.checks}
        self.assertIn("corporate-trust.mount", keys)
        self.assertIn("proxy.environment", keys)
        trust = next(c for c in result.checks if c.key == "corporate-trust.mount")
        proxy = next(c for c in result.checks if c.key == "proxy.environment")
        self.assertTrue(trust.ok, trust.detail)
        self.assertTrue(proxy.ok, proxy.detail)

    def test_verify_runtime_reports_disabled_trust_and_proxy_contract(self) -> None:
        result, _runner = self._verify(
            corporate_trust_enabled=False,
            proxy_url=None,
            proxy_no_proxy=None,
        )
        keys = {c.key for c in result.checks}
        self.assertIn("corporate-trust.mount", keys)
        self.assertIn("proxy.environment", keys)
        trust = next(c for c in result.checks if c.key == "corporate-trust.mount")
        proxy = next(c for c in result.checks if c.key == "proxy.environment")
        self.assertTrue(trust.ok, trust.detail)
        self.assertTrue(proxy.ok, proxy.detail)

    def test_disabled_trust_rejects_stale_system_bundle_mount(self) -> None:
        result, _runner = self._verify(
            corporate_trust_enabled=False,
            proxy_url=None,
            proxy_no_proxy=None,
            runner=_ContractRunner(
                configured=False,
                overrides={
                    _MOUNTS_PROBE: (0, "ro,relatime\n", ""),
                },
            ),
        )
        trust = next(
            c for c in result.checks if c.key == "corporate-trust.mount"
        )
        self.assertFalse(trust.ok, trust.detail)

    def test_disabled_proxy_rejects_injected_proxy_variables(self) -> None:
        result, _runner = self._verify(
            corporate_trust_enabled=False,
            proxy_url=None,
            proxy_no_proxy=None,
            runner=_ContractRunner(
                configured=False,
                overrides={
                    ("printenv", "HTTP_PROXY"):
                        (0, "http://proxy.corp.example:3128\n", ""),
                },
            ),
        )
        proxy = next(
            c for c in result.checks if c.key == "proxy.environment"
        )
        self.assertFalse(proxy.ok, proxy.detail)

    def test_verification_never_dumps_environment_or_claims_daemon_coverage(self) -> None:
        # Disabled contract — the guard must hold for the existing verifier
        # and remain true once trust/proxy probes are added.
        result, runner = self._verify(
            corporate_trust_enabled=False,
            proxy_url=None,
            proxy_no_proxy=None,
        )
        self.assertIsInstance(result, object)
        container = "pi-cli-pi-1"
        for argv in runner.calls:
            # Every command must be a targeted ``docker exec``.
            self.assertEqual(
                argv[:2], ("docker", "exec"),
                f"verification must use docker exec, got {argv}",
            )
            self.assertEqual(argv[2], container)
            cmd = argv[3:]
            # No bare environment dumps.
            self.assertNotEqual(cmd, ("printenv",),
                                f"bare printenv dump: {argv}")
            self.assertNotEqual(cmd, ("env",), f"bare env dump: {argv}")
            self.assertNotEqual(cmd[:1], ("env",), f"env command: {argv}")
            # Every printenv must be keyed with exactly one variable name.
            if cmd and cmd[0] == "printenv":
                self.assertEqual(len(cmd), 2,
                                 f"printenv must be keyed, got {argv}")


class TestMountsProbeExactDestination(unittest.TestCase):
    """The mount probe matches only the exact mountpoint field."""

    def _run_probe(self, mounts: str) -> "subprocess.CompletedProcess[str]":
        import subprocess

        with tempfile.TemporaryDirectory() as root:
            fixture = Path(root) / "mounts"
            fixture.write_text(mounts)
            return subprocess.run(
                ["awk", _MOUNTS_PROBE[1], str(fixture)],
                capture_output=True, text=True,
            )

    def test_probe_ignores_unrelated_mounts_containing_the_filename(self) -> None:
        result = self._run_probe(
            "host /host/ca-certificates.crt ext4 rw,relatime 0 0\n"
            "host /etc/ssl/certs/ca-certificates.crt ext4 ro,relatime 0 0\n"
            "host /etc/other/ca-certificates.crt ext4 rw,relatime 0 0\n",
        )
        self.assertEqual(0, result.returncode)
        # Only the exact-destination line's options are reported; the
        # unrelated source/destination matches are ignored.
        self.assertEqual("ro,relatime\n", result.stdout)

    def test_probe_reports_absent_when_only_unrelated_mounts_exist(self) -> None:
        result = self._run_probe(
            "host /host/ca-certificates.crt ext4 ro,relatime 0 0\n",
        )
        self.assertEqual(0, result.returncode)
        self.assertEqual("", result.stdout)


if __name__ == "__main__":
    unittest.main()
