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
from docker.versioning.rendering import compose_command as render_compose_command
from tests.versioning.support.inventory_builder import minimal_toml, write_toml

_REPO_ROOT = Path(__file__).resolve().parent.parent
_BASE_COMPOSE = _REPO_ROOT / "docker-compose.yml"
_RUNTIME_COMPOSE = _REPO_ROOT / "docker-compose.runtime.yml"


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


class TestBuildRuntimeSeparation(unittest.TestCase):
    """RED tests — prove that build and runtime compose configuration
    are not yet separated."""

    def test_base_compose_does_not_reference_project_path(self):
        """The base docker-compose.yml must not contain PROJECT_PATH
        references or the .pi home-directory volume — those belong to
        runtime configuration only."""
        text = _BASE_COMPOSE.read_text(encoding="utf-8")
        self.assertNotIn(
            "PROJECT_PATH", text,
            "docker-compose.yml must not reference PROJECT_PATH_* — "
            "runtime concerns belong in docker-compose.runtime.yml",
        )
        self.assertNotIn(
            "${HOME}/.pi", text,
            "docker-compose.yml must not mount ${HOME}/.pi — "
            "that is a runtime concern",
        )

    def test_runtime_compose_has_dot_pi_volume(self):
        """The runtime compose file must mount the host .pi directory."""
        text = _RUNTIME_COMPOSE.read_text(encoding="utf-8")
        self.assertIn("${HOME}/.pi:/home/dev/.pi", text)

    def test_runtime_compose_exists(self):
        """A separate runtime compose file must exist and contain the
        strict project-path requirements."""
        self.assertTrue(
            _RUNTIME_COMPOSE.is_file(),
            "docker-compose.runtime.yml must exist with runtime-only "
            "service configuration",
        )

    def test_runtime_compose_requires_project_path(self):
        """The runtime compose file must enforce PROJECT_PATH_1
        so that low-level 'docker compose run pi' still fails without
        a selected project."""
        text = _RUNTIME_COMPOSE.read_text(encoding="utf-8")
        self.assertIn("PROJECT_PATH_1", text)
        # The strict :? form must be present so Compose fails early
        self.assertRegex(text, r"PROJECT_PATH_1:\?")

    def test_base_compose_build_args_preserved(self):
        """The base docker-compose.yml must still contain all required
        version build arguments."""
        text = _BASE_COMPOSE.read_text(encoding="utf-8")
        required_args = (
            "NODE_BASE_IMAGE", "RUST_VERSION", "PYTHON_VERSION",
            "PI_VERSION", "EFFECTIVE_VERSIONS_FILE",
        )
        for arg in required_args:
            self.assertIn(
                arg, text,
                f"docker-compose.yml must preserve build arg: {arg}",
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
        return self.tmpdir / ".docker-generated" / "docker-constructor.toml"

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
            "--effective-inventory-output", "docker-constructor.toml",
            "--",
            "build", "pi",
        ]
        with mock.patch.object(sys, "argv", argv):
            try:
                code = main()
            except SystemExit as e:
                code = int(e.code)
        self.assertEqual(code, EXIT_USAGE)
    # ------------------------------------------------------------------
    # Build/runtime separation — subprocess tests (tasks 1.1, 1.2, 3.3)
    # ------------------------------------------------------------------

    def test_build_does_not_need_project_path(self):
        """'compose build' must not include the runtime compose file
        — build succeeds without project config or HOME."""
        with mock.patch("subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(
                args=[], returncode=0, stdout="", stderr="",
            )
            # Only PATH — no HOME, no PROJECT_PATH_*, no COMPOSE_FILE
            with mock.patch.dict(os.environ, {
                "PATH": os.environ.get("PATH", "/usr/bin"),
            }, clear=True):
                self._run_compose("build", "pi")
            args, kwargs = mock_run.call_args
            cmd = list(args[0])
            env = kwargs.get("env", {})
            # No runtime file in COMPOSE_FILE
            self.assertNotIn("docker-compose.runtime.yml", env.get("COMPOSE_FILE", ""))
            # No runtime file injected as -f arg
            self.assertNotIn("-f", cmd[:4] if len(cmd) >= 4 else cmd)

    def test_run_includes_runtime_compose_file(self):
        """'compose run' must include docker-compose.runtime.yml
        so that docker compose enforces PROJECT_PATH_1."""
        with mock.patch("subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(
                args=[], returncode=0, stdout="", stderr="",
            )
            with mock.patch.dict(os.environ, {
                "PATH": os.environ.get("PATH", "/usr/bin"),
                "HOME": os.environ.get("HOME", "/tmp"),
            }, clear=True):
                self._run_compose("run", "pi")
            _, kwargs = mock_run.call_args
            env = kwargs.get("env", {})
            compose_file = env.get("COMPOSE_FILE", "")
            self.assertIn("docker-compose.runtime.yml", compose_file)
            self.assertIn("docker-compose.yml", compose_file)

    # -- global option parsing (spaced form) -------------------------------

    def test_ansi_never_before_run_recognised(self):
        """--ansi never (value-consuming option) must not shadow 'run'."""
        with mock.patch("subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(
                args=[], returncode=0, stdout="", stderr="",
            )
            with mock.patch.dict(os.environ, {
                "PATH": os.environ.get("PATH", "/usr/bin"),
                "HOME": os.environ.get("HOME", "/tmp"),
            }, clear=True):
                self._run_compose("--ansi", "never", "run", "pi")
            _, kwargs = mock_run.call_args
            env = kwargs.get("env", {})
            self.assertIn(
                "docker-compose.runtime.yml", env.get("COMPOSE_FILE", ""),
                "--ansi never run pi must include runtime compose file",
            )

    def test_progress_plain_before_build_recognised(self):
        """--progress plain before build must not trigger runtime."""
        with mock.patch("subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(
                args=[], returncode=0, stdout="", stderr="",
            )
            with mock.patch.dict(os.environ, {
                "PATH": os.environ.get("PATH", "/usr/bin"),
                "HOME": os.environ.get("HOME", "/tmp"),
            }, clear=True):
                self._run_compose("--progress", "plain", "build", "pi")
            _, kwargs = mock_run.call_args
            self.assertNotIn(
                "docker-compose.runtime.yml",
                kwargs.get("env", {}).get("COMPOSE_FILE", ""),
            )

    def test_parallel_n_before_build_recognised(self):
        """--parallel 4 before build must not confuse detection."""
        with mock.patch("subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(
                args=[], returncode=0, stdout="", stderr="",
            )
            with mock.patch.dict(os.environ, {
                "PATH": os.environ.get("PATH", "/usr/bin"),
                "HOME": os.environ.get("HOME", "/tmp"),
            }, clear=True):
                self._run_compose("--parallel", "4", "build", "pi")
            _, kwargs = mock_run.call_args
            self.assertNotIn(
                "docker-compose.runtime.yml",
                kwargs.get("env", {}).get("COMPOSE_FILE", ""),
            )

    # -- option=value form -------------------------------------------------

    def test_option_equals_value_run_detected(self):
        """--profile=debug (single-token form) must not shadow 'run'."""
        with mock.patch("subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(
                args=[], returncode=0, stdout="", stderr="",
            )
            with mock.patch.dict(os.environ, {
                "PATH": os.environ.get("PATH", "/usr/bin"),
                "HOME": os.environ.get("HOME", "/tmp"),
            }, clear=True):
                self._run_compose("--profile=debug", "run", "pi")
            _, kwargs = mock_run.call_args
            env = kwargs.get("env", {})
            self.assertIn("docker-compose.runtime.yml", env.get("COMPOSE_FILE", ""))

    def test_option_equals_value_build_detected(self):
        """--progress=plain (single-token form) before build must not
        trigger runtime."""
        with mock.patch("subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(
                args=[], returncode=0, stdout="", stderr="",
            )
            with mock.patch.dict(os.environ, {
                "PATH": os.environ.get("PATH", "/usr/bin"),
                "HOME": os.environ.get("HOME", "/tmp"),
            }, clear=True):
                self._run_compose("--progress=plain", "build", "pi")
            _, kwargs = mock_run.call_args
            self.assertNotIn(
                "docker-compose.runtime.yml",
                kwargs.get("env", {}).get("COMPOSE_FILE", ""),
            )

    # -- -f / --file injection ---------------------------------------------

    def test_explicit_f_injects_files_not_env(self):
        """When the user passes -f, runtime files must be injected as
        leading -f pairs, not via COMPOSE_FILE (which -f overrides)."""
        with mock.patch("subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(
                args=[], returncode=0, stdout="", stderr="",
            )
            with mock.patch.dict(os.environ, {
                "PATH": os.environ.get("PATH", "/usr/bin"),
                "HOME": os.environ.get("HOME", "/tmp"),
            }, clear=True):
                self._run_compose("-f", "custom.yml", "run", "pi")
            args, kwargs = mock_run.call_args
            cmd = list(args[0])
            env = kwargs.get("env", {})
            # Must NOT set COMPOSE_FILE
            self.assertNotIn("COMPOSE_FILE", env)
            # Must inject -f docker-compose.yml -f docker-compose.runtime.yml
            # before the user's -f custom.yml
            self.assertIn("-f", cmd)
            idx_base = cmd.index("-f")
            self.assertEqual(cmd[idx_base + 1], "docker-compose.yml")
            self.assertEqual(cmd[idx_base + 2], "-f")
            self.assertEqual(cmd[idx_base + 3], "docker-compose.runtime.yml")
            # User's explicit file comes after
            self.assertIn("-f", cmd[idx_base + 4:])

    def test_explicit_file_long_form_injects_correctly(self):
        """--file custom.yml run pi must also inject runtime -f pair."""
        with mock.patch("subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(
                args=[], returncode=0, stdout="", stderr="",
            )
            with mock.patch.dict(os.environ, {
                "PATH": os.environ.get("PATH", "/usr/bin"),
                "HOME": os.environ.get("HOME", "/tmp"),
            }, clear=True):
                self._run_compose("--file", "custom.yml", "run", "pi")
            args, _ = mock_run.call_args
            cmd = list(args[0])
            self.assertIn("-f", cmd)

    def test_explicit_file_equals_form_injects_correctly(self):
        """--file=custom.yml (single token) run pi must inject runtime pair."""
        with mock.patch("subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(
                args=[], returncode=0, stdout="", stderr="",
            )
            with mock.patch.dict(os.environ, {
                "PATH": os.environ.get("PATH", "/usr/bin"),
                "HOME": os.environ.get("HOME", "/tmp"),
            }, clear=True):
                self._run_compose("--file=custom.yml", "run", "pi")
            args, kwargs = mock_run.call_args
            cmd = list(args[0])
            env = kwargs.get("env", {})
            self.assertNotIn("COMPOSE_FILE", env)
            self.assertIn("-f", cmd)

    def test_explicit_f_build_no_injection(self):
        """-f with build must NOT inject runtime files."""
        with mock.patch("subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(
                args=[], returncode=0, stdout="", stderr="",
            )
            with mock.patch.dict(os.environ, {
                "PATH": os.environ.get("PATH", "/usr/bin"),
                "HOME": os.environ.get("HOME", "/tmp"),
            }, clear=True):
                self._run_compose("-f", "custom.yml", "build", "pi")
            args, _ = mock_run.call_args
            cmd = list(args[0])
            # runtime files must appear nowhere in the command
            flat = " ".join(cmd)
            self.assertNotIn("docker-compose.runtime.yml", flat)

    # -- launcher COMPOSE_FILE boundary ------------------------------------

    def test_external_compose_file_respected(self):
        """When the caller (e.g. launcher) already sets COMPOSE_FILE,
        the resolver must not add the runtime file on top."""
        with mock.patch("subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(
                args=[], returncode=0, stdout="", stderr="",
            )
            with mock.patch.dict(os.environ, {
                "COMPOSE_FILE": (
                    "docker-compose.yml:docker-compose.runtime.yml"
                    ":/tmp/fragment.yml:/tmp/override.yml"
                ),
                "PATH": os.environ.get("PATH", "/usr/bin"),
                "HOME": os.environ.get("HOME", "/tmp"),
            }):
                self._run_compose("run", "pi")
            _, kwargs = mock_run.call_args
            env = kwargs.get("env", {})
            self.assertEqual(
                env.get("COMPOSE_FILE", ""),
                "docker-compose.yml:docker-compose.runtime.yml"
                ":/tmp/fragment.yml:/tmp/override.yml",
            )

    def test_launcher_produces_correct_command_and_compose_file(self):
        """Execution-level test: verify launcher's run_container builds
        the exact COMPOSE_FILE chain (base → runtime → fragments → override)
        and invokes versions.py compose run with a 1:1 mount for the main
        project."""
        import importlib.util
        import sys as _sys

        spec = importlib.util.spec_from_file_location(
            "launch_pi", _REPO_ROOT / "launch-pi.py",
        )
        launch_pi = importlib.util.module_from_spec(spec)
        _sys.modules["launch_pi"] = launch_pi
        spec.loader.exec_module(launch_pi)

        with mock.patch("subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(
                args=[], returncode=0, stdout="", stderr="",
            )
            with mock.patch.dict(os.environ, {
                "PATH": os.environ.get("PATH", "/usr/bin"),
                "HOME": os.environ.get("HOME", "/tmp"),
            }, clear=True):
                launch_pi.run_container(
                    main_path="/home/user/my-project",
                    mount_main_path="/home/user/my-project",
                    additional_projects=[
                        {"workspaceFolders": ["/home/user/lib"]},
                    ],
                    override_path=Path("/tmp/test-override.yml"),
                    extra_fragments=[Path("/tmp/test-fragment.yml")],
                    container_num=99,
                    dry_run=False,
                )

            args, kwargs = mock_run.call_args
            cmd = list(args[0])
            env = kwargs.get("env", {})

            # Canonical resolver wrapper
            self.assertEqual(cmd[0], "python3")
            self.assertIn("docker/versions.py", cmd[1])
            self.assertIn("compose", cmd)
            self.assertIn("run", cmd)
            self.assertIn("pi", cmd)

            # Main 1:1 mount is passed via env
            self.assertEqual(env.get("PROJECT_PATH_1"), "/home/user/my-project")

            # COMPOSE_FILE: base + runtime + fragments + override
            compose_file = env.get("COMPOSE_FILE", "")
            parts = compose_file.split(":")
            part_names = [Path(p).name for p in parts]
            self.assertEqual(part_names[0], "docker-compose.yml")
            self.assertEqual(part_names[1], "docker-compose.runtime.yml")
            self.assertIn("test-fragment.yml", part_names)
            self.assertIn("test-override.yml", part_names)
            # Runtime file comes before fragments
            rt_idx = part_names.index("docker-compose.runtime.yml")
            frag_idx = part_names.index("test-fragment.yml")
            self.assertLess(rt_idx, frag_idx,
                            "runtime compose must precede fragments")


if __name__ == "__main__":
    unittest.main()
