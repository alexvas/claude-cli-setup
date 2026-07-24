"""Unit tests for ``docker.versioning.rendering`` — build argument rendering.

All tests use the shared inventory builder; no Docker, no network, no
subprocess.
"""
from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from types import MappingProxyType

from docker.versioning.effective import (
    EffectiveConfiguration,
    EffectiveConfigError,
    apply_overrides,
)
from docker.versioning.inventory import load_inventory
from docker.versioning.rendering import (
    EffectiveInventoryOutputError,
    compose_command,
    render_build_environment,
    write_effective_inventory,
)

from tests.versioning.support.inventory_builder import minimal_toml, write_toml


def _python_override_toml() -> str:
    """Return minimal TOML with Python override policy declared."""
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


class TestRenderBuildEnvironment(unittest.TestCase):
    """Tests for ``render_build_environment()``."""

    def setUp(self):
        self.toml_path = write_toml(_python_override_toml())
        self.inventory = load_inventory(self.toml_path)
        self.effective = apply_overrides(self.inventory, {})

    def tearDown(self):
        self.toml_path.unlink(missing_ok=True)

    # ------------------------------------------------------------------
    # Default configuration
    # ------------------------------------------------------------------

    def test_default_renders_all_expected_variables(self):
        env = render_build_environment(self.effective)

        expected = {
            "NODE_BASE_IMAGE",
            "RUST_VERSION", "RUST_PROFILE", "RUST_COMPONENTS",
            "UV_VERSION", "UV_URL", "UV_SHA256",
            "PYTHON_VERSION", "TY_VERSION",
            "RUSTUP_URL", "RUSTUP_SHA256",
            "RTK_VERSION", "RTK_URL", "RTK_SHA256",
            "FD_VERSION", "FD_URL", "FD_SHA256",
            "PI_VERSION", "OPENSPEC_VERSION",
            "OH_MY_ZSH_VERSION",
            "PI_READ_VERSION",
            "PI_CODEX_USAGE_VERSION",
            "PI_PROXY_VERSION",
            "EFFECTIVE_VERSIONS_FILE",
        }
        self.assertEqual(set(env.keys()), expected)

    def test_default_values_match_inventory(self):
        env = render_build_environment(self.effective)
        inv = self.inventory

        # Node image: docker.io/library/node:<tag>@<digest>
        expected_node_img = (
            "docker.io/library/node:24-trixie-slim"
            "@sha256:0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"
        )
        self.assertEqual(env["NODE_BASE_IMAGE"], expected_node_img)

        # Toolchain
        self.assertEqual(env["RUST_VERSION"], "1.0.0")
        self.assertEqual(env["RUST_PROFILE"], "minimal")
        self.assertEqual(env["RUST_COMPONENTS"], "rustfmt clippy")
        self.assertEqual(env["UV_VERSION"], "0.1.0")
        self.assertEqual(env["PYTHON_VERSION"], "3.14.6")
        self.assertEqual(env["TY_VERSION"], "0.0.61")

        # Prebuilt
        self.assertEqual(env["RTK_VERSION"], "v0.43.0")
        self.assertEqual(env["FD_VERSION"], "v10.4.2")

        # Node tools
        self.assertEqual(env["PI_VERSION"], "0.80.10")
        self.assertEqual(env["OPENSPEC_VERSION"], "1.6.0")

        # Runtime
        self.assertEqual(env["OH_MY_ZSH_VERSION"],
                         "70ad5e3df8f7bed68aa6672029496926e632aedd")

    def test_node_image_format_is_registry_repo_tag_digest(self):
        env = render_build_environment(self.effective)
        img = env["NODE_BASE_IMAGE"]
        self.assertRegex(
            img,
            r"^docker\.io/library/node:24-trixie-slim@sha256:[a-f0-9]{64}$",
        )

    # ------------------------------------------------------------------
    # Python override
    # ------------------------------------------------------------------

    def test_python_override_changes_python_version(self):
        eff = apply_overrides(self.inventory, {
            "stages.toolchain.python.version": "3.14.7",
        })
        env = render_build_environment(eff)
        self.assertEqual(env["PYTHON_VERSION"], "3.14.7")

    def test_python_override_does_not_change_other_values(self):
        base_env = render_build_environment(self.effective)
        eff = apply_overrides(self.inventory, {
            "stages.toolchain.python.version": "3.14.7",
        })
        over_env = render_build_environment(eff)

        for key in base_env:
            if key == "PYTHON_VERSION":
                continue
            self.assertEqual(base_env[key], over_env[key],
                             f"{key} changed after Python override")

    # ------------------------------------------------------------------
    # Artifacts — platform selection
    # ------------------------------------------------------------------

    def test_artifacts_selected_for_linux_amd64(self):
        env = render_build_environment(self.effective, platform="linux-amd64")
        # x86_64 is the canonical arch for linux-amd64
        self.assertIn("x86_64", env["UV_URL"])
        self.assertTrue(
            env["UV_URL"].startswith("https://"),
            f"UV_URL is not a URL: {env['UV_URL']}",
        )

    def test_unknown_platform_raises_effective_config_error(self):
        with self.assertRaises(EffectiveConfigError) as ctx:
            render_build_environment(self.effective, platform="nonexistent-os")
        self.assertIn("nonexistent-os", str(ctx.exception))

    # ------------------------------------------------------------------
    # All values are strings
    # ------------------------------------------------------------------

    def test_all_values_are_strings(self):
        env = render_build_environment(self.effective)
        for key, value in env.items():
            self.assertIsInstance(value, str,
                                  f"{key} is {type(value).__name__}, not str")

    # ------------------------------------------------------------------
    # Deterministic ordering
    # ------------------------------------------------------------------

    def test_deterministic_ordering(self):
        env1 = render_build_environment(self.effective)
        env2 = render_build_environment(self.effective)
        self.assertEqual(list(env1.keys()), list(env2.keys()))

    # ------------------------------------------------------------------
    # Values with spaces
    # ------------------------------------------------------------------

    def test_rust_components_preserves_spaces(self):
        env = render_build_environment(self.effective)
        self.assertEqual(env["RUST_COMPONENTS"], "rustfmt clippy")

    # ------------------------------------------------------------------
    # Effective versions file
    # ------------------------------------------------------------------

    def test_effective_versions_file_in_output(self):
        env = render_build_environment(self.effective)
        self.assertIn("EFFECTIVE_VERSIONS_FILE", env)
        self.assertEqual(env["EFFECTIVE_VERSIONS_FILE"],
                         ".docker-generated/docker-constructor.toml")

    def test_custom_inventory_output_path(self):
        env = render_build_environment(
            self.effective,
            inventory_output="build/effective.toml",
        )
        self.assertEqual(env["EFFECTIVE_VERSIONS_FILE"], "build/effective.toml")


class TestWriteEffectiveInventory(unittest.TestCase):
    """Tests for ``write_effective_inventory()``."""

    def setUp(self):
        self.toml_path = write_toml(_python_override_toml())
        self.inventory = load_inventory(self.toml_path)
        self.effective = apply_overrides(self.inventory, {})
        self.tmpdir = Path(tempfile.mkdtemp())

    def tearDown(self):
        self.toml_path.unlink(missing_ok=True)
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    # ------------------------------------------------------------------
    # Write and read-back
    # ------------------------------------------------------------------

    def test_written_toml_is_readable(self):
        dest = self.tmpdir / "versions.toml"
        write_effective_inventory(self.effective, dest)
        self.assertTrue(dest.is_file())

        import tomllib
        with open(dest, "rb") as f:
            data = tomllib.load(f)
        self.assertIn("stages", data)

    def test_full_load_inventory_round_trip(self):
        """Generated TOML must survive a full ``load_inventory()``
        round-trip: schema at top level, all tables parse correctly,
        version values preserved."""
        dest = self.tmpdir / "versions.toml"
        write_effective_inventory(self.effective, dest)

        # Must parse with tomllib
        import tomllib
        with open(dest, "rb") as f:
            raw = tomllib.load(f)

        # schema must be a top-level key (not absorbed into a table)
        self.assertIn("schema", raw,
                      "schema missing — likely absorbed into preceding table")
        self.assertEqual(raw["schema"], 1)

        # stages must be a top-level key
        self.assertIn("stages", raw)
        self.assertIn("toolchain", raw["stages"])

        # load_inventory must succeed (validates types, constraints)
        from docker.versioning.inventory import load_inventory
        reloaded = load_inventory(dest)
        self.assertEqual(
            reloaded.stages.toolchain.python.version,
            self.effective.inventory.stages.toolchain.python.version,
        )

    def test_python_override_reflected_in_written_toml(self):
        eff = apply_overrides(self.inventory, {
            "stages.toolchain.python.version": "3.14.7",
        })
        dest = self.tmpdir / "versions.toml"
        write_effective_inventory(eff, dest)

        import tomllib
        with open(dest, "rb") as f:
            data = tomllib.load(f)
        self.assertEqual(
            data["stages"]["toolchain"]["python"]["version"],
            "3.14.7",
        )

    def test_deterministic_output(self):
        dest = self.tmpdir / "versions.toml"
        write_effective_inventory(self.effective, dest)
        content1 = dest.read_bytes()

        dest.unlink()
        write_effective_inventory(self.effective, dest)
        content2 = dest.read_bytes()

        self.assertEqual(content1, content2)

    def test_atomic_write(self):
        dest = self.tmpdir / "versions.toml"

        self.assertFalse(dest.is_file())
        write_effective_inventory(self.effective, dest)
        self.assertTrue(dest.is_file())

        tmps = list(self.tmpdir.glob(".versions-*"))
        self.assertEqual(len(tmps), 0,
                         f"tmp files left behind: {tmps}")

    def test_creates_parent_directory(self):
        dest = self.tmpdir / "deep" / "nested" / "versions.toml"
        write_effective_inventory(self.effective, dest)
        self.assertTrue(dest.is_file())

    def test_does_not_overwrite_original_versions_toml(self):
        dest = self.tmpdir / "versions.toml"
        original_mtime = self.toml_path.stat().st_mtime
        write_effective_inventory(self.effective, dest)
        self.assertEqual(self.toml_path.stat().st_mtime, original_mtime)


class TestEffectiveInventoryOutputValidation(unittest.TestCase):
    """Tests for ``write_effective_inventory`` path validation."""

    def setUp(self):
        self.tmpdir = Path(tempfile.mkdtemp())
        self.repo = self.tmpdir / "repo"
        self.repo.mkdir()
        (self.repo / "docker-constructor.toml").write_text(
            minimal_toml(), encoding="utf-8",
        )
        from docker.versioning.inventory import load_inventory
        from docker.versioning.effective import apply_overrides
        inv = load_inventory(self.repo / "docker-constructor.toml")
        self.effective = apply_overrides(inv, {})

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_valid_relative_path_inside_repo(self):
        dest = self.repo / ".docker-generated" / "docker-constructor.toml"
        write_effective_inventory(
            self.effective, dest,
            repo_root=self.repo,
            output_path=".docker-generated/docker-constructor.toml",
        )
        self.assertTrue(dest.is_file())

    def test_absolute_path_rejected(self):
        with self.assertRaises(EffectiveInventoryOutputError) as ctx:
            write_effective_inventory(
                self.effective, Path("/etc/versions.toml"),
                repo_root=self.repo,
                output_path="/etc/versions.toml",
            )
        self.assertIn("relative path", str(ctx.exception).lower())

    def test_traversal_rejected(self):
        with self.assertRaises(EffectiveInventoryOutputError) as ctx:
            write_effective_inventory(
                self.effective, Path("/tmp/ignored"),
                repo_root=self.repo,
                output_path="../etc/versions.toml",
            )
        self.assertIn("..", str(ctx.exception))

    def test_docker_constructor_toml_rejected(self):
        with self.assertRaises(EffectiveInventoryOutputError) as ctx:
            write_effective_inventory(
                self.effective, self.repo / "docker-constructor.toml",
                repo_root=self.repo,
                output_path="docker-constructor.toml",
            )
        self.assertIn("authoritative", str(ctx.exception).lower())

    def test_symlink_escape_rejected(self):
        # Create a symlink pointing outside the repo
        outside = self.tmpdir / "outside.toml"
        outside.write_text("# bad", encoding="utf-8")
        (self.repo / ".docker-generated").mkdir(exist_ok=True)
        link_target = self.repo / ".docker-generated" / "docker-constructor.toml"
        link_target.symlink_to(outside.resolve())
        with self.assertRaises(EffectiveInventoryOutputError) as ctx:
            write_effective_inventory(
                self.effective, link_target,
                repo_root=self.repo,
                output_path=".docker-generated/docker-constructor.toml",
            )
        self.assertIn("symlink", str(ctx.exception).lower())


class TestComposeCommand(unittest.TestCase):
    """Tests for ``compose_command()``."""

    def test_returns_tuple(self):
        cmd = compose_command(["build", "pi"])
        self.assertIsInstance(cmd, tuple)

    def test_canonical_form(self):
        cmd = compose_command(["build", "pi"])
        self.assertEqual(cmd, ("docker", "compose", "build", "pi"))

    def test_no_args(self):
        cmd = compose_command([])
        self.assertEqual(cmd, ("docker", "compose"))

    def test_with_options(self):
        cmd = compose_command(["--progress", "plain", "build", "pi"])
        self.assertEqual(
            cmd,
            ("docker", "compose", "--progress", "plain", "build", "pi"),
        )


if __name__ == "__main__":
    unittest.main()
