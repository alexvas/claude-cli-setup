"""Host-side unit tests for docker/verify_versioned_image.py.

All tests mock ``subprocess.run`` — no Docker daemon required.
"""
from __future__ import annotations

import json
import os
import subprocess
import tempfile
import unittest
from unittest import mock

from docker.verify_versioned_image import main as verify_main, _image_inv_snippet, _READ_PACKAGE_JSON


# ---------------------------------------------------------------------------
# Static TOML fixture — mirrors production inventory schema with
# source.package (not entry-level package) for extensions.
# ---------------------------------------------------------------------------

_FIXTURE_TOML = r"""schema = 1

[stages]

[stages.base]
[stages.base.node]
tag = "24-trixie-slim"
digest = "sha256:ae91dcc111a68c9d2d81ff2a17bda61be126426176fde6fe7d08ab13b7f50573"

[stages.toolchain]

[stages.toolchain.rust]
version = "1.88.0"
profile = "minimal"
components = ["rustfmt", "clippy"]

[stages.toolchain.rust.rustup]
[stages.toolchain.rust.rustup.source]
type = "static-url"
checksum_url = "https://example.com/rustup-init.sha256"

[stages.toolchain.rust.rustup.update]
provider = "static-url"
stable_only = true

[stages.toolchain.rust.rustup.artifacts.linux-amd64]
url = "https://example.com/rustup-init"
sha256 = "4acc9acc76d5079515b46346a485974457b5a79893cfb01112423c89aeb5aa10"

[stages.toolchain.uv]
version = "0.11.29"

[stages.toolchain.uv.artifacts.linux-amd64]
url = "https://example.com/uv.tar.gz"
sha256 = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"

[stages.toolchain.python]
version = "3.14.6"

[stages.toolchain.ty]
version = "0.0.61"

[stages.pi-tools.pi]
version = "0.80.10"

[stages.openspec-tools.openspec]
version = "1.6.0"

[stages.rtk-prebuilt.rtk]
version = "v0.43.0"

[stages.rtk-prebuilt.rtk.artifacts.linux-amd64]
url = "https://example.com/rtk_amd64.deb"
sha256 = "eb571d784b3269521722ebe2f0dc2409e89da6bd70bf097ddb21e9d4b3b240b9"

[stages.fd-prebuilt.fd]
version = "v10.4.2"

[stages.fd-prebuilt.fd.artifacts.linux-amd64]
url = "https://example.com/fd_amd64.deb"
sha256 = "0e44eb5fca93f09bc6f5430b90acdf44c8e069d0a903700aeb4820629337b67b"

[stages.runtime.oh-my-zsh]
revision = "70ad5e3df8f7bed68aa6672029496926e632aedd"

[runtime]
[runtime.pi-extensions.pi-read]
version = "0.2.0"

[runtime.pi-extensions.pi-read.source]
type = "npm"
package = "@arcanemachine/pi-read"

[runtime.pi-extensions.pi-read.update]
provider = "npm"
stable_only = true

[runtime.pi-extensions.pi-codex-usage]
version = "0.3.1"

[runtime.pi-extensions.pi-codex-usage.source]
type = "npm"
package = "@llblab/pi-codex-usage"

[runtime.pi-extensions.pi-codex-usage.update]
provider = "npm"
stable_only = true

[runtime.pi-extensions.pi-proxy]
version = "0.5.0"

[runtime.pi-extensions.pi-proxy.source]
type = "npm"
package = "pi-proxy"

[runtime.pi-extensions.pi-proxy.update]
provider = "npm"
stable_only = true
"""


def _write_fixture(td: str) -> str:
    p = os.path.join(td, "versions.toml")
    with open(p, "w") as f:
        f.write(_FIXTURE_TOML)
    return p


def _fixture_dict() -> dict:
    import tomllib
    return tomllib.loads(_FIXTURE_TOML)


# ---------------------------------------------------------------------------
# Mock subprocess.run side-effect factory
# ---------------------------------------------------------------------------

def _make_run_side_effect(inv: dict):
    """Build a side_effect function for mocked subprocess.run.

    *inv* is the expected effective inventory dict (host-side).
    Responds to Docker commands with matching tool output so the verifier
    sees consistent state and exits 0.
    """

    versions = {
        "rustc": "rustc 1.88.0 (abc123 2025)",
        "cargo": "cargo 1.88.0 (def456 2025)",
        "rustfmt": "rustfmt 1.7.1-stable (abc123 2025)",
        "cargo clippy": "clippy 0.1.88 (abc123 2025)",
        "uv": "uv 0.11.29",
        "ty": "ty 0.0.61",
        "pi": "pi v0.80.10",
        "openspec": "openspec v1.6.0",
        "rtk": "rtk v0.43.0",
        "fd": "fd v10.4.2",
        "node": "v24.11.0",
    }

    py3_real = "/home/dev/.local/share/uv/python/cpython-3.14.6-linux-x86_64-gnu/bin/python3"

    # Extension package.json responses
    _ext_pkgs = {
        "@arcanemachine/pi-read": {"name": "@arcanemachine/pi-read", "version": "0.2.0"},
        "@llblab/pi-codex-usage": {"name": "@llblab/pi-codex-usage", "version": "0.3.1"},
        "pi-proxy": {"name": "pi-proxy", "version": "0.5.0"},
    }

    def _side_effect(cmd_args, **kwargs):
        cmd_str = " ".join(cmd_args)
        # Normalized: drop the always-present CHOWN_WORK_ON_START from
        # exact-terminal-string checks so tests are robust.
        cmd_normalised = cmd_str.replace(" -e CHOWN_WORK_ON_START=0", "")

        # --- Image inventory read (JSON dump) ---
        if "tomllib.load" in cmd_str and "json.dumps" in cmd_str:
            json_data = json.dumps(inv, sort_keys=True)
            return subprocess.CompletedProcess(cmd_args, 0, stdout=json_data, stderr="")

        # --- Extension package.json read ---
        if "package.json" in cmd_str and "json.load" in cmd_str:
            # The last arg is the pkg directory path
            pkg_dir = cmd_args[-1]
            for pkg_name, pkg_data in _ext_pkgs.items():
                if pkg_dir.endswith("/" + pkg_name):
                    return subprocess.CompletedProcess(
                        cmd_args, 0,
                        stdout=json.dumps(pkg_data) + "\n", stderr="",
                    )
            return subprocess.CompletedProcess(
                cmd_args, 1, stdout="", stderr="not found",
            )

        # --- stat ---
        if "stat -c" in cmd_str:
            path = cmd_args[cmd_args.index("-c") + 2]
            if "versions.toml" in path:
                return subprocess.CompletedProcess(cmd_args, 0, stdout="root:root 444\n", stderr="")
            if "versions.py" in path:
                return subprocess.CompletedProcess(cmd_args, 0, stdout="root:root\n", stderr="")
            return subprocess.CompletedProcess(cmd_args, 0, stdout="dev:dev 755\n", stderr="")

        # --- writability checks ---
        if "test -w /usr/local/share/pi-cli/versions.toml" in cmd_str:
            return subprocess.CompletedProcess(cmd_args, 0, stdout="OK\n", stderr="")
        if "test -w /usr/local/lib/pi-cli/docker/versions.py" in cmd_str:
            return subprocess.CompletedProcess(cmd_args, 0, stdout="OK\n", stderr="")

        # --- Tool --version ---
        if " --version" in cmd_str:
            # cargo clippy must be checked before cargo (cargo --version is a
            # substring of cargo clippy --version and would match first).
            if "cargo clippy --version" in cmd_str:
                return subprocess.CompletedProcess(
                    cmd_args, 0,
                    stdout=versions.get("cargo clippy", "clippy 0.1.88") + "\n",
                    stderr="",
                )
            for tool, output in versions.items():
                if f"{tool} --version" in cmd_str:
                    return subprocess.CompletedProcess(cmd_args, 0, stdout=output + "\n", stderr="")
            return subprocess.CompletedProcess(cmd_args, 0, stdout="tool 1.0.0\n", stderr="")

        # --- command -v python3 ---
        if "command -v python3" in cmd_normalised and "bash -c" in cmd_normalised:
            return subprocess.CompletedProcess(cmd_args, 0, stdout="/usr/bin/python3\n", stderr="")
        if "command -v python" in cmd_normalised and "python3" not in cmd_str:
            return subprocess.CompletedProcess(cmd_args, 0, stdout="/usr/bin/python3\n", stderr="")

        # --- command -v pip / pip3 ---
        if "command -v pip3" in cmd_str:
            return subprocess.CompletedProcess(cmd_args, 1, stdout="", stderr="")
        if "command -v pip" in cmd_str:
            return subprocess.CompletedProcess(cmd_args, 1, stdout="", stderr="")

        # --- readlink -f ---
        if "readlink -f" in cmd_str:
            return subprocess.CompletedProcess(cmd_args, 0, stdout=py3_real + "\n", stderr="")

        # --- rustup component list ---
        if "rustup" in cmd_str and "component" in cmd_str and "list" in cmd_str:
            # --installed output: component names only, no (installed) marker
            installed = (
                "rustc-x86_64-unknown-linux-gnu\n"
                "cargo-x86_64-unknown-linux-gnu\n"
                "rustfmt-x86_64-unknown-linux-gnu\n"
                "clippy-x86_64-unknown-linux-gnu\n"
            )
            return subprocess.CompletedProcess(cmd_args, 0, stdout=installed, stderr="")

        # --- Python version check (sys.version_info) ---
        if "sys.version_info" in cmd_str:
            return subprocess.CompletedProcess(cmd_args, 0, stdout="3.14.6\n", stderr="")

        return subprocess.CompletedProcess(cmd_args, 0, stdout="mock output\n", stderr="")

    return _side_effect


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestImageInvSnippet(unittest.TestCase):
    """Validate the Python snippet injected via docker run -c."""

    def test_snippet_is_valid_python(self):
        compile(_image_inv_snippet(), "<snippet>", "exec")

    def test_snippet_has_no_compound_statements_after_semicolons(self):
        snippet = _image_inv_snippet()
        for frag in snippet.split(";"):
            stripped = frag.strip()
            if stripped.startswith(("with ", "if ", "for ", "while ", "def ", "class ", "try:")):
                self.fail(f"compound statement after semicolon: {frag!r}")


class TestExtensionPackageJsonSnippet(unittest.TestCase):
    """Validate the snippet that reads package.json inside the container."""

    def test_snippet_is_valid_python(self):
        compile(_READ_PACKAGE_JSON, "<pkg-snippet>", "exec")


class TestVerifyVersionedImage(unittest.TestCase):
    """Unit tests for verify_versioned_image.py — all subprocess.run mocked."""

    @mock.patch("subprocess.run")
    def test_correct_inventory_identity(self, mock_run):
        with tempfile.TemporaryDirectory() as td:
            inv_path = _write_fixture(td)
            inv = _fixture_dict()
            mock_run.side_effect = _make_run_side_effect(inv)
            rc = verify_main(["--image", "img", "--inventory", inv_path])
            self.assertEqual(rc, 0)

    @mock.patch("subprocess.run")
    def test_inventory_version_mismatch(self, mock_run):
        """Rust version differs in image inventory → non-zero exit."""
        with tempfile.TemporaryDirectory() as td:
            inv_path = _write_fixture(td)
            image_inv = _fixture_dict()
            image_inv["stages"]["toolchain"]["rust"]["version"] = "1.99.0"

            def _side(cmd_args, **kwargs):
                cmd_str = " ".join(cmd_args)
                if "tomllib.load" in cmd_str and "json.dumps" in cmd_str:
                    return subprocess.CompletedProcess(
                        cmd_args, 0,
                        stdout=json.dumps(image_inv, sort_keys=True), stderr="",
                    )
                return _make_run_side_effect(_fixture_dict())(cmd_args, **kwargs)

            mock_run.side_effect = _side
            rc = verify_main(["--image", "img", "--inventory", inv_path])
            self.assertNotEqual(rc, 0)

    @mock.patch("subprocess.run")
    def test_inventory_artifact_digest_mismatch(self, mock_run):
        """Image rustup SHA-256 differs from host inventory → non-zero exit.

        This proves the verifier detects when the embedded image inventory
        records a different artifact digest than the host inventory — a
        necessary precondition for catching corrupted-version builds.
        """
        with tempfile.TemporaryDirectory() as td:
            inv_path = _write_fixture(td)
            image_inv = _fixture_dict()
            image_inv["stages"]["toolchain"]["rust"]["rustup"]["artifacts"]["linux-amd64"]["sha256"] = (
                "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
            )

            def _side(cmd_args, **kwargs):
                cmd_str = " ".join(cmd_args)
                if "tomllib.load" in cmd_str and "json.dumps" in cmd_str:
                    return subprocess.CompletedProcess(
                        cmd_args, 0,
                        stdout=json.dumps(image_inv, sort_keys=True), stderr="",
                    )
                return _make_run_side_effect(_fixture_dict())(cmd_args, **kwargs)

            mock_run.side_effect = _side
            rc = verify_main(["--image", "img", "--inventory", inv_path])
            self.assertNotEqual(rc, 0)

    @mock.patch("subprocess.run")
    def test_python_version_mismatch(self, mock_run):
        with tempfile.TemporaryDirectory() as td:
            inv_path = _write_fixture(td)

            def _side(cmd_args, **kwargs):
                cmd_str = " ".join(cmd_args)
                if "sys.version_info" in cmd_str:
                    return subprocess.CompletedProcess(cmd_args, 0, stdout="3.14.7\n", stderr="")
                return _make_run_side_effect(_fixture_dict())(cmd_args, **kwargs)

            mock_run.side_effect = _side
            rc = verify_main(["--image", "img", "--inventory", inv_path])
            self.assertNotEqual(rc, 0)

    @mock.patch("subprocess.run")
    def test_python_path_not_in_uv_dir(self, mock_run):
        with tempfile.TemporaryDirectory() as td:
            inv_path = _write_fixture(td)

            def _side(cmd_args, **kwargs):
                cmd_str = " ".join(cmd_args)
                if "command -v python3" in cmd_str and "bash -c" in cmd_str:
                    return subprocess.CompletedProcess(cmd_args, 0, stdout="/usr/local/bin/python3\n", stderr="")
                if "readlink -f" in cmd_str:
                    return subprocess.CompletedProcess(cmd_args, 0, stdout="/usr/local/bin/python3\n", stderr="")
                return _make_run_side_effect(_fixture_dict())(cmd_args, **kwargs)

            mock_run.side_effect = _side
            rc = verify_main(["--image", "img", "--inventory", inv_path])
            self.assertNotEqual(rc, 0)

    @mock.patch("subprocess.run")
    def test_pip_present_is_rejected(self, mock_run):
        with tempfile.TemporaryDirectory() as td:
            inv_path = _write_fixture(td)

            def _side(cmd_args, **kwargs):
                cmd_str = " ".join(cmd_args)
                if "command -v pip3" in cmd_str:
                    return subprocess.CompletedProcess(cmd_args, 0, stdout="/usr/bin/pip3\n", stderr="")
                if "command -v pip" in cmd_str:
                    return subprocess.CompletedProcess(cmd_args, 0, stdout="/usr/bin/pip\n", stderr="")
                return _make_run_side_effect(_fixture_dict())(cmd_args, **kwargs)

            mock_run.side_effect = _side
            rc = verify_main(["--image", "img", "--inventory", inv_path])
            self.assertNotEqual(rc, 0)

    @mock.patch("subprocess.run")
    def test_ownership_wrong(self, mock_run):
        with tempfile.TemporaryDirectory() as td:
            inv_path = _write_fixture(td)

            def _side(cmd_args, **kwargs):
                cmd_str = " ".join(cmd_args)
                if "stat -c" in cmd_str and "versions.toml" in cmd_str:
                    return subprocess.CompletedProcess(cmd_args, 0, stdout="dev:dev 644\n", stderr="")
                return _make_run_side_effect(_fixture_dict())(cmd_args, **kwargs)

            mock_run.side_effect = _side
            rc = verify_main(["--image", "img", "--inventory", inv_path])
            self.assertNotEqual(rc, 0)

    @mock.patch("subprocess.run")
    def test_docker_run_command_construction(self, mock_run):
        with tempfile.TemporaryDirectory() as td:
            inv_path = _write_fixture(td)
            mock_run.side_effect = _make_run_side_effect(_fixture_dict())
            verify_main(["--image", "my-image", "--inventory", inv_path])
            calls = [" ".join(c[0][0]) for c in mock_run.call_args_list]
            self.assertTrue(any("docker" in c and "run" in c and "--rm" in c and "my-image" in c
                                for c in calls))

    @mock.patch("subprocess.run")
    def test_nonzero_docker_exit_propagated(self, mock_run):
        with tempfile.TemporaryDirectory() as td:
            inv_path = _write_fixture(td)

            def _side(cmd_args, **kwargs):
                cmd_str = " ".join(cmd_args)
                if "rustc --version" in cmd_str:
                    return subprocess.CompletedProcess(cmd_args, 1, stdout="", stderr="rustc: not found")
                return _make_run_side_effect(_fixture_dict())(cmd_args, **kwargs)

            mock_run.side_effect = _side
            rc = verify_main(["--image", "img", "--inventory", inv_path])
            self.assertNotEqual(rc, 0)

    @mock.patch("subprocess.run")
    def test_node_major_mismatch(self, mock_run):
        with tempfile.TemporaryDirectory() as td:
            inv_path = _write_fixture(td)

            def _side(cmd_args, **kwargs):
                cmd_str = " ".join(cmd_args)
                if "node --version" in cmd_str:
                    return subprocess.CompletedProcess(cmd_args, 0, stdout="v22.11.0\n", stderr="")
                return _make_run_side_effect(_fixture_dict())(cmd_args, **kwargs)

            mock_run.side_effect = _side
            rc = verify_main(["--image", "img", "--inventory", inv_path])
            self.assertNotEqual(rc, 0)

    @mock.patch("subprocess.run")
    def test_v_prefix_normalisation(self, mock_run):
        with tempfile.TemporaryDirectory() as td:
            inv_path = _write_fixture(td)

            def _side(cmd_args, **kwargs):
                cmd_str = " ".join(cmd_args)
                if "fd --version" in cmd_str:
                    return subprocess.CompletedProcess(cmd_args, 0, stdout="fd 10.4.2\n", stderr="")
                return _make_run_side_effect(_fixture_dict())(cmd_args, **kwargs)

            mock_run.side_effect = _side
            rc = verify_main(["--image", "img", "--inventory", inv_path])
            self.assertEqual(rc, 0)

    @mock.patch("subprocess.run")
    def test_no_fallback_versions(self, mock_run):
        with tempfile.TemporaryDirectory() as td:
            inv_path = _write_fixture(td)

            def _side(cmd_args, **kwargs):
                cmd_str = " ".join(cmd_args)
                if "rustc --version" in cmd_str:
                    return subprocess.CompletedProcess(cmd_args, 0, stdout="rustc dev\n", stderr="")
                return _make_run_side_effect(_fixture_dict())(cmd_args, **kwargs)

            mock_run.side_effect = _side
            rc = verify_main(["--image", "img", "--inventory", inv_path])
            self.assertNotEqual(rc, 0)

    @mock.patch("subprocess.run")
    def test_tool_output_exact_numeric_extraction(self, mock_run):
        with tempfile.TemporaryDirectory() as td:
            inv_path = _write_fixture(td)

            def _side(cmd_args, **kwargs):
                cmd_str = " ".join(cmd_args)
                if "uv --version" in cmd_str:
                    return subprocess.CompletedProcess(cmd_args, 0, stdout="uv 0.11.29 (abcdef)\n", stderr="")
                return _make_run_side_effect(_fixture_dict())(cmd_args, **kwargs)

            mock_run.side_effect = _side
            rc = verify_main(["--image", "img", "--inventory", inv_path])
            self.assertEqual(rc, 0)

    # --- Extension tests using source.package + package.json ---

    @mock.patch("subprocess.run")
    def test_all_extensions_verified_via_package_json(self, mock_run):
        """All three extensions verified by reading node_modules/<source.package>/package.json."""
        with tempfile.TemporaryDirectory() as td:
            inv_path = _write_fixture(td)
            mock_run.side_effect = _make_run_side_effect(_fixture_dict())
            rc = verify_main(["--image", "img", "--inventory", inv_path,
                              "--pi-home", "/opt/pi"])
            self.assertEqual(rc, 0)

            # Verify mount is at /home/dev/.pi
            for call_args in mock_run.call_args_list:
                cmd_parts = call_args[0][0]
                for i, part in enumerate(cmd_parts):
                    if part == "-v" and i + 1 < len(cmd_parts):
                        mount = cmd_parts[i + 1]
                        if "/opt/pi" in mount:
                            self.assertEqual(mount, "/opt/pi:/home/dev/.pi:ro")

    @mock.patch("subprocess.run")
    def test_missing_extension_package_json(self, mock_run):
        """Extension's node_modules directory doesn't exist → non-zero exit."""
        with tempfile.TemporaryDirectory() as td:
            inv_path = _write_fixture(td)
            inv = _fixture_dict()
            # Remove pi-codex-usage and pi-proxy from inventory so they're not expected,
            # then test that one missing is treated correctly.
            # Actually, keep all 3. Override only pi-codex-usage to fail.

            def _side(cmd_args, **kwargs):
                cmd_str = " ".join(cmd_args)
                if "package.json" in cmd_str and "json.load" in cmd_str:
                    pkg_dir = cmd_args[-1]
                    if "pi-codex-usage" in pkg_dir:
                        return subprocess.CompletedProcess(cmd_args, 1, stdout="", stderr="ENOENT")
                    if "pi-read" in pkg_dir:
                        return subprocess.CompletedProcess(
                            cmd_args, 0,
                            stdout='{"name":"@arcanemachine/pi-read","version":"0.2.0"}\n',
                            stderr="",
                        )
                    if "pi-proxy" in pkg_dir:
                        return subprocess.CompletedProcess(
                            cmd_args, 0,
                            stdout='{"name":"pi-proxy","version":"0.5.0"}\n',
                            stderr="",
                        )
                return _make_run_side_effect(inv)(cmd_args, **kwargs)

            mock_run.side_effect = _side
            rc = verify_main(["--image", "img", "--inventory", inv_path,
                              "--pi-home", "/opt/pi"])
            self.assertNotEqual(rc, 0)

    @mock.patch("subprocess.run")
    def test_extension_version_mismatch_from_package_json(self, mock_run):
        """package.json version != inventory version → non-zero exit."""
        with tempfile.TemporaryDirectory() as td:
            inv_path = _write_fixture(td)
            inv = _fixture_dict()

            def _side(cmd_args, **kwargs):
                cmd_str = " ".join(cmd_args)
                if "package.json" in cmd_str and "json.load" in cmd_str:
                    pkg_dir = cmd_args[-1]
                    if "pi-read" in pkg_dir:
                        return subprocess.CompletedProcess(
                            cmd_args, 0,
                            stdout='{"name":"@arcanemachine/pi-read","version":"0.9.9"}\n',
                            stderr="",
                        )
                    if "pi-codex-usage" in pkg_dir:
                        return subprocess.CompletedProcess(
                            cmd_args, 0,
                            stdout='{"name":"@llblab/pi-codex-usage","version":"0.3.1"}\n',
                            stderr="",
                        )
                    if "pi-proxy" in pkg_dir:
                        return subprocess.CompletedProcess(
                            cmd_args, 0,
                            stdout='{"name":"pi-proxy","version":"0.5.0"}\n',
                            stderr="",
                        )
                return _make_run_side_effect(inv)(cmd_args, **kwargs)

            mock_run.side_effect = _side
            rc = verify_main(["--image", "img", "--inventory", inv_path,
                              "--pi-home", "/opt/pi"])
            self.assertNotEqual(rc, 0)

    @mock.patch("subprocess.run")
    def test_extension_package_name_mismatch(self, mock_run):
        """package.json name != source.package → non-zero exit."""
        with tempfile.TemporaryDirectory() as td:
            inv_path = _write_fixture(td)
            inv = _fixture_dict()

            def _side(cmd_args, **kwargs):
                cmd_str = " ".join(cmd_args)
                if "package.json" in cmd_str and "json.load" in cmd_str:
                    pkg_dir = cmd_args[-1]
                    if "pi-read" in pkg_dir:
                        return subprocess.CompletedProcess(
                            cmd_args, 0,
                            stdout='{"name":"@evil/pi-read","version":"0.2.0"}\n',
                            stderr="",
                        )
                    if "pi-codex-usage" in pkg_dir:
                        return subprocess.CompletedProcess(
                            cmd_args, 0,
                            stdout='{"name":"@llblab/pi-codex-usage","version":"0.3.1"}\n',
                            stderr="",
                        )
                    if "pi-proxy" in pkg_dir:
                        return subprocess.CompletedProcess(
                            cmd_args, 0,
                            stdout='{"name":"pi-proxy","version":"0.5.0"}\n',
                            stderr="",
                        )
                return _make_run_side_effect(inv)(cmd_args, **kwargs)

            mock_run.side_effect = _side
            rc = verify_main(["--image", "img", "--inventory", inv_path,
                              "--pi-home", "/opt/pi"])
            self.assertNotEqual(rc, 0)

    # --- CHOWN_WORK_ON_START ---

    @mock.patch("subprocess.run")
    def test_chown_work_on_start_is_set(self, mock_run):
        """Every docker run command includes CHOWN_WORK_ON_START=0."""
        with tempfile.TemporaryDirectory() as td:
            inv_path = _write_fixture(td)
            mock_run.side_effect = _make_run_side_effect(_fixture_dict())
            verify_main(["--image", "img", "--inventory", inv_path])
            for call_args in mock_run.call_args_list:
                cmd_parts = call_args[0][0]
                cmd_flat = " ".join(cmd_parts)
                if "docker" in cmd_parts[0] and "run" in cmd_parts[1:3]:
                    self.assertIn("-e", cmd_parts)
                    self.assertIn("CHOWN_WORK_ON_START=0", cmd_parts,
                                  f"CHOWN_WORK_ON_START=0 missing in: {cmd_flat}")

    # --- Rust component checks ---

    @mock.patch("subprocess.run")
    def test_rustfmt_clippy_installed(self, mock_run):
        """rustfmt and clippy are reported as installed → exit 0."""
        with tempfile.TemporaryDirectory() as td:
            inv_path = _write_fixture(td)
            mock_run.side_effect = _make_run_side_effect(_fixture_dict())
            rc = verify_main(["--image", "img", "--inventory", inv_path])
            self.assertEqual(rc, 0)

    @mock.patch("subprocess.run")
    def test_rustfmt_not_installed(self, mock_run):
        """rustfmt missing from component list → non-zero exit."""
        with tempfile.TemporaryDirectory() as td:
            inv_path = _write_fixture(td)
            inv = _fixture_dict()

            def _side(cmd_args, **kwargs):
                cmd_str = " ".join(cmd_args)
                if "rustup" in cmd_str and "component" in cmd_str and "list" in cmd_str:
                    installed = (
                        "rustc-x86_64-unknown-linux-gnu\n"
                        "cargo-x86_64-unknown-linux-gnu\n"
                    )
                    return subprocess.CompletedProcess(cmd_args, 0, stdout=installed, stderr="")
                return _make_run_side_effect(inv)(cmd_args, **kwargs)

            mock_run.side_effect = _side
            rc = verify_main(["--image", "img", "--inventory", inv_path])
            self.assertNotEqual(rc, 0)

    @mock.patch("subprocess.run")
    def test_clippy_not_installed(self, mock_run):
        """clippy missing from component list → non-zero exit."""
        with tempfile.TemporaryDirectory() as td:
            inv_path = _write_fixture(td)
            inv = _fixture_dict()

            def _side(cmd_args, **kwargs):
                cmd_str = " ".join(cmd_args)
                if "rustup" in cmd_str and "component" in cmd_str and "list" in cmd_str:
                    installed = (
                        "rustc-x86_64-unknown-linux-gnu\n"
                        "cargo-x86_64-unknown-linux-gnu\n"
                        "rustfmt-x86_64-unknown-linux-gnu\n"
                    )
                    return subprocess.CompletedProcess(cmd_args, 0, stdout=installed, stderr="")
                return _make_run_side_effect(inv)(cmd_args, **kwargs)

            mock_run.side_effect = _side
            rc = verify_main(["--image", "img", "--inventory", inv_path])
            self.assertNotEqual(rc, 0)

    # --- rustfmt / clippy callable ---

    @mock.patch("subprocess.run")
    def test_rustfmt_and_clippy_actually_called(self, mock_run):
        """rustfmt --version and cargo clippy --version are invoked."""
        with tempfile.TemporaryDirectory() as td:
            inv_path = _write_fixture(td)
            mock_run.side_effect = _make_run_side_effect(_fixture_dict())
            verify_main(["--image", "img", "--inventory", inv_path])
            all_cmds = " ".join(
                " ".join(call_args[0][0]) for call_args in mock_run.call_args_list
            )
            self.assertIn("rustfmt --version", all_cmds,
                          "rustfmt --version was not called")
            self.assertIn("cargo clippy --version", all_cmds,
                          "cargo clippy --version was not called")

    @mock.patch("subprocess.run")
    def test_rustfmt_unavailable_is_rejected(self, mock_run):
        """rustfmt registered but --version fails → non-zero exit."""
        with tempfile.TemporaryDirectory() as td:
            inv_path = _write_fixture(td)
            inv = _fixture_dict()

            def _side(cmd_args, **kwargs):
                cmd_str = " ".join(cmd_args)
                if "rustfmt --version" in cmd_str:
                    return subprocess.CompletedProcess(cmd_args, 1, stdout="", stderr="not found")
                return _make_run_side_effect(inv)(cmd_args, **kwargs)

            mock_run.side_effect = _side
            rc = verify_main(["--image", "img", "--inventory", inv_path])
            self.assertNotEqual(rc, 0)

    @mock.patch("subprocess.run")
    def test_clippy_unavailable_is_rejected(self, mock_run):
        """clippy registered but cargo clippy --version fails → non-zero exit."""
        with tempfile.TemporaryDirectory() as td:
            inv_path = _write_fixture(td)
            inv = _fixture_dict()

            def _side(cmd_args, **kwargs):
                cmd_str = " ".join(cmd_args)
                if "cargo clippy --version" in cmd_str:
                    return subprocess.CompletedProcess(cmd_args, 1, stdout="", stderr="not found")
                return _make_run_side_effect(inv)(cmd_args, **kwargs)

            mock_run.side_effect = _side
            rc = verify_main(["--image", "img", "--inventory", inv_path])
            self.assertNotEqual(rc, 0)

    # --- Deep inventory comparison ---

    @mock.patch("subprocess.run")
    def test_deep_inventory_catches_profile_change(self, mock_run):
        """Rust profile differs → caught by deep comparison."""
        with tempfile.TemporaryDirectory() as td:
            inv_path = _write_fixture(td)
            inv = _fixture_dict()
            inv["stages"]["toolchain"]["rust"]["profile"] = "complete"
            mock_run.side_effect = _make_run_side_effect(inv)
            rc = verify_main(["--image", "img", "--inventory", inv_path])
            self.assertNotEqual(rc, 0)

    @mock.patch("subprocess.run")
    def test_deep_inventory_catches_extra_image_key(self, mock_run):
        """Extra key in image inventory → caught by deep comparison."""
        with tempfile.TemporaryDirectory() as td:
            inv_path = _write_fixture(td)
            inv = _fixture_dict()
            inv["stages"]["toolchain"]["unexpected_tool"] = {"version": "9.9.9"}
            mock_run.side_effect = _make_run_side_effect(inv)
            rc = verify_main(["--image", "img", "--inventory", inv_path])
            self.assertNotEqual(rc, 0)

    # --- readlink -f failure ---

    @mock.patch("subprocess.run")
    def test_readlink_failure_detected(self, mock_run):
        """readlink -f returns empty/non-zero → explicit mismatch."""
        with tempfile.TemporaryDirectory() as td:
            inv_path = _write_fixture(td)
            inv = _fixture_dict()

            def _side(cmd_args, **kwargs):
                cmd_str = " ".join(cmd_args)
                if "readlink -f" in cmd_str:
                    return subprocess.CompletedProcess(cmd_args, 0, stdout="\n", stderr="")
                return _make_run_side_effect(inv)(cmd_args, **kwargs)

            mock_run.side_effect = _side
            rc = verify_main(["--image", "img", "--inventory", inv_path])
            self.assertNotEqual(rc, 0)
