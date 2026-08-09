"""RED contracts for conditional direct-Docker host access."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from docker.versioning.rendering import RunRenderInputs, render_run_vector


_BASE = dict(
    image="pi-cli-pi:latest", container_name="pi-1",
    projection_host_path="/tmp/.docker-generated/runtime/projection.toml",
    projection_container_path="/run/pi-cli/docker-constructor.runtime.toml",
    pi_home_host="/home/user/.pi", main_project="/work/project",
)


def _render(host_access):
    return render_run_vector(RunRenderInputs(**_BASE, host_access=host_access))


class TestConditionalHostAccessRenderingRed(unittest.TestCase):
    def test_disabled_emits_no_host_mapping_or_variables(self):
        from docker.versioning.rendering import RunHostAccess
        args = _render(RunHostAccess.disabled())
        self.assertNotIn("--add-host", args)
        self.assertFalse(any("HOST_ACCESS_ADDRESS=" in arg for arg in args))
        self.assertFalse(any("HOST_PROXY_PORT=" in arg for arg in args))

    def test_docker_gateway_emits_one_mapping_and_matching_address(self):
        from docker.versioning.rendering import RunHostAccess
        args = _render(RunHostAccess(address="172.17.0.1", mode="docker-gateway"))
        self.assertEqual(args.count("--add-host"), 1)
        index = args.index("--add-host")
        self.assertEqual(args[index + 1], "host.docker.internal:172.17.0.1")
        self.assertEqual(args.count("HOST_ACCESS_ADDRESS=172.17.0.1"), 1)

    def test_external_ipv4_and_ipv6_are_rendered_but_gateway_token_is_rejected(self):
        from docker.versioning.rendering import RunHostAccess
        for address in ("192.0.2.10", "2001:db8::10"):
            with self.subTest(address=address):
                args = _render(RunHostAccess(address=address, mode="external-address"))
                self.assertIn(f"host.docker.internal:{address}", args)
                self.assertEqual(args.count(f"HOST_ACCESS_ADDRESS={address}"), 1)
        with self.assertRaises(ValueError):
            RunHostAccess(address="host-gateway", mode="external-address")

    def test_proxy_port_is_neutral_and_does_not_create_proxy_urls(self):
        from docker.versioning.rendering import RunHostAccess
        args = _render(RunHostAccess(address="192.0.2.10", proxy_port=1080))
        self.assertIn("HOST_PROXY_PORT=1080", args)
        forbidden = ("PI_PROXY_URL", "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "://")
        self.assertFalse(any(token in arg for arg in args for token in forbidden))

    def test_enabled_without_proxy_port_omits_all_proxy_environment(self):
        from docker.versioning.rendering import RunHostAccess
        args = _render(RunHostAccess(address="192.0.2.10", mode="external-address"))
        forbidden = ("HOST_PROXY_PORT=", "PI_PROXY_URL", "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "://")
        self.assertFalse(any(token in arg for arg in args for token in forbidden))


class TestHostAccessPlanningRed(unittest.TestCase):
    def _inventory(self, directory: Path, policy: str) -> Path:
        canonical = (Path(__file__).resolve().parents[1] / "docker-constructor.toml").read_text()
        path = directory / "custom.toml"
        path.write_text(canonical + "\n" + policy)
        return path

    def _request(self, inventory: Path, *, dry_run: bool, effects: list[str]):
        from docker.launcher import ProjectSelection, RunRequest

        class BombExecutor:
            def run(self, _args, *, interactive=False):
                del interactive
                effects.append("execution")
                raise AssertionError("Docker execution must not run")

        class BombInspector:
            def list_names(self):
                effects.append("inspection")
                raise AssertionError("container inspection must not run")

        def bomb_projection(*_args, **_kwargs):
            effects.append("projection")
            raise AssertionError("projection publication must not run")

        def bomb_artifact(*_args, **_kwargs):
            effects.append("materialization")
            raise AssertionError("artifact materialization must not run")

        return RunRequest(
            inventory_path=str(inventory), image="pi-cli-pi:latest",
            selection=ProjectSelection(main_project="/work/project"),
            pi_home_host="/home/user/.pi", dry_run=dry_run,
            executor=BombExecutor(), inspector=BombInspector(),
            _create_projection=bomb_projection, _artifact_fetcher=bomb_artifact,
        )

    def test_enabled_missing_or_malformed_local_state_fails_before_effects(self):
        from unittest.mock import patch

        from docker.launcher import orchestrate_run

        policy = '[runtime.host-access]\nenabled = true\nmode = "docker-gateway"\n'
        for local_bytes in (None, b"not = ["):
            with self.subTest(local_bytes=local_bytes), tempfile.TemporaryDirectory() as root:
                root_path = Path(root)
                inventory = self._inventory(root_path, policy)
                companion = root_path / "custom.local.toml"
                if local_bytes is not None:
                    companion.write_bytes(local_bytes)
                effects: list[str] = []
                req = self._request(inventory, dry_run=False, effects=effects)

                def bomb_materialize(*_args, **_kwargs):
                    effects.append("materialization")
                    raise AssertionError("artifact materialization must not run")

                with patch("docker.launcher.artifact_cache.materialize_selected_artifacts", bomb_materialize):
                    result = orchestrate_run(req)
                self.assertEqual(result.exit_kind.value, "config")
                self.assertRegex(result.message or "", "doctor|local")
                self.assertEqual(effects, [])

    def test_orchestrate_dry_run_renders_policy_and_never_mutates_companion(self):
        from docker.launcher import orchestrate_run

        scenarios = (
            # Disabled access must not read or require malformed host state.
            ('[runtime.host-access]\nenabled = false\n', b"[host-access]\naddress = 42\n", (), ("--add-host", "HOST_ACCESS_ADDRESS=", "HOST_PROXY_PORT=")),
            ('[runtime.host-access]\nenabled = true\nmode = "external-address"\nproxy-port = 1080\n',
             b'[host-access]\naddress = "192.0.2.10"\n',
             ("host.docker.internal:192.0.2.10", "HOST_ACCESS_ADDRESS=192.0.2.10", "HOST_PROXY_PORT=1080"), ()),
        )
        for policy, local_bytes, expected, absent in scenarios:
            with self.subTest(policy=policy), tempfile.TemporaryDirectory() as root:
                root_path = Path(root)
                inventory = self._inventory(root_path, policy)
                companion = root_path / "custom.local.toml"
                companion.write_bytes(local_bytes)
                before = companion.read_bytes()
                result = orchestrate_run(self._request(inventory, dry_run=True, effects=[]))
                self.assertEqual(result.exit_kind.value, "success")
                for value in expected:
                    self.assertIn(value, result.run_args)
                for value in absent:
                    self.assertFalse(any(value in arg for arg in result.run_args))
                self.assertEqual(companion.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
