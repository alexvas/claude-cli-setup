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
        result = _run("get", "stages.base.node.tag")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("trixie", result.stdout)

    def test_scalar_python_version(self):
        result = _run("get", "stages.toolchain.python.version")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), "3.14.6")

    def test_scalar_python_source_type(self):
        result = _run("get", "stages.toolchain.python.source.type")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), "uv-python")

    def test_scalar_override_constraint(self):
        result = _run("get", "stages.toolchain.python.override.constraint")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(">=3.14.6", result.stdout)

    def test_scalar_extension_version(self):
        result = _run("get", "runtime.pi-extensions.pi-read.version")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), "0.2.0")

    def test_container_path_json(self):
        result = _run("get", "stages.toolchain.python", "--json")
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
        self.assertIn("stages", data)

    def test_json_deterministic_ordering(self):
        result1 = _run("get", "stages.toolchain", "--json")
        result2 = _run("get", "stages.toolchain", "--json")
        self.assertEqual(result1.stdout, result2.stdout)

    def test_tuple_becomes_json_array(self):
        result = _run("get", "stages.toolchain.rust.components", "--json")
        data = json.loads(result.stdout)
        self.assertIsInstance(data, list)
        self.assertIn("rustfmt", data)

    # Negatives

    def test_unknown_path_exits_four(self):
        result = _run("get", "stages.toolchain.pythno.version")
        self.assertEqual(result.returncode, 4, result.stderr)
        self.assertIn("pythno", result.stderr)

    def test_missing_field_exits_four(self):
        result = _run("get", "stages.toolchain.python.missing")
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
    })

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


# ---------------------------------------------------------------------------
# 2.4 Override
# ---------------------------------------------------------------------------

class TestCliOverride(unittest.TestCase):
    def test_override_get_python(self):
        result = _run(
            "get", "stages.toolchain.python.version",
            "--override", "stages.toolchain.python.version=3.14.7",
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), "3.14.7")

    def test_override_env_python(self):
        result = _run(
            "env", "--json",
            "--override", "stages.toolchain.python.version=3.14.7",
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        data = json.loads(result.stdout)
        self.assertEqual(data["PYTHON_VERSION"], "3.14.7")

    def test_override_effective_inventory(self):
        result = _run(
            "get", "stages.toolchain.python.version", "--json",
            "--override", "stages.toolchain.python.version=3.14.7",
        )
        data = json.loads(result.stdout)
        self.assertEqual(data, "3.14.7")

    def test_source_inventory_unchanged(self):
        """Default inventory still returns 3.14.6 even after override."""
        result = _run("get", "stages.toolchain.python.version")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), "3.14.6")

    # Negatives

    def test_override_rejects_short_version(self):
        result = _run(
            "get", "stages.toolchain.python.version",
            "--override", "stages.toolchain.python.version=3.14",
        )
        self.assertEqual(result.returncode, 6, result.stderr)
        self.assertIn("not a valid", result.stderr.lower())

    def test_override_rejects_v_prefix(self):
        result = _run(
            "get", "stages.toolchain.python.version",
            "--override", "stages.toolchain.python.version=v3.14.7",
        )
        self.assertEqual(result.returncode, 6, result.stderr)

    def test_override_rejects_prerelease(self):
        result = _run(
            "get", "stages.toolchain.python.version",
            "--override", "stages.toolchain.python.version=3.14.7-beta.1",
        )
        self.assertEqual(result.returncode, 6, result.stderr)

    def test_override_rejects_old_version(self):
        result = _run(
            "get", "stages.toolchain.python.version",
            "--override", "stages.toolchain.python.version=3.14.5",
        )
        self.assertEqual(result.returncode, 6, result.stderr)
        self.assertIn("does not satisfy", result.stderr)

    def test_override_rejects_latest(self):
        result = _run(
            "get", "stages.toolchain.python.version",
            "--override", "stages.toolchain.python.version=latest",
        )
        self.assertEqual(result.returncode, 6, result.stderr)

    def test_override_unsupported_path_exits_five(self):
        result = _run(
            "get", "stages.toolchain.python.version",
            "--override", "stages.toolchain.ty.version=0.0.62",
        )
        self.assertEqual(result.returncode, 5, result.stderr)

    def test_override_unknown_path_exits_five(self):
        result = _run(
            "get", "stages.toolchain.python.version",
            "--override", "unknown.path=1.0.0",
        )
        self.assertEqual(result.returncode, 5, result.stderr)

    def test_override_malformed_spaces_exits_two(self):
        result = _run(
            "get", "stages.toolchain.python.version",
            "--override", "stages.toolchain.python.version =3.14.7",
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


if __name__ == "__main__":
    unittest.main()
