"""Subprocess-level tests for the versions.py CLI.

These tests run ``python3 docker/versions.py`` as a real process to
validate exit codes, output formats, and error messages.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import unittest
from pathlib import Path
from docker.versioning.cli import _shell_escape

_REPO_ROOT = Path(__file__).resolve().parent.parent
_VERSIONS_PY = _REPO_ROOT / "docker" / "versions.py"
_FIXTURES = _REPO_ROOT / "tests" / "fixtures" / "versions"


def _versions_py_cmd() -> list[str]:
    """Return the command line to invoke versions.py directly if
    the file is executable, otherwise through the interpreter."""
    if os.access(_VERSIONS_PY, os.X_OK):
        return [str(_VERSIONS_PY)]
    return [sys.executable, str(_VERSIONS_PY)]

# Minimal sanitized environment — no HOME to avoid config leakage
_SANITIZED_ENV: dict[str, str] = {}
for _k in ("PATH", "LANG", "LC_ALL"):
    if _k in os.environ:
        _SANITIZED_ENV[_k] = os.environ[_k]


def _run(*args: str, **kwargs: object) -> subprocess.CompletedProcess[str]:
    cmd = [sys.executable, str(_VERSIONS_PY), *args]
    return subprocess.run(
        cmd,
        cwd=str(_REPO_ROOT),
        text=True,
        capture_output=True,
        env=_SANITIZED_ENV,
        **kwargs,  # type: ignore[arg-type]
    )


# ---------------------------------------------------------------------------
# 2.1 Validate
# ---------------------------------------------------------------------------

class TestCliValidate(unittest.TestCase):
    def test_valid_inventory_exits_zero(self):
        result = _run("validate")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), "valid")
        self.assertEqual(result.stderr, "")

    def test_json_output_valid(self):
        result = _run("validate", "--json")
        self.assertEqual(result.returncode, 0, result.stderr)
        data = json.loads(result.stdout)
        self.assertEqual(data, {"valid": True})

    def test_invalid_fixture_exits_three(self):
        invalid_path = _FIXTURES / "missing-source.toml"
        result = _run("validate", "--inventory", str(invalid_path))
        self.assertEqual(result.returncode, 3, result.stderr)
        self.assertIn("source", result.stderr.lower())

    def test_nonexistent_inventory_exits_three(self):
        result = _run("validate", "--inventory", "/nonexistent/path.toml")
        self.assertEqual(result.returncode, 3, result.stderr)
        self.assertIn("inventory", result.stderr.lower())

    def test_malformed_toml_exits_three(self):
        import tempfile
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".toml", delete=False
        ) as tf:
            tf.write("this is not toml {{{")
            malformed = tf.name
        try:
            result = _run("validate", "--inventory", malformed)
            self.assertEqual(result.returncode, 3, result.stderr)
        finally:
            Path(malformed).unlink()

    def test_unreadable_file_exits_three(self):
        result = _run("validate", "--inventory", "/root/secret.toml")
        self.assertEqual(result.returncode, 3, result.stderr)

    def test_repeated_run_byte_identical(self):
        result1 = _run("validate")
        result2 = _run("validate")
        self.assertEqual(result1.stdout, result2.stdout)
        self.assertEqual(result1.stderr, result2.stderr)
        self.assertEqual(result1.returncode, result2.returncode)


# ---------------------------------------------------------------------------
# 2.2 Get
# ---------------------------------------------------------------------------

class TestCliGet(unittest.TestCase):
    def test_scalar_schema(self):
        result = _run("get", "schema")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), "1")

    def test_scalar_node_tag(self):
        result = _run("get", "build.stages.base.node.tag")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("trixie", result.stdout)

    def test_scalar_python_version(self):
        result = _run("get", "build.stages.toolchain.python.version")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), "3.14.6")

    def test_scalar_python_source_type(self):
        result = _run("get", "build.stages.toolchain.python.source.type")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), "uv-python")

    def test_scalar_override_constraint(self):
        result = _run("get", "build.stages.toolchain.python.override.constraint")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(">=3.14.6", result.stdout)

    def test_scalar_extension_version(self):
        result = _run("get", "runtime.pi-extensions.pi-read.version")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), "0.2.0")

    def test_container_path_json(self):
        result = _run("get", "build.stages.toolchain.python", "--json")
        self.assertEqual(result.returncode, 0, result.stderr)
        data = json.loads(result.stdout)
        self.assertIn("version", data)
        self.assertEqual(data["version"], "3.14.6")

    def test_container_extensions_json(self):
        result = _run("get", "runtime.pi-extensions", "--json")
        self.assertEqual(result.returncode, 0, result.stderr)
        data = json.loads(result.stdout)
        self.assertIn("pi-read", data)

    def test_root_path_json(self):
        result = _run("get", ".", "--json")
        self.assertEqual(result.returncode, 0, result.stderr)
        data = json.loads(result.stdout)
        self.assertIn("schema", data)
        self.assertIn("build", data)
        self.assertIn("stages", data["build"])

    def test_json_deterministic_ordering(self):
        result1 = _run("get", "build.stages.toolchain", "--json")
        result2 = _run("get", "build.stages.toolchain", "--json")
        self.assertEqual(result1.stdout, result2.stdout)

    def test_tuple_becomes_json_array(self):
        result = _run("get", "build.stages.toolchain.rust.components", "--json")
        data = json.loads(result.stdout)
        self.assertIsInstance(data, list)
        self.assertIn("rustfmt", data)

    # Negatives

    def test_unknown_path_exits_four(self):
        result = _run("get", "build.stages.toolchain.pythno.version")
        self.assertEqual(result.returncode, 4, result.stderr)
        self.assertIn("pythno", result.stderr)

    def test_missing_field_exits_four(self):
        result = _run("get", "build.stages.toolchain.python.missing")
        self.assertEqual(result.returncode, 4, result.stderr)
        self.assertIn("missing", result.stderr.lower())

    def test_unknown_extension_exits_four(self):
        result = _run("get", "runtime.pi-extensions.unknown.version")
        self.assertEqual(result.returncode, 4, result.stderr)
        self.assertIn("unknown", result.stderr.lower())

    def test_dunder_path_rejected(self):
        result = _run("get", "__class__")
        self.assertEqual(result.returncode, 4, result.stderr)
        self.assertIn("restricted", result.stderr.lower())


# ---------------------------------------------------------------------------
# 2.3 Env
# ---------------------------------------------------------------------------

class TestCliEnv(unittest.TestCase):
    EXPECTED_KEYS = frozenset({
        "NODE_BASE_IMAGE",
        "RUST_VERSION", "RUST_PROFILE", "RUST_COMPONENTS",
        "UV_VERSION", "UV_URL", "UV_SHA256",
        "PYTHON_VERSION",
        "TY_VERSION",
        "RTK_VERSION", "RTK_URL", "RTK_SHA256",
        "FD_VERSION", "FD_URL", "FD_SHA256",
        "PI_VERSION", "OPENSPEC_VERSION",
        "OH_MY_ZSH_VERSION",
        "PI_READ_VERSION", "PI_CODEX_USAGE_VERSION", "PI_PROXY_VERSION",
        "EFFECTIVE_VERSIONS_FILE",
    })

    _GENERATED_DIR = _REPO_ROOT / ".docker-generated"

    @classmethod
    def setUpClass(cls):
        cls._cleanup_generated()

    @classmethod
    def tearDownClass(cls):
        cls._cleanup_generated()

    @staticmethod
    def _cleanup_generated():
        import shutil
        generated = _REPO_ROOT / ".docker-generated"
        if generated.exists():
            shutil.rmtree(generated)

    def test_text_output_format(self):
        result = _run("env")
        self.assertEqual(result.returncode, 0, result.stderr)
        lines = result.stdout.strip().split("\n")
        for line in lines:
            self.assertRegex(line, r"^export [A-Z_][A-Z0-9_]*=", f"bad line: {line}")

    def test_json_output_format(self):
        result = _run("env", "--json")
        self.assertEqual(result.returncode, 0, result.stderr)
        data = json.loads(result.stdout)
        self.assertIsInstance(data, dict)
        for v in data.values():
            self.assertIsInstance(v, str)

    def test_expected_variables_present(self):
        result = _run("env", "--json")
        data = json.loads(result.stdout)
        keys = set(data.keys())
        for expected in self.EXPECTED_KEYS:
            self.assertIn(expected, keys, f"Missing env var: {expected}")

    def test_deterministic_ordering(self):
        result1 = _run("env")
        result2 = _run("env")
        self.assertEqual(result1.stdout, result2.stdout)

    def test_default_python_is_3146(self):
        result = _run("env", "--json")
        data = json.loads(result.stdout)
        self.assertEqual(data["PYTHON_VERSION"], "3.14.6")

    def test_no_diagnostic_in_stdout(self):
        result = _run("env")
        for line in result.stdout.strip().split("\n"):
            self.assertNotIn("shell", line.lower())

    def test_node_base_image_format(self):
        result = _run("env", "--json")
        data = json.loads(result.stdout)
        image = data["NODE_BASE_IMAGE"]
        self.assertRegex(image, r"^\S+/\S+:\S+@sha256:[a-f0-9]{64}$")

    def test_text_output_shell_safe_roundtrip(self):
        """env text output exports variables visible to child processes."""
        import subprocess
        result = _run("env")
        self.assertEqual(result.returncode, 0, result.stderr)

        # Child sh -c receives exported variables via eval
        r = subprocess.run(
            ["sh", "-c",
             "eval \"$1\"\n"
             + 'test "$RUST_COMPONENTS" = "rustfmt clippy"\n'
             + 'test "$PYTHON_VERSION" = "3.14.6"\n'
             + 'test -n "$FD_URL"\n'
             + 'echo "OK"',
             "_", result.stdout],
            capture_output=True,
            text=True,
        )
        self.assertEqual(r.returncode, 0,
                         f"stderr: {r.stderr}\nstdout: {r.stdout}")
        self.assertIn("OK", r.stdout)

    def test_text_output_preserves_spaces(self):
        """Values with embedded spaces survive shell round-trip intact."""
        result = _run("env")
        lines = result.stdout.strip().split("\n")
        for line in lines:
            if line.startswith("export RUST_COMPONENTS="):
                # The raw output should contain 'rustfmt clippy' inside quotes
                self.assertIn("'rustfmt clippy'", line)
                return
        self.fail("RUST_COMPONENTS not found in env output")

    def test_writes_effective_inventory_file(self):
        """env writes .docker-generated/docker-constructor.toml to disk."""
        result = _run("env")
        self.assertEqual(result.returncode, 0, result.stderr)
        generated = self._GENERATED_DIR / "docker-constructor.toml"
        self.assertTrue(generated.exists(),
                        f"Expected {generated} to exist after env")

    def test_effective_versions_file_env_var(self):
        """EFFECTIVE_VERSIONS_FILE is present and points to the generated path."""
        result = _run("env", "--json")
        data = json.loads(result.stdout)
        self.assertEqual(
            data["EFFECTIVE_VERSIONS_FILE"],
            ".docker-generated/docker-constructor.toml",
        )

    def test_effective_inventory_output_override(self):
        """--effective-inventory-output changes the generated file path."""
        result = _run(
            "env", "--json",
            "--effective-inventory-output", ".docker-generated/custom.toml",
        )
        data = json.loads(result.stdout)
        self.assertEqual(data["EFFECTIVE_VERSIONS_FILE"], ".docker-generated/custom.toml")

    def test_generated_inventory_is_loadable(self):
        """The generated TOML loads as a valid effective inventory."""
        from docker.versioning.inventory import load_inventory
        result = _run("env")
        self.assertEqual(result.returncode, 0, result.stderr)
        generated = self._GENERATED_DIR / "docker-constructor.toml"
        inv = load_inventory(generated)
        self.assertEqual(inv.schema, 1)
        self.assertEqual(inv.stages.toolchain.python.version, "3.14.6")

    def test_override_writes_effective_inventory(self):
        """env --override writes the overridden value into the generated file."""
        from docker.versioning.inventory import load_inventory
        result = _run(
            "env", "--json",
            "--override", "build.stages.toolchain.python.version=3.14.7",
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        data = json.loads(result.stdout)
        self.assertEqual(data["PYTHON_VERSION"], "3.14.7")
        # The generated file must also reflect the override
        generated = self._GENERATED_DIR / "docker-constructor.toml"
        inv = load_inventory(generated)
        self.assertEqual(inv.stages.toolchain.python.version, "3.14.7")

    def test_shell_roundtrip_includes_effective_versions_file(self):
        """eval "$(env)" exports EFFECTIVE_VERSIONS_FILE for downstream compose."""
        import subprocess as sp
        result = _run("env")
        self.assertEqual(result.returncode, 0, result.stderr)
        r = sp.run(
            ["sh", "-c",
             "eval \"$1\"\n"
             + 'test "$EFFECTIVE_VERSIONS_FILE" = ".docker-generated/docker-constructor.toml"\n'
             + 'test -f "$EFFECTIVE_VERSIONS_FILE"\n'
             + 'echo "OK"',
             "_", result.stdout],
            capture_output=True,
            text=True,
            cwd=str(_REPO_ROOT),
        )
        self.assertEqual(r.returncode, 0,
                         f"stderr: {r.stderr}\nstdout: {r.stdout}")
        self.assertIn("OK", r.stdout)

    def test_platform_default_is_linux_amd64(self):
        """Default platform produces linux-amd64 artifact URLs."""
        result = _run("env", "--json")
        data = json.loads(result.stdout)
        self.assertIn("x86_64-unknown-linux-gnu", data["UV_URL"])

    def test_platform_flag_accepted(self):
        """--platform linux-amd64 produces same result as default."""
        result_default = _run("env", "--json")
        result_explicit = _run("env", "--json", "--platform", "linux-amd64")
        self.assertEqual(result_default.stdout, result_explicit.stdout)

    def test_unknown_platform_exits_with_error(self):
        """--platform nonexistent-os exits with config error."""
        result = _run("env", "--platform", "nonexistent-os")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("error", result.stderr.lower())


# ---------------------------------------------------------------------------
# 2.4 Override
# ---------------------------------------------------------------------------

class TestCliOverride(unittest.TestCase):
    def test_override_get_python(self):
        result = _run(
            "get", "build.stages.toolchain.python.version",
            "--override", "build.stages.toolchain.python.version=3.14.7",
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), "3.14.7")

    def test_override_env_python(self):
        result = _run(
            "env", "--json",
            "--override", "build.stages.toolchain.python.version=3.14.7",
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        data = json.loads(result.stdout)
        self.assertEqual(data["PYTHON_VERSION"], "3.14.7")

    def test_override_effective_inventory(self):
        result = _run(
            "get", "build.stages.toolchain.python.version", "--json",
            "--override", "build.stages.toolchain.python.version=3.14.7",
        )
        data = json.loads(result.stdout)
        self.assertEqual(data, "3.14.7")

    def test_source_inventory_unchanged(self):
        """Default inventory still returns 3.14.6 even after override."""
        result = _run("get", "build.stages.toolchain.python.version")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), "3.14.6")

    # Negatives

    def test_override_rejects_short_version(self):
        result = _run(
            "get", "build.stages.toolchain.python.version",
            "--override", "build.stages.toolchain.python.version=3.14",
        )
        self.assertEqual(result.returncode, 6, result.stderr)
        self.assertIn("not a valid", result.stderr.lower())

    def test_override_rejects_v_prefix(self):
        result = _run(
            "get", "build.stages.toolchain.python.version",
            "--override", "build.stages.toolchain.python.version=v3.14.7",
        )
        self.assertEqual(result.returncode, 6, result.stderr)

    def test_override_rejects_prerelease(self):
        result = _run(
            "get", "build.stages.toolchain.python.version",
            "--override", "build.stages.toolchain.python.version=3.14.7-beta.1",
        )
        self.assertEqual(result.returncode, 6, result.stderr)

    def test_override_rejects_old_version(self):
        result = _run(
            "get", "build.stages.toolchain.python.version",
            "--override", "build.stages.toolchain.python.version=3.14.5",
        )
        self.assertEqual(result.returncode, 6, result.stderr)
        self.assertIn("does not satisfy", result.stderr)

    def test_override_rejects_latest(self):
        result = _run(
            "get", "build.stages.toolchain.python.version",
            "--override", "build.stages.toolchain.python.version=latest",
        )
        self.assertEqual(result.returncode, 6, result.stderr)

    def test_override_unsupported_path_exits_five(self):
        result = _run(
            "get", "build.stages.toolchain.python.version",
            "--override", "build.stages.toolchain.ty.version=0.0.62",
        )
        self.assertEqual(result.returncode, 5, result.stderr)

    def test_override_unknown_path_exits_five(self):
        result = _run(
            "get", "build.stages.toolchain.python.version",
            "--override", "unknown.path=1.0.0",
        )
        self.assertEqual(result.returncode, 5, result.stderr)

    def test_override_malformed_spaces_exits_two(self):
        result = _run(
            "get", "build.stages.toolchain.python.version",
            "--override", "build.stages.toolchain.python.version =3.14.7",
        )
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertIn("spaces", result.stderr.lower())


class TestShellEscape(unittest.TestCase):
    def test_plain_string(self):
        self.assertEqual(_shell_escape("hello"), "'hello'")

    def test_string_with_spaces(self):
        self.assertEqual(_shell_escape("rustfmt clippy"), "'rustfmt clippy'")

    def test_string_with_single_quote(self):
        self.assertEqual(_shell_escape("it's"), "'it'\\''s'")

    def test_string_with_single_quotes_multiple(self):
        self.assertEqual(
            _shell_escape("don't stop believin'"),
            "'don'\\''t stop believin'\\'''",
        )

    def test_empty_string(self):
        self.assertEqual(_shell_escape(""), "''")

    def test_string_with_special_chars(self):
        self.assertEqual(
            _shell_escape('$PATH "double"'),
            "'$PATH \"double\"'",
        )


# ---------------------------------------------------------------------------
# 1.1 Executable file mode
# ---------------------------------------------------------------------------

class TestExecutableFileMode(unittest.TestCase):
    """Verify that docker/versions.py has a portable shebang and is
    tracked as executable in Git."""

    def test_has_portable_python3_shebang(self):
        """First line must be the env-based Python 3 shebang."""
        first_line = _VERSIONS_PY.read_text(encoding="utf-8").splitlines()[0]
        self.assertEqual(
            first_line, "#!/usr/bin/env python3",
            f"Expected shebang, got: {first_line!r}",
        )

    def test_git_tracks_executable_mode(self):
        """File must have executable permission tracked in Git so that
        clones receive the +x mode on POSIX hosts."""
        import subprocess as sp
        proc = sp.run(
            ["git", "ls-files", "--stage", str(_VERSIONS_PY)],
            cwd=str(_REPO_ROOT),
            capture_output=True,
            text=True,
        )
        self.assertEqual(proc.returncode, 0,
                         f"git ls-files failed: {proc.stderr}")
        # Git index line: <mode> <hash> <stage> <path>
        # Executable files have mode 100755.
        mode = proc.stdout.strip().split()[0] if proc.stdout.strip() else ""
        self.assertEqual(
            mode, "100755",
            f"Expected Git mode 100755 (executable), got: {mode}",
        )


class TestDirectExecutionParity(unittest.TestCase):
    """Verify that direct execution produces identical output to
    interpreter-prefixed invocation."""

    @staticmethod
    def _run_direct(*args: str) -> subprocess.CompletedProcess[str]:
        cmd = [str(_VERSIONS_PY), *args]
        return subprocess.run(
            cmd,
            cwd=str(_REPO_ROOT),
            text=True,
            capture_output=True,
            env=_SANITIZED_ENV,
        )

    @staticmethod
    def _run_interpreter(*args: str) -> subprocess.CompletedProcess[str]:
        cmd = [sys.executable, str(_VERSIONS_PY), *args]
        return subprocess.run(
            cmd,
            cwd=str(_REPO_ROOT),
            text=True,
            capture_output=True,
            env=_SANITIZED_ENV,
        )

    # ── successful invocations ────────────────────────────────────────

    def test_validate_output_parity(self):
        direct = self._run_direct("validate")
        interpreter = self._run_interpreter("validate")
        self.assertEqual(direct.stdout, interpreter.stdout)
        self.assertEqual(direct.stderr, interpreter.stderr)
        self.assertEqual(direct.returncode, interpreter.returncode)

    def test_validate_json_output_parity(self):
        direct = self._run_direct("validate", "--json")
        interpreter = self._run_interpreter("validate", "--json")
        self.assertEqual(direct.stdout, interpreter.stdout)
        self.assertEqual(direct.returncode, interpreter.returncode)

    def test_env_output_parity(self):
        direct = self._run_direct("env")
        interpreter = self._run_interpreter("env")
        self.assertEqual(direct.stdout, interpreter.stdout)
        self.assertEqual(direct.stderr, interpreter.stderr)
        self.assertEqual(direct.returncode, interpreter.returncode)

    def test_env_json_output_parity(self):
        direct = self._run_direct("env", "--json")
        interpreter = self._run_interpreter("env", "--json")
        self.assertEqual(direct.stdout, interpreter.stdout)
        self.assertEqual(direct.returncode, interpreter.returncode)

    def test_get_scalar_output_parity(self):
        direct = self._run_direct("get", "build.stages.toolchain.python.version")
        interpreter = self._run_interpreter("get", "build.stages.toolchain.python.version")
        self.assertEqual(direct.stdout, interpreter.stdout)
        self.assertEqual(direct.returncode, interpreter.returncode)

    def test_get_json_output_parity(self):
        direct = self._run_direct("get", "build.stages.toolchain.python.version", "--json")
        interpreter = self._run_interpreter("get", "build.stages.toolchain.python.version", "--json")
        self.assertEqual(direct.stdout, interpreter.stdout)
        self.assertEqual(direct.returncode, interpreter.returncode)

    def test_compose_help_output_parity(self):
        direct = self._run_direct("compose", "--help")
        interpreter = self._run_interpreter("compose", "--help")
        self.assertEqual(direct.stdout, interpreter.stdout)
        self.assertEqual(direct.returncode, interpreter.returncode)

    def test_check_updates_help_output_parity(self):
        direct = self._run_direct("check-updates", "--help")
        interpreter = self._run_interpreter("check-updates", "--help")
        self.assertEqual(direct.stdout, interpreter.stdout)
        self.assertEqual(direct.returncode, interpreter.returncode)

    # ── error paths ───────────────────────────────────────────────────

    def test_invalid_inventory_exit_code_parity(self):
        invalid_path = _FIXTURES / "missing-source.toml"
        direct = self._run_direct("validate", "--inventory", str(invalid_path))
        interpreter = self._run_interpreter("validate", "--inventory", str(invalid_path))
        self.assertEqual(direct.returncode, interpreter.returncode)
        self.assertEqual(direct.stderr, interpreter.stderr)

    def test_nonexistent_inventory_exit_code_parity(self):
        direct = self._run_direct("validate", "--inventory", "/nonexistent/path.toml")
        interpreter = self._run_interpreter("validate", "--inventory", "/nonexistent/path.toml")
        self.assertEqual(direct.returncode, interpreter.returncode)

    def test_unknown_path_exit_code_parity(self):
        direct = self._run_direct("get", "build.stages.toolchain.pythno.version")
        interpreter = self._run_interpreter("get", "build.stages.toolchain.pythno.version")
        self.assertEqual(direct.returncode, interpreter.returncode)
        self.assertEqual(direct.stderr, interpreter.stderr)

    def test_override_malformed_exit_code_parity(self):
        direct = self._run_direct(
            "get", "build.stages.toolchain.python.version",
            "--override", "build.stages.toolchain.python.version =3.14.7",
        )
        interpreter = self._run_interpreter(
            "get", "build.stages.toolchain.python.version",
            "--override", "build.stages.toolchain.python.version =3.14.7",
        )
        self.assertEqual(direct.returncode, interpreter.returncode)
        self.assertIn("spaces", direct.stderr.lower())

    def test_unknown_only_filter_exit_code_parity(self):
        direct = self._run_direct("check-updates", "--only", "nonexistent-xyz")
        interpreter = self._run_interpreter("check-updates", "--only", "nonexistent-xyz")
        self.assertEqual(direct.returncode, interpreter.returncode)
        self.assertEqual(direct.stderr, interpreter.stderr)


class TestCliCheckUpdates(unittest.TestCase):
    """CLI argument-parsing smoke tests.  Full pipeline coverage is in
    ``test_version_check_updates.py`` with injected offline transports."""

    def test_check_updates_help(self):
        proc = _run("check-updates", "--help")
        self.assertEqual(proc.returncode, 0)
        self.assertIn("check-updates", proc.stdout)

    def test_check_updates_invalid_inventory(self):
        proc = _run("check-updates", "--inventory", "/nonexistent.toml")
        self.assertEqual(proc.returncode, 3)

    def test_check_updates_unknown_only_filter(self):
        """Unknown --only filters must produce exit 2 (usage error)
        with the filter name and known paths/providers listed."""
        proc = _run("check-updates", "--only", "nonexistent-xyz")
        self.assertEqual(proc.returncode, 2)
        self.assertIn("nonexistent-xyz", proc.stderr)
        self.assertIn("Known paths", proc.stderr)


# ---------------------------------------------------------------------------
# Inventory discovery — no fallback to legacy versions.toml
# ---------------------------------------------------------------------------

class TestInventoryDiscovery(unittest.TestCase):
    """Default discovery rejects legacy ``versions.toml`` when
    ``docker-constructor.toml`` is absent, but explicit ``--inventory``
    accepts any filename.

    Unit-level tests — the default inventory path is resolved relative
    to ``docker/versioning/cli.py``, not the current working directory.
    """

    def test_resolve_default_returns_docker_constructor_not_versions(self):
        """``_resolve_default_inventory()`` must return
        ``docker-constructor.toml``, never ``versions.toml``."""
        from docker.versioning.cli import _resolve_default_inventory
        default = _resolve_default_inventory()
        self.assertEqual(default.name, "docker-constructor.toml")
        self.assertNotIn("versions.toml", str(default))

    def test_default_discovery_finds_docker_constructor(self):
        """The resolved default path must point to an existing file."""
        from docker.versioning.cli import _resolve_default_inventory
        from docker.versioning.inventory import load_inventory
        default = _resolve_default_inventory()
        self.assertTrue(default.is_file(),
                        f"docker-constructor.toml not found at {default}")
        # Must load without error
        load_inventory(default)

    def test_default_path_is_absolute_and_not_cwd_dependent(self):
        """The default inventory path is resolved from the module
        location (inside docker/) upwards, never from os.getcwd().
        Changing CWD must not change the resolved path."""
        import os as _os
        from docker.versioning.cli import _resolve_default_inventory
        original_cwd = _os.getcwd()
        default_before = _resolve_default_inventory()
        try:
            _os.chdir("/tmp")
            default_after = _resolve_default_inventory()
        finally:
            _os.chdir(original_cwd)
        self.assertEqual(default_before, default_after,
                         "resolved path must not depend on cwd")

    def test_load_inventory_fails_when_file_missing(self):
        """``load_inventory`` must raise ``FileNotFoundError`` when the
        resolved default path does not exist — no fallback to
        ``versions.toml`` or any other filename."""
        from docker.versioning.inventory import load_inventory
        from tests.versioning.support.inventory_builder import minimal_toml
        with self.assertRaises(FileNotFoundError):
            load_inventory(Path("/nonexistent/docker-constructor.toml"))
        # Explicitly: even when a file named versions.toml exists in
        # the same directory, it must NOT be used as fallback.
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            (Path(td) / "versions.toml").write_text(
                minimal_toml(), encoding="utf-8",
            )
            nonexistent = Path(td) / "docker-constructor.toml"
            with self.assertRaises(FileNotFoundError):
                load_inventory(nonexistent)

    def test_explicit_inventory_accepts_legacy_name(self):
        """``load_inventory`` with explicit ``versions.toml`` path works."""
        import tempfile
        from docker.versioning.inventory import load_inventory
        from tests.versioning.support.inventory_builder import minimal_toml
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "versions.toml"
            p.write_text(minimal_toml(), encoding="utf-8")
            inv = load_inventory(p)
            self.assertEqual(inv.schema, 1)

    def test_explicit_inventory_accepts_arbitrary_name(self):
        """``load_inventory`` with arbitrary filename works."""
        import tempfile
        from docker.versioning.inventory import load_inventory
        from tests.versioning.support.inventory_builder import minimal_toml
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "arbitrary.toml"
            p.write_text(minimal_toml(), encoding="utf-8")
            inv = load_inventory(p)
            self.assertEqual(inv.schema, 1)

    def test_cli_rejects_missing_default(self):
        """``validate`` fails when ``docker-constructor.toml`` is
        absent from the default location, proving the CLI does not
        fall back to ``versions.toml``.

        Uses ``--inventory`` pointing to a nonexistent path to avoid
        mutating the real repository."""
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            nonexistent = Path(td) / "docker-constructor.toml"
            proc = _run("validate", "--inventory", str(nonexistent))
            self.assertNotEqual(proc.returncode, 0,
                                "must not silently succeed without inventory")
            self.assertIn("inventory not found", proc.stderr.lower())

    def test_cli_rejects_missing_default_no_fallback_to_versions(self):
        """When ``--inventory`` points to a nonexistent
        ``docker-constructor.toml``, the CLI must NOT silently fall
        back to a ``versions.toml`` that exists alongside it."""
        import tempfile
        from tests.versioning.support.inventory_builder import minimal_toml
        with tempfile.TemporaryDirectory() as td:
            # Create versions.toml (should be ignored)
            (Path(td) / "versions.toml").write_text(
                minimal_toml(), encoding="utf-8")
            # Point to nonexistent docker-constructor.toml
            nonexistent = Path(td) / "docker-constructor.toml"
            proc = _run("validate", "--inventory", str(nonexistent))
            self.assertNotEqual(proc.returncode, 0,
                                "must not fall back to versions.toml")
            self.assertIn("inventory not found", proc.stderr.lower())


# ---------------------------------------------------------------------------
# Integrated repository-fixture test — Task 4.1
# ---------------------------------------------------------------------------

class TestIntegratedRepoFixture(unittest.TestCase):
    """End-to-end exercise of validate, env rendering, effective output
    generation, and update checks in a repository fixture containing
    only ``docker-constructor.toml``.

    Uses library functions directly because the CLI resolves the repo
    root from the module path (not CWD), so subprocess tests from a
    temp directory always hit the real repo root.
    """

    @classmethod
    def setUpClass(cls):
        import tempfile
        from tests.versioning.support.inventory_builder import minimal_toml
        cls.tmpdir = Path(tempfile.mkdtemp())
        cls.inventory_path = cls.tmpdir / "docker-constructor.toml"
        cls.inventory_path.write_text(
            _PYTHON_OVERRIDE_TOML_FOR_INTEGRATION(),
            encoding="utf-8",
        )

        from docker.versioning.inventory import load_inventory
        cls.inventory = load_inventory(cls.inventory_path)

    @classmethod
    def tearDownClass(cls):
        import shutil
        shutil.rmtree(cls.tmpdir, ignore_errors=True)

    # -- Validate ----------------------------------------------------------

    def test_validate_succeeds(self):
        """``validate_inventory`` must not raise for a valid inventory."""
        import tomllib
        from docker.versioning.inventory import validate_inventory
        with open(self.inventory_path, "rb") as f:
            raw = tomllib.load(f)
        validate_inventory(raw)  # must not raise

    def test_validate_json_output(self):
        """The validate command must produce parseable JSON."""
        inventory_arg = str(self.inventory_path)
        proc = _run("validate", "--inventory", inventory_arg, "--json")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        data = json.loads(proc.stdout)
        self.assertTrue(data.get("valid"))

    # -- Env rendering -----------------------------------------------------

    def test_env_renders_without_error(self):
        """``render_build_environment`` must produce expected keys."""
        from docker.versioning.effective import apply_overrides
        from docker.versioning.rendering import render_build_environment
        eff = apply_overrides(self.inventory, {})
        env = render_build_environment(eff)
        self.assertIsInstance(env, dict)
        self.assertIn("PYTHON_VERSION", env)
        self.assertIn("EFFECTIVE_VERSIONS_FILE", env)

    def test_env_default_output_path_is_docker_constructor_toml(self):
        """Default generated inventory output must be
        ``.docker-generated/docker-constructor.toml``."""
        from docker.versioning.effective import apply_overrides
        from docker.versioning.rendering import render_build_environment
        eff = apply_overrides(self.inventory, {})
        env = render_build_environment(eff)
        self.assertEqual(
            env["EFFECTIVE_VERSIONS_FILE"],
            ".docker-generated/docker-constructor.toml",
        )

    # -- Effective output generation ---------------------------------------

    def test_effective_inventory_is_written_and_loadable(self):
        """``write_effective_inventory`` writes a file that survives a
        full ``load_inventory`` round-trip."""
        from docker.versioning.effective import apply_overrides
        from docker.versioning.inventory import load_inventory
        from docker.versioning.rendering import write_effective_inventory

        eff = apply_overrides(self.inventory, {})
        dest = self.tmpdir / "generated.toml"

        write_effective_inventory(eff, dest)
        self.assertTrue(dest.is_file())

        import tomllib
        with open(dest, "rb") as f:
            raw = tomllib.load(f)
        self.assertIn("schema", raw)
        self.assertEqual(raw["schema"], 1)

        reloaded = load_inventory(dest)
        self.assertEqual(
            reloaded.stages.toolchain.python.version,
            self.inventory.stages.toolchain.python.version,
        )

    def test_effective_inventory_reflects_overrides(self):
        """Overridden values appear in the generated effective inventory."""
        from docker.versioning.effective import apply_overrides
        from docker.versioning.rendering import write_effective_inventory

        eff = apply_overrides(self.inventory, {
            "build.stages.toolchain.python.version": "3.99.0",
        })
        dest = self.tmpdir / "overridden.toml"
        write_effective_inventory(eff, dest)

        import tomllib
        with open(dest, "rb") as f:
            raw = tomllib.load(f)
        self.assertEqual(
            raw["build"]["stages"]["toolchain"]["python"]["version"],
            "3.99.0",
        )

    def test_effective_inventory_rejects_authoritative_name(self):
        """``write_effective_inventory`` with repo_root must reject the
        authoritative inventory path as output to prevent overwrite."""
        from docker.versioning.effective import apply_overrides
        from docker.versioning.rendering import (
            EffectiveInventoryOutputError,
            write_effective_inventory,
        )

        eff = apply_overrides(self.inventory, {})
        with self.assertRaises(EffectiveInventoryOutputError):
            write_effective_inventory(
                eff,
                self.inventory_path,
                repo_root=self.tmpdir,
                output_path="docker-constructor.toml",
            )

    def test_override_constraint_survives_round_trip(self):
        """Override policy constraints must round-trip as proper
        ``Constraint`` objects, not raw dicts or strings.

        This guards against a serialization defect where
        ``write_effective_inventory`` emits override constraints in a
        format that ``load_inventory`` cannot reconstruct as
        ``OverridePolicy``."""
        from docker.versioning.effective import apply_overrides
        from docker.versioning.inventory import load_inventory
        from docker.versioning.rendering import write_effective_inventory
        from docker.versioning.constraints import Constraint

        eff = apply_overrides(self.inventory, {
            "build.stages.toolchain.python.version": "3.15.0",
        })
        dest = self.tmpdir / "roundtrip.toml"
        write_effective_inventory(eff, dest)

        reloaded = load_inventory(dest)
        py = reloaded.stages.toolchain.python

        # Version must reflect the override
        self.assertEqual(py.version, "3.15.0")

        # Override policy must exist and have the correct types
        self.assertIsNotNone(py.override)
        self.assertIsInstance(py.override.constraint, Constraint,
                              "constraint must be a Constraint, not a dict")
        self.assertEqual(str(py.override.constraint), ">=3.14.6")
        self.assertFalse(py.override.allow_prerelease)
        self.assertEqual(py.override.scheme, "numeric")

        # The constraint must actually validate the version
        self.assertTrue(py.override.constraint.matches(
            __import__("docker.versioning.constraints", fromlist=["parse_numeric_version"])
            .parse_numeric_version("3.15.0")
        ))

    # -- Update checks -----------------------------------------------------

    def test_check_updates_with_injected_transport(self):
        """``check_updates`` must accept injected transports and return
        results without network."""
        import json as _json
        from docker.versioning.providers.base import ProviderContext
        from docker.versioning.updates import (
            _DEFAULT_PROVIDERS,
            check_updates,
        )

        class _NoNetwork:
            def request(self, method, url, *, headers=()):
                return type("HttpResponse", (), {
                    "status": 503,
                    "headers": {},
                    "body": b"test: no network",
                })()

        class _NoGit:
            def resolve_ref(self, repository, ref):
                raise RuntimeError("test: no git")

        ctx = ProviderContext(
            http=_NoNetwork(),
            git=_NoGit(),
            include_prerelease=False,
            tokens={},
        )
        results = check_updates(
            self.inventory,
            providers=_DEFAULT_PROVIDERS,
            context=ctx,
        )
        self.assertIsInstance(results, tuple)
        # Every result should indicate a provider error or a skipped
        # path — none should crash.
        for r in results:
            self.assertIsInstance(r, object)

    # -- Helpers (none needed — library functions tested directly) ----------


# -- Module-level helpers --------------------------------------------------


def _PYTHON_OVERRIDE_TOML_FOR_INTEGRATION() -> str:
    """Return minimal TOML with Python override policy declared.

    Duplicated from test_version_rendering.py to avoid cross-test
    import coupling for the integrated repo-fixture test.
    """
    from tests.versioning.support.inventory_builder import minimal_toml
    return minimal_toml(
        **{
            "build.stages.toolchain.python": (
                'version = "3.14.6"\n'
                "\n"
                "[build.stages.toolchain.python.override]\n"
                'constraint = ">=3.14.6"\n'
                "allow_prerelease = false\n"
                'scheme = "numeric"'
            ),
        }
    )


if __name__ == "__main__":
    unittest.main()
