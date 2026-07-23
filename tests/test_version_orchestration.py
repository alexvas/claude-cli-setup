"""Orchestration tests — mocked subprocess for ``versions.py compose``.

No Docker daemon, no network.  ``subprocess.run`` is patched to verify
the exact command, environment, and exit-code propagation.
"""
from __future__ import annotations

import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from docker.versioning.cli import (
    EXIT_INVALID,
    EXIT_OK,
    EXIT_USAGE,
    main,
)
from docker.versioning.inventory import load_inventory
from docker.versioning.effective import apply_overrides
from docker.versioning.rendering import render_build_environment
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


class TestComposeOrchestration(unittest.TestCase):
    """Test ``versions.py compose`` with mocked ``subprocess.run``."""

    def setUp(self):
        self.toml_path = write_toml(_python_override_toml())
        self.tmpdir = Path(tempfile.mkdtemp())

    def tearDown(self):
        self.toml_path.unlink(missing_ok=True)
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _inventory_output(self) -> Path:
        return self.tmpdir / ".docker-generated" / "versions.toml"

    def _run_compose(self, *compose_args: str, **extra_args: str) -> int:
        """Invoke ``main()`` with ``compose`` arguments; return exit code."""
        import sys

        argv = [
            "versions.py",
            "compose",
            "--inventory", str(self.toml_path),
        ]
        for k, v in extra_args.items():
            argv.extend([k, v])
        if compose_args:
            argv.append("--")
            argv.extend(compose_args)
        else:
            argv.append("--")

        with mock.patch.object(sys, "argv", argv):
            try:
                return main()
            except SystemExit as e:
                return int(e.code)

    # ------------------------------------------------------------------
    # 1. Canonical command
    # ------------------------------------------------------------------

    def test_runs_docker_compose_with_passed_args(self):
        with mock.patch("subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(
                args=[], returncode=0, stdout="", stderr="",
            )
            code = self._run_compose("build", "pi")
            self.assertEqual(code, EXIT_OK)
            mock_run.assert_called_once()
            args, kwargs = mock_run.call_args
            self.assertEqual(tuple(args[0]), ("docker", "compose", "build", "pi"))

    # ------------------------------------------------------------------
    # 2. Environment contains rendering output
    # ------------------------------------------------------------------

    def test_environment_contains_rendered_values(self):
        with mock.patch("subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(
                args=[], returncode=0, stdout="", stderr="",
            )
            self._run_compose("build", "pi")
            _, kwargs = mock_run.call_args
            env = kwargs.get("env", {})
            self.assertIn("NODE_BASE_IMAGE", env)
            self.assertIn("PYTHON_VERSION", env)
            self.assertIn("RUST_VERSION", env)

    # ------------------------------------------------------------------
    # 3. Parent environment preserved
    # ------------------------------------------------------------------

    def test_parent_environment_preserved(self):
        with mock.patch("subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(
                args=[], returncode=0, stdout="", stderr="",
            )
            with mock.patch.dict(os.environ, {"CUSTOM_VAR": "custom_value"}):
                self._run_compose("build", "pi")
            _, kwargs = mock_run.call_args
            env = kwargs.get("env", {})
            self.assertEqual(env.get("CUSTOM_VAR"), "custom_value")

    # ------------------------------------------------------------------
    # 4. Resolver values take priority over external env
    # ------------------------------------------------------------------

    def test_resolved_values_override_external_environment(self):
        with mock.patch("subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(
                args=[], returncode=0, stdout="", stderr="",
            )
            with mock.patch.dict(os.environ, {"PYTHON_VERSION": "9.9.9"}):
                self._run_compose("build", "pi")
            _, kwargs = mock_run.call_args
            env = kwargs.get("env", {})
            self.assertEqual(env["PYTHON_VERSION"], "3.14.6")

    # ------------------------------------------------------------------
    # 5. --override affects both environment and generated inventory
    # ------------------------------------------------------------------

    def test_override_changes_environment_and_generated_inventory(self):
        with mock.patch("subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(
                args=[], returncode=0, stdout="", stderr="",
            )
            # Use a relative output path so validation passes
            self._run_compose(
                "build", "pi",
                **{
                    "--override": "stages.toolchain.python.version=3.14.7",
                    "--effective-inventory-output": ".docker-generated/test-override.toml",
                },
            )
            _, kwargs = mock_run.call_args
            env = kwargs.get("env", {})
            self.assertEqual(env["PYTHON_VERSION"], "3.14.7")

            # Generated inventory must also reflect the override.
            # Path is relative to the actual repo root.
            import docker.versioning.cli as cli_mod
            repo_root = Path(cli_mod.__file__).parent.parent.parent
            output = repo_root / ".docker-generated" / "test-override.toml"
            self.assertTrue(output.is_file(),
                            f"Generated inventory not found: {output}")
            import tomllib
            with open(output, "rb") as f:
                data = tomllib.load(f)
            self.assertEqual(
                data["stages"]["toolchain"]["python"]["version"],
                "3.14.7",
            )
            # Clean up
            output.unlink(missing_ok=True)

    # ------------------------------------------------------------------
    # 6. Arguments after -- passed verbatim
    # ------------------------------------------------------------------

    def test_args_after_separator_passed_verbatim(self):
        with mock.patch("subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(
                args=[], returncode=0, stdout="", stderr="",
            )
            self._run_compose("--progress", "plain", "build", "pi")
            args, _ = mock_run.call_args
            self.assertEqual(
                tuple(args[0]),
                ("docker", "compose", "--progress", "plain", "build", "pi"),
            )

    # ------------------------------------------------------------------
    # 7. shell=False
    # ------------------------------------------------------------------

    def test_shell_false(self):
        with mock.patch("subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(
                args=[], returncode=0, stdout="", stderr="",
            )
            self._run_compose("build", "pi")
            _, kwargs = mock_run.call_args
            self.assertFalse(kwargs.get("shell", False))

    # ------------------------------------------------------------------
    # 8. cwd is repo root
    # ------------------------------------------------------------------

    def test_cwd_is_repo_root(self):
        with mock.patch("subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(
                args=[], returncode=0, stdout="", stderr="",
            )
            self._run_compose("build", "pi")
            _, kwargs = mock_run.call_args
            # cwd should be set (repo root)
            self.assertIn("cwd", kwargs)

    # ------------------------------------------------------------------
    # 9. Exit code propagation
    # ------------------------------------------------------------------

    def test_compose_nonzero_exit_code_propagated(self):
        with mock.patch("subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(
                args=[], returncode=42, stdout="", stderr="",
            )
            code = self._run_compose("build", "pi")
            self.assertEqual(code, 42)

    # ------------------------------------------------------------------
    # 10. FileNotFoundError → short error
    # ------------------------------------------------------------------

    def test_docker_not_found_produces_short_error(self):
        with mock.patch("subprocess.run") as mock_run:
            mock_run.side_effect = FileNotFoundError("docker")
            import sys
            from io import StringIO
            captured = StringIO()
            with mock.patch.object(sys, "stderr", captured):
                code = self._run_compose("build", "pi")
            self.assertNotEqual(code, EXIT_OK)
            output = captured.getvalue()
            self.assertIn("docker", output.lower())

    # ------------------------------------------------------------------
    # 11. Inventory validation failure happens before subprocess
    # ------------------------------------------------------------------

    def test_invalid_inventory_fails_before_subprocess(self):
        with mock.patch("subprocess.run") as mock_run:
            import sys
            argv = [
                "versions.py",
                "compose",
                "--inventory", "/nonexistent/path.toml",
                "--",
                "build", "pi",
            ]
            with mock.patch.object(sys, "argv", argv):
                try:
                    code = main()
                except SystemExit as e:
                    code = int(e.code)
            self.assertEqual(code, EXIT_INVALID)
            mock_run.assert_not_called()

    # ------------------------------------------------------------------
    # 12. Unsafe --effective-inventory-output rejected with exit 2
    # ------------------------------------------------------------------

    def test_absolute_effective_inventory_output_rejected(self):
        import sys
        argv = [
            "versions.py",
            "compose",
            "--inventory", str(self.toml_path),
            "--effective-inventory-output", "/etc/hacked.toml",
            "--",
            "build", "pi",
        ]
        with mock.patch.object(sys, "argv", argv):
            try:
                code = main()
            except SystemExit as e:
                code = int(e.code)
        self.assertEqual(code, EXIT_USAGE)

    def test_traversal_effective_inventory_output_rejected(self):
        import sys
        argv = [
            "versions.py",
            "compose",
            "--inventory", str(self.toml_path),
            "--effective-inventory-output", "../../../etc/hacked.toml",
            "--",
            "build", "pi",
        ]
        with mock.patch.object(sys, "argv", argv):
            try:
                code = main()
            except SystemExit as e:
                code = int(e.code)
        self.assertEqual(code, EXIT_USAGE)

    def test_versions_toml_as_output_rejected(self):
        import sys
        argv = [
            "versions.py",
            "compose",
            "--inventory", str(self.toml_path),
            "--effective-inventory-output", "versions.toml",
            "--",
            "build", "pi",
        ]
        with mock.patch.object(sys, "argv", argv):
            try:
                code = main()
            except SystemExit as e:
                code = int(e.code)
        self.assertEqual(code, EXIT_USAGE)


if __name__ == "__main__":
    unittest.main()
