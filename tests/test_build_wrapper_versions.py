"""Tests for ``build_wrapper.py`` version resolution integration.

Mock ``subprocess.run``, ``docker_rootless``, host probing, and
confirmations.  Verify that version values come from ``rendering.py``,
not from ``.env`` or hardcoded constants.
"""
from __future__ import annotations

import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tests.versioning.support.inventory_builder import minimal_toml, write_toml


def _python_override_toml() -> str:
    return minimal_toml(
        **{
            "stages.toolchain.python": (
                'version = "3.14.6"\n'
                "\n"
                "[stages.toolchain.python.override]\n"
                'constraint = ">=3.14.6"\n'
                "allow_prerelease = false\n"
                'scheme = "numeric"'
            ),
        }
    )


class TestResolveBuildInputs(unittest.TestCase):
    """Direct tests for ``resolve_build_inputs()``."""

    def setUp(self):
        self.toml_path = write_toml(_python_override_toml())

    def tearDown(self):
        self.toml_path.unlink(missing_ok=True)

    def test_default_returns_all_expected_variables(self):
        from docker.build_wrapper import resolve_build_inputs

        env = resolve_build_inputs(inventory_path=self.toml_path)
        self.assertIn("NODE_BASE_IMAGE", env)
        self.assertIn("PYTHON_VERSION", env)
        self.assertIn("RUST_VERSION", env)
        self.assertEqual(env["PYTHON_VERSION"], "3.14.6")

    def test_override_changes_version(self):
        from docker.build_wrapper import resolve_build_inputs

        env = resolve_build_inputs(
            inventory_path=self.toml_path,
            overrides={"stages.toolchain.python.version": "3.14.7"},
        )
        self.assertEqual(env["PYTHON_VERSION"], "3.14.7")

    def test_version_values_are_not_from_environ(self):
        """Version values must come from inventory, not os.environ."""
        from docker.build_wrapper import resolve_build_inputs

        with mock.patch.dict(os.environ, {"PYTHON_VERSION": "9.9.9"}):
            env = resolve_build_inputs(inventory_path=self.toml_path)
        self.assertEqual(env["PYTHON_VERSION"], "3.14.6")

    def test_all_values_are_strings(self):
        from docker.build_wrapper import resolve_build_inputs

        env = resolve_build_inputs(inventory_path=self.toml_path)
        for k, v in env.items():
            self.assertIsInstance(v, str,
                                  f"{k} is {type(v).__name__}")

    def test_writes_effective_inventory_to_disk(self):
        """resolve_build_inputs must write the effective inventory TOML
        so that the Docker build can COPY it — EFFECTIVE_VERSIONS_FILE
        alone is not enough."""
        from docker.build_wrapper import resolve_build_inputs

        # Point ROOT to a tempdir so .docker-generated/ is created there
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            with mock.patch("docker.build_wrapper.ROOT", root):
                env = resolve_build_inputs(
                    inventory_path=self.toml_path,
                    inventory_output=".docker-generated/versions.toml",
                )

            generated = root / ".docker-generated" / "versions.toml"
            self.assertTrue(
                generated.is_file(),
                f"Effective inventory not written: {generated}",
            )

            # Verify it's valid TOML with expected keys
            import tomllib
            with open(generated, "rb") as f:
                data = tomllib.load(f)
            self.assertIn("stages", data)
            self.assertIn("toolchain", data["stages"])

            # EFFECTIVE_VERSIONS_FILE must point to the generated file
            self.assertEqual(
                env.get("EFFECTIVE_VERSIONS_FILE"),
                ".docker-generated/versions.toml",
            )
    def test_operational_env_values_preserved_in_compose_env(self):
        """Values from .env (like API keys, HOST_GATEWAY_IP) must survive
        the merge — version values only override conflicting version keys."""
        import docker.build_wrapper as bw

        # Simulate a loaded .env with operational values
        fake_dotenv = {
            "CUSTOM_API_KEY": "secret123",
            "PYTHON_VERSION": "9.9.9",  # should be overridden
            "HOST_GATEWAY_IP": "10.0.0.1",
        }

        with mock.patch.object(bw, "docker_rootless", return_value=False):
            with mock.patch.object(bw, "load_dotenv", return_value=fake_dotenv):
                with mock.patch.object(bw, "run_diagnosis") as mock_diag:
                    mock_diag.return_value = bw.Diagnosis(
                        rootless=False,
                        probe_port=9999,
                        probe_token="OK",
                        lan_ip=None,
                        chosen_gateway="host-gateway",
                    )
                    mock_diag.return_value.probes = [
                        bw.ProbeResult("host-gateway", True, "10.0.0.2", "ok"),
                    ]
                    type(mock_diag.return_value).host_gateway_ip = (
                        mock.PropertyMock(return_value="10.0.0.2")
                    )

                    with mock.patch.object(bw, "confirm", return_value=True):
                        with mock.patch("subprocess.run") as mock_run:
                            mock_run.return_value = mock.MagicMock(returncode=0)
                            with mock.patch.object(bw, "update_env_file"):
                                import sys
                                argv = [
                                    "build_wrapper.py",
                                    "build",
                                    "--yes",
                                    "--inventory", str(self.toml_path),
                                ]
                                with mock.patch.object(sys, "argv", argv):
                                    try:
                                        code = bw.main()
                                    except SystemExit as e:
                                        code = int(e.code)

                    self.assertEqual(code, 0)

                    # Extract the env passed to subprocess.run
                    for call in mock_run.call_args_list:
                        args, kwargs = call
                        if "docker" in str(args[0][0]):
                            env = kwargs.get("env", {})
                            # Operational value preserved
                            self.assertEqual(
                                env.get("CUSTOM_API_KEY"), "secret123",
                                ".env operational values must survive",
                            )
                            # Version value overrides .env value
                            self.assertEqual(
                                env.get("PYTHON_VERSION"), "3.14.6",
                                "version value must override .env "
                                "PYTHON_VERSION=9.9.9",
                            )
                            # Diagnostic HOST_GATEWAY_IP overrides .env
                            self.assertEqual(
                                env.get("HOST_GATEWAY_IP"), "10.0.0.2",
                                "diagnosis must override .env "
                                "HOST_GATEWAY_IP=10.0.0.1",
                            )
                            break
    def test_duplicate_override_rejected_not_last_value_wins(self):
        """Duplicate overrides must be rejected, not silently
        accept the last value."""
        import docker.build_wrapper as bw

        with mock.patch.object(bw, "docker_rootless", return_value=False):
            with mock.patch.object(bw, "run_diagnosis") as mock_diag:
                mock_diag.return_value = bw.Diagnosis(
                    rootless=False,
                    probe_port=9999,
                    probe_token="OK",
                    lan_ip=None,
                    chosen_gateway="host-gateway",
                )
                mock_diag.return_value.probes = [
                    bw.ProbeResult("host-gateway", True, "10.0.0.1", "ok"),
                ]
                type(mock_diag.return_value).host_gateway_ip = (
                    mock.PropertyMock(return_value="10.0.0.1")
                )

                with mock.patch.object(bw, "confirm", return_value=True):
                    with mock.patch("subprocess.run") as mock_run:
                        import sys
                        argv = [
                            "build_wrapper.py",
                            "build",
                            "--yes",
                            "--inventory", str(self.toml_path),
                            "--override",
                            "stages.toolchain.python.version=3.14.6",
                            "--override",
                            "stages.toolchain.python.version=3.14.7",
                        ]
                        with mock.patch.object(sys, "argv", argv):
                            try:
                                code = bw.main()
                            except SystemExit as e:
                                code = int(e.code)

                    self.assertEqual(code, 2,
                                     "duplicate override should exit 2")
                    mock_run.assert_not_called()

    def test_invalid_inventory_caught_not_traceback(self):
        """A nonexistent inventory file must produce a clean error,
        not a traceback."""
        import docker.build_wrapper as bw

        with mock.patch.object(bw, "docker_rootless", return_value=False):
            with mock.patch("subprocess.run") as mock_run:
                import sys
                import io
                argv = [
                    "build_wrapper.py",
                    "build",
                    "--yes",
                    "--inventory", "/nonexistent/inventory.toml",
                ]
                captured = io.StringIO()
                with mock.patch.object(sys, "argv", argv):
                    with mock.patch.object(sys, "stderr", captured):
                        try:
                            code = bw.main()
                        except SystemExit as e:
                            code = int(e.code)

                self.assertNotEqual(code, 0)
                mock_run.assert_not_called()
                output = captured.getvalue()
                self.assertNotIn("Traceback", output)
                self.assertIn("error:", output.lower())


class TestBuildWrapperVersionIntegration(unittest.TestCase):
    """Integration: mocked build_wrapper main() with fake Docker."""

    def setUp(self):
        self.toml_path = write_toml(_python_override_toml())
        self.tmpdir = Path(tempfile.mkdtemp())

    def tearDown(self):
        self.toml_path.unlink(missing_ok=True)
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_version_env_passed_to_compose_build(self):
        """When build_wrapper runs, compose_build must receive the
        resolved version environment combined with HOST_GATEWAY_IP."""
        import docker.build_wrapper as bw

        # Mock everything that touches Docker or filesystem
        with mock.patch.object(bw, "docker_rootless", return_value=False):
            with mock.patch.object(bw, "run_diagnosis") as mock_diag:
                mock_diag.return_value = bw.Diagnosis(
                    rootless=False,
                    probe_port=9999,
                    probe_token="OK",
                    lan_ip=None,
                    chosen_gateway="host-gateway",
                )
                mock_diag.return_value.probes = [
                    bw.ProbeResult("host-gateway", True, "10.0.0.1", "ok"),
                ]
                # Make host_gateway_ip property work
                type(mock_diag.return_value).host_gateway_ip = mock.PropertyMock(
                    return_value="10.0.0.1",
                )

                with mock.patch.object(bw, "confirm", return_value=True):
                    with mock.patch("subprocess.run") as mock_run:
                        mock_run.return_value = subprocess.CompletedProcess(
                            args=[], returncode=0, stdout="", stderr="",
                        )
                        with mock.patch.object(bw, "update_env_file"):
                            import sys
                            argv = [
                                "build_wrapper.py",
                                "build",
                                "--yes",
                                "--inventory", str(self.toml_path),
                            ]
                            with mock.patch.object(sys, "argv", argv):
                                try:
                                    code = bw.main()
                                except SystemExit as e:
                                    code = int(e.code)

                        self.assertEqual(code, 0)

                        # Verify compose_build was called with version env
                        compose_calls = [
                            c for c in mock_run.call_args_list
                            if "docker" in str(c.args) and "compose" in str(c.args)
                        ]
                        self.assertTrue(
                            len(compose_calls) > 0,
                            "docker compose was not invoked",
                        )

                        # The environment passed to subprocess.run must
                        # include version variables from rendering.py
                        for call in mock_run.call_args_list:
                            args, kwargs = call
                            if "docker" in str(args[0][0]):
                                env = kwargs.get("env", {})
                                if "PYTHON_VERSION" in env:
                                    self.assertEqual(
                                        env["PYTHON_VERSION"], "3.14.6",
                                    )
                                    self.assertIn("NODE_BASE_IMAGE", env)
                                    break

    def test_version_environment_not_overwritten_by_os_environ(self):
        """Even if os.environ has PYTHON_VERSION=9.9.9, the resolved
        value from inventory must win."""
        import docker.build_wrapper as bw

        with mock.patch.object(bw, "docker_rootless", return_value=False):
            with mock.patch.object(bw, "run_diagnosis") as mock_diag:
                mock_diag.return_value = bw.Diagnosis(
                    rootless=False,
                    probe_port=9999,
                    probe_token="OK",
                    lan_ip=None,
                    chosen_gateway="host-gateway",
                )
                mock_diag.return_value.probes = [
                    bw.ProbeResult("host-gateway", True, "10.0.0.1", "ok"),
                ]
                type(mock_diag.return_value).host_gateway_ip = mock.PropertyMock(
                    return_value="10.0.0.1",
                )

                with mock.patch.object(bw, "confirm", return_value=True):
                    with mock.patch("subprocess.run") as mock_run:
                        mock_run.return_value = subprocess.CompletedProcess(
                            args=[], returncode=0, stdout="", stderr="",
                        )
                        with mock.patch.object(bw, "update_env_file"):
                            import sys
                            argv = [
                                "build_wrapper.py",
                                "build",
                                "--yes",
                                "--inventory", str(self.toml_path),
                            ]
                            with mock.patch.dict(
                                os.environ,
                                {"PYTHON_VERSION": "9.9.9"},
                            ):
                                with mock.patch.object(sys, "argv", argv):
                                    try:
                                        code = bw.main()
                                    except SystemExit as e:
                                        code = int(e.code)

                        self.assertEqual(code, 0)

                        for call in mock_run.call_args_list:
                            args, kwargs = call
                            if "docker" in str(args[0][0]):
                                env = kwargs.get("env", {})
                                if "PYTHON_VERSION" in env:
                                    self.assertEqual(
                                        env["PYTHON_VERSION"], "3.14.6",
                                        "os.environ PYTHON_VERSION=9.9.9 "
                                        "must not override resolved 3.14.6",
                                    )
                                    break

    def test_compose_nonzero_exit_propagated(self):
        """build_wrapper must propagate Compose exit code."""
        import docker.build_wrapper as bw

        with mock.patch.object(bw, "docker_rootless", return_value=False):
            with mock.patch.object(bw, "run_diagnosis") as mock_diag:
                mock_diag.return_value = bw.Diagnosis(
                    rootless=False,
                    probe_port=9999,
                    probe_token="OK",
                    lan_ip=None,
                    chosen_gateway="host-gateway",
                )
                mock_diag.return_value.probes = [
                    bw.ProbeResult("host-gateway", True, "10.0.0.1", "ok"),
                ]
                type(mock_diag.return_value).host_gateway_ip = mock.PropertyMock(
                    return_value="10.0.0.1",
                )

                with mock.patch.object(bw, "confirm", return_value=True):
                    with mock.patch("subprocess.run") as mock_run:
                        mock_run.return_value = subprocess.CompletedProcess(
                            args=[], returncode=42, stdout="", stderr="",
                        )
                        with mock.patch.object(bw, "update_env_file"):
                            import sys
                            argv = [
                                "build_wrapper.py",
                                "build",
                                "--yes",
                                "--inventory", str(self.toml_path),
                            ]
                            with mock.patch.object(sys, "argv", argv):
                                try:
                                    code = bw.main()
                                except SystemExit as e:
                                    code = int(e.code)

                        self.assertEqual(code, 42,
                                         "expected exit 42 from Compose")


if __name__ == "__main__":
    unittest.main()
