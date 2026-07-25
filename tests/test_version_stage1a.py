"""Tests added in Stage 1A: entry contracts, typed access, digest, provider-field types.

All tests are RED — the current monolith does not implement these contracts.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

_THIS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(_THIS_DIR.parent))
sys.path.insert(0, str(_THIS_DIR))

from docker.versions import (
    InventoryError,
    VersionConfigError,
    ConstraintSyntaxError,
    load_inventory,
)

from versioning.support.inventory_builder import minimal_toml, write_toml, FIXTURES

# Artifact values matched to tested extension versions so the URL-version
# consistency check passes when tests override only the version line.
_EXT_ARTIFACT_1_2_3 = (
    'url = "https://registry.npmjs.org/@arcanemachine/pi-read/-/pi-read-1.2.3.tgz"\n'
    'integrity = "sha512-VO9pV15PFTBOfcNq9hgKJ3K6k4Bb0ndDlX6N5ReNTOa/r66/Ppfc9N/hexsK5veMHGl1YbjCo3wOnL5jJu17/Q=="\n'
)
_EXT_ARTIFACT_1_0_0 = (
    'url = "https://registry.npmjs.org/@arcanemachine/pi-read/-/pi-read-1.0.0.tgz"\n'
    'integrity = "sha512-VO9pV15PFTBOfcNq9hgKJ3K6k4Bb0ndDlX6N5ReNTOa/r66/Ppfc9N/hexsK5veMHGl1YbjCo3wOnL5jJu17/Q=="\n'
)
_EXT_ARTIFACT_0_3_0 = (
    'url = "https://registry.npmjs.org/@arcanemachine/pi-read/-/pi-read-0.3.0-beta.1.tgz"\n'
    'integrity = "sha512-VO9pV15PFTBOfcNq9hgKJ3K6k4Bb0ndDlX6N5ReNTOa/r66/Ppfc9N/hexsK5veMHGl1YbjCo3wOnL5jJu17/Q=="\n'
)
_EXT_ARTIFACT_0_2_0 = (
    'url = "https://registry.npmjs.org/@arcanemachine/pi-read/-/pi-read-0.2.0-beta.1.tgz"\n'
    'integrity = "sha512-VO9pV15PFTBOfcNq9hgKJ3K6k4Bb0ndDlX6N5ReNTOa/r66/Ppfc9N/hexsK5veMHGl1YbjCo3wOnL5jJu17/Q=="\n'
)

# ---------------------------------------------------------------------------
# 2. Constraint regression: equal strict/inclusive bounds
# ---------------------------------------------------------------------------

class TestConstraintEqualBoundRegression(unittest.TestCase):
    """Tests from stage-1a spec section 2."""

    def test_contradictory_gt_gte_lte(self):
        from docker.versions import parse_constraint, validate_constraint_consistency
        c = parse_constraint(">3.0.0,>=3.0.0,<=3.0.0")
        with self.assertRaises(ConstraintSyntaxError):
            validate_constraint_consistency(c)

    def test_contradictory_lt_lte_gte(self):
        from docker.versions import parse_constraint, validate_constraint_consistency
        c = parse_constraint("<3.0.0,<=3.0.0,>=3.0.0")
        with self.assertRaises(ConstraintSyntaxError):
            validate_constraint_consistency(c)

    def test_valid_gt_gte_lt(self):
        from docker.versions import parse_constraint, validate_constraint_consistency
        c = parse_constraint(">3.0.0,>=3.0.0,<4.0.0")
        validate_constraint_consistency(c)  # must not raise

    def test_valid_gte_lte(self):
        from docker.versions import parse_constraint, validate_constraint_consistency
        c = parse_constraint(">=3.0.0,<=3.0.0")
        validate_constraint_consistency(c)  # must not raise


# ---------------------------------------------------------------------------
# 3. Full entry contract: Python
# ---------------------------------------------------------------------------

class TestPythonEntryContract(unittest.TestCase):
    """Python must provide uv-python source + update."""

    def _load(self, **overrides: str) -> object:
        toml = minimal_toml(**overrides)
        path = write_toml(toml)
        try:
            return load_inventory(path)
        finally:
            path.unlink()

    def test_python_source_loaded(self):
        inv = self._load()
        s = inv.stages.toolchain.python.source
        self.assertEqual(s.type, "uv-python")
        self.assertEqual(s.implementation, "cpython")

    def test_python_update_loaded(self):
        inv = self._load()
        u = inv.stages.toolchain.python.update
        self.assertEqual(u.provider, "uv-python")
        self.assertEqual(u.implementation, "cpython")
        self.assertTrue(u.stable_only)

    def test_python_missing_source(self):
        toml = minimal_toml(
            **{"build.stages.toolchain.python.source": ""}
        )
        path = write_toml(toml)
        try:
            with self.assertRaises(InventoryError):
                load_inventory(path)
        finally:
            path.unlink()

    def test_python_missing_update(self):
        toml = minimal_toml(
            **{"build.stages.toolchain.python.update": ""}
        )
        path = write_toml(toml)
        try:
            with self.assertRaises(InventoryError):
                load_inventory(path)
        finally:
            path.unlink()

    def test_python_unknown_implementation(self):
        toml = minimal_toml(
            **{
                "build.stages.toolchain.python.source": (
                    'type = "uv-python"\nimplementation = "pypy"\n'
                ),
            }
        )
        path = write_toml(toml)
        try:
            with self.assertRaises(InventoryError):
                load_inventory(path)
        finally:
            path.unlink()

    def test_python_source_type_pypi_rejected(self):
        toml = minimal_toml(
            **{
                "build.stages.toolchain.python.source": (
                    'type = "pypi"\npackage = "python"\n'
                ),
            }
        )
        path = write_toml(toml)
        try:
            with self.assertRaises(InventoryError):
                load_inventory(path)
        finally:
            path.unlink()

    def test_python_incompatible_update_provider(self):
        toml = minimal_toml(
            **{
                "build.stages.toolchain.python.update": (
                    'provider = "npm"\nstable_only = true\nimplementation = "cpython"\n'
                ),
            }
        )
        path = write_toml(toml)
        try:
            with self.assertRaises(InventoryError):
                load_inventory(path)
        finally:
            path.unlink()

    def test_python_stable_only_not_boolean(self):
        toml = minimal_toml(
            **{
                "build.stages.toolchain.python.update": (
                    'provider = "uv-python"\nimplementation = "cpython"\nstable_only = "yes"\n'
                ),
            }
        )
        path = write_toml(toml)
        try:
            with self.assertRaises(InventoryError):
                load_inventory(path)
        finally:
            path.unlink()


# ---------------------------------------------------------------------------
# 3. Full entry contract: ty
# ---------------------------------------------------------------------------

class TestTyEntryContract(unittest.TestCase):
    """ty must provide pypi source + update."""

    def _load(self, **overrides: str) -> object:
        toml = minimal_toml(**overrides)
        path = write_toml(toml)
        try:
            return load_inventory(path)
        finally:
            path.unlink()

    def test_ty_loaded(self):
        inv = self._load()
        ty = inv.stages.toolchain.ty
        self.assertEqual(ty.version, "0.0.61")
        self.assertEqual(ty.source.type, "pypi")
        self.assertEqual(ty.source.package, "ty")
        self.assertEqual(ty.update.provider, "pypi")
        self.assertTrue(ty.update.stable_only)

    def test_ty_missing_after_load(self):
        """ty entry must be present, not silently dropped."""
        inv = self._load()
        self.assertIsNotNone(inv.stages.toolchain.ty)

    def test_ty_missing_package(self):
        toml = minimal_toml(
            **{
                "build.stages.toolchain.ty.source": 'type = "pypi"\n',
            }
        )
        path = write_toml(toml)
        try:
            with self.assertRaises(InventoryError):
                load_inventory(path)
        finally:
            path.unlink()

    def test_ty_empty_package(self):
        toml = minimal_toml(
            **{
                "build.stages.toolchain.ty.source": 'type = "pypi"\npackage = ""\n',
            }
        )
        path = write_toml(toml)
        try:
            with self.assertRaises(InventoryError):
                load_inventory(path)
        finally:
            path.unlink()

    def test_ty_incompatible_provider(self):
        toml = minimal_toml(
            **{
                "build.stages.toolchain.ty.update": (
                    'provider = "npm"\nstable_only = true\n'
                ),
            }
        )
        path = write_toml(toml)
        try:
            with self.assertRaises(InventoryError):
                load_inventory(path)
        finally:
            path.unlink()

    def test_ty_moving_version_latest(self):
        toml = minimal_toml(
            **{
                "build.stages.toolchain.ty": 'version = "latest"',
            }
        )
        path = write_toml(toml)
        try:
            with self.assertRaises((VersionConfigError, InventoryError)):
                load_inventory(path)
        finally:
            path.unlink()

    def test_ty_non_numeric_exact_version(self):
        toml = minimal_toml(
            **{
                "build.stages.toolchain.ty": 'version = "v0.0.61"',
            }
        )
        path = write_toml(toml)
        try:
            with self.assertRaises((VersionConfigError, InventoryError)):
                load_inventory(path)
        finally:
            path.unlink()


# ---------------------------------------------------------------------------
# 3. Full entry contract: Pi extensions
# ---------------------------------------------------------------------------

class TestPiExtensionContract(unittest.TestCase):
    """Each pi extension must have npm source + update, NO entry-level package."""

    def _load(self, **overrides: str) -> object:
        toml = minimal_toml(**overrides)
        path = write_toml(toml)
        try:
            return load_inventory(path)
        finally:
            path.unlink()

    def test_pi_read_has_source(self):
        inv = self._load()
        ext = inv.runtime_pi_extensions["pi-read"]
        self.assertEqual(ext.source.type, "npm")
        self.assertEqual(ext.source.package, "@arcanemachine/pi-read")

    def test_pi_read_has_update(self):
        inv = self._load()
        ext = inv.runtime_pi_extensions["pi-read"]
        self.assertEqual(ext.update.provider, "npm")
        self.assertTrue(ext.update.stable_only)

    def test_pi_read_no_entry_level_package(self):
        """Entry-level package is rejected — package belongs in source."""
        # Add package at entry level alongside the existing source
        toml = minimal_toml(
            **{
                "runtime.pi-extensions.pi-read": (
                    'version = "0.2.0"\n'
                    'package = "@arcanemachine/pi-read"\n'
                ),
            }
        )
        path = write_toml(toml)
        try:
            with self.assertRaises((InventoryError, VersionConfigError)):
                load_inventory(path)
        finally:
            path.unlink()

    def test_pi_read_missing_npm_source(self):
        toml = minimal_toml(
            **{
                "runtime.pi-extensions.pi-read": 'version = "0.2.0"',
                "runtime.pi-extensions.pi-read.source": "",  # remove source
            }
        )
        path = write_toml(toml)
        try:
            with self.assertRaises(InventoryError):
                load_inventory(path)
        finally:
            path.unlink()

    def test_pi_read_missing_update(self):
        toml = minimal_toml(
            **{
                "runtime.pi-extensions.pi-read": 'version = "0.2.0"',
                "runtime.pi-extensions.pi-read.update": "",  # remove update
            }
        )
        path = write_toml(toml)
        try:
            with self.assertRaises(InventoryError):
                load_inventory(path)
        finally:
            path.unlink()

    def test_pi_read_empty_package(self):
        toml = minimal_toml(
            **{
                "runtime.pi-extensions.pi-read.source": (
                    'type = "npm"\npackage = ""'
                ),
            }
        )
        path = write_toml(toml)
        try:
            with self.assertRaises((InventoryError, VersionConfigError)):
                load_inventory(path)
        finally:
            path.unlink()

    def test_pi_read_incompatible_provider(self):
        toml = minimal_toml(
            **{
                "runtime.pi-extensions.pi-read.update": (
                    'provider = "pypi"\nstable_only = true'
                ),
            }
        )
        path = write_toml(toml)
        try:
            with self.assertRaises(InventoryError):
                load_inventory(path)
        finally:
            path.unlink()

    def test_pi_read_malformed_version(self):
        # Extension versions are npm package versions — semver is broader than X.Y.Z.
        # Verify that valid semver pre-release tags pass.
        toml = minimal_toml(
            **{
                "runtime.pi-extensions.pi-read": 'version = "0.3.0-beta.1"',
                "runtime.pi-extensions.pi-read.artifact": _EXT_ARTIFACT_0_3_0,
            }
        )
        path = write_toml(toml)
        try:
            inv = load_inventory(path)
            self.assertEqual(
                inv.runtime_pi_extensions["pi-read"].version, "0.3.0-beta.1"
            )
        finally:
            path.unlink()


# ---------------------------------------------------------------------------
# 4. Provider-field type tests
# ---------------------------------------------------------------------------

class TestProviderFieldTypes(unittest.TestCase):
    """Wrong TOML types for provider-specific fields must raise path-qualified errors."""

    def _expect_error(self, **overrides: str):
        toml = minimal_toml(**overrides)
        path = write_toml(toml)
        try:
            with self.assertRaises(InventoryError) as ctx:
                load_inventory(path)
            return str(ctx.exception)
        finally:
            path.unlink()

    def test_stable_only_string(self):
        err = self._expect_error(
            **{
                "build.stages.toolchain.python.update": (
                    'provider = "uv-python"\nimplementation = "cpython"\nstable_only = "yes"\n'
                ),
            }
        )
        self.assertIn("boolean", err.lower())

    def test_required_platforms_string(self):
        err = self._expect_error(
            **{
                "build.stages.toolchain.uv.update": (
                    'provider = "github-release"\nstable_only = true\nrequired_platforms = "linux-amd64"\n'
                ),
            }
        )
        self.assertIn("list", err.lower())

    def test_channel_int(self):
        err = self._expect_error(
            **{
                "build.stages.toolchain.rust.update": (
                    'provider = "rust-channel"\nchannel = 123\nstable_only = true\n'
                ),
            }
        )
        self.assertIn("string", err.lower())

    def test_track_boolean(self):
        err = self._expect_error(
            **{
                "build.stages.base.node.update": (
                    'provider = "docker-registry"\nstable_only = true\ntrack = true\n'
                ),
            }
        )
        self.assertIn("string", err.lower())

    def test_implementation_not_string(self):
        err = self._expect_error(
            **{
                "build.stages.toolchain.python.source": (
                    'type = "uv-python"\nimplementation = ["cpython"]\n'
                ),
            }
        )
        self.assertIn("string", err.lower())

    # --- Enum fields ---

    def test_uv_python_implementation_cpython_accepted(self):
        inv = minimal_toml()  # defaults to cpython
        toml = inv
        path = write_toml(toml)
        try:
            load_inventory(path)  # must not raise
        finally:
            path.unlink()

    def test_rust_channel_stable_accepted(self):
        inv = minimal_toml()
        toml = inv
        path = write_toml(toml)
        try:
            load_inventory(path)
        finally:
            path.unlink()

    def test_docker_track_tag_digest_accepted(self):
        inv = minimal_toml()
        toml = inv
        path = write_toml(toml)
        try:
            load_inventory(path)
        finally:
            path.unlink()

    def test_unknown_implementation_rejected(self):
        err = self._expect_error(
            **{
                "build.stages.toolchain.python.source": (
                    'type = "uv-python"\nimplementation = "graalvm"\n'
                ),
            }
        )
        self.assertIn("implementation", err.lower())

    def test_unknown_rust_channel_rejected(self):
        err = self._expect_error(
            **{
                "build.stages.toolchain.rust.update": (
                    'provider = "rust-channel"\nchannel = "nightly"\nstable_only = true\n'
                ),
            }
        )
        # "nightly" is a moving selector → should be rejected
        self.assertTrue("moving" in err.lower() or "channel" in err.lower())


# ---------------------------------------------------------------------------
# 5. Digest regression tests
# ---------------------------------------------------------------------------

class TestDigestRegression(unittest.TestCase):
    """All digest failures must be InventoryError, never IndexError."""

    def _expect_inventory_error(self, digest_value: str):
        toml = minimal_toml(
            **{"base.node": f'digest = "{digest_value}"'}
        )
        path = write_toml(toml)
        try:
            with self.assertRaises(InventoryError):
                load_inventory(path)
        finally:
            path.unlink()

    def test_missing_sha256_prefix(self):
        self._expect_inventory_error(
            "ae91dcc111a68c9d2d81ff2a17bda61be126426176fde6fe7d08ab13b7f50573"
        )

    def test_wrong_algorithm_prefix(self):
        self._expect_inventory_error(
            "x:ae91dcc111a68c9d2d81ff2a17bda61be126426176fde6fe7d08ab13b7f50573"
        )

    def test_missing_colon(self):
        self._expect_inventory_error(
            "sha256ae91dcc111a68c9d2d81ff2a17bda61be126426176fde6fe7d08ab13b7f50573"
        )

    def test_uppercase_hex(self):
        self._expect_inventory_error(
            "sha256:AE91DCC111A68C9D2D81FF2A17BDA61BE126426176FDE6FE7D08AB13B7F50573"
        )

    def test_short_digest(self):
        self._expect_inventory_error(
            "sha256:ae91dcc111a68"
        )

    def test_non_hex(self):
        self._expect_inventory_error(
            "sha256:ae91dcc111a68c9d2d81ff2a17bda61be126426176fde6fe7d08ab13b7f5057g"
        )

    def test_placeholder_digest(self):
        self._expect_inventory_error(
            "sha256:0000000000000000000000000000000000000000000000000000000000000000"
        )

    def test_valid_digest_passes(self):
        toml = minimal_toml()
        path = write_toml(toml)
        try:
            load_inventory(path)  # must not raise
        finally:
            path.unlink()


# ---------------------------------------------------------------------------
# 6. Typed-access tests
# ---------------------------------------------------------------------------

class TestTypedAccess(unittest.TestCase):
    """All expected stage attributes exist; typos raise AttributeError."""

    def setUp(self):
        toml = minimal_toml()
        path = write_toml(toml)
        self._path = path
        self.inv = load_inventory(path)

    def tearDown(self):
        self._path.unlink()

    def test_base_node(self):
        self.assertIsNotNone(self.inv.stages.base.node)

    def test_toolchain_rust(self):
        self.assertIsNotNone(self.inv.stages.toolchain.rust)

    def test_toolchain_uv(self):
        self.assertIsNotNone(self.inv.stages.toolchain.uv)

    def test_toolchain_python(self):
        self.assertIsNotNone(self.inv.stages.toolchain.python)

    def test_toolchain_ty(self):
        self.assertIsNotNone(self.inv.stages.toolchain.ty)

    def test_rtk_prebuilt_rtk(self):
        self.assertIsNotNone(self.inv.stages.rtk_prebuilt.rtk)

    def test_fd_prebuilt_fd(self):
        self.assertIsNotNone(self.inv.stages.fd_prebuilt.fd)

    def test_pi_tools_pi(self):
        self.assertIsNotNone(self.inv.stages.pi_tools.pi)

    def test_openspec_tools_openspec(self):
        self.assertIsNotNone(self.inv.stages.openspec_tools.openspec)

    def test_runtime_oh_my_zsh(self):
        self.assertIsNotNone(self.inv.stages.runtime.oh_my_zsh)

    def test_pi_extensions_pi_read(self):
        self.assertIsNotNone(self.inv.runtime_pi_extensions["pi-read"])

    def test_typo_toolchain_tty(self):
        with self.assertRaises(AttributeError):
            _ = self.inv.stages.toolchain.tty

    def test_typo_rtk_prebuilt_rrtk(self):
        with self.assertRaises(AttributeError):
            _ = self.inv.stages.rtk_prebuilt.rrtk

    def test_typo_pi_tools_pii(self):
        with self.assertRaises(AttributeError):
            _ = self.inv.stages.pi_tools.pii


# ---------------------------------------------------------------------------
# 7. Real inventory test
# ---------------------------------------------------------------------------

class TestRealInventory(unittest.TestCase):
    """Production docker-constructor.toml must load."""

    def test_repository_inventory_is_valid(self):
        repo_root = _THIS_DIR.parent
        inv = load_inventory(repo_root / "docker-constructor.toml")
        # Python
        self.assertEqual(inv.stages.toolchain.python.version, "3.14.6")
        # ty
        self.assertEqual(inv.stages.toolchain.ty.version, "0.0.61")
        self.assertEqual(inv.stages.toolchain.ty.source.package, "ty")
        # pi-read extension
        pi_read = inv.runtime_pi_extensions["pi-read"]
        self.assertEqual(pi_read.version, "0.2.0")
        self.assertEqual(pi_read.source.package, "@arcanemachine/pi-read")
        self.assertEqual(pi_read.update.provider, "npm")


# ---------------------------------------------------------------------------
# 8. Import-boundary tests
# ---------------------------------------------------------------------------

class TestImportBoundary(unittest.TestCase):
    """Package imports and direct script execution must work."""

    def test_package_import_constraints(self):
        try:
            from docker.versioning.inventory import load_inventory as li  # noqa: F401, F811
            self.assertTrue(callable(li))
        except ImportError:
            self.fail("docker.versioning.inventory is not importable")

    def test_compat_import_from_docker_versions(self):
        from docker.versions import load_inventory as li  # noqa: F811
        self.assertTrue(callable(li))

    def test_direct_script_execution(self):
        import subprocess
        result = subprocess.run(
            [sys.executable, str(_THIS_DIR.parent / "docker" / "versions.py"), "validate"],
            capture_output=True,
            text=True,
        )
        self.assertEqual(
            result.returncode, 0,
            f"docker/versions.py failed: {result.stderr}"
        )


# 9. Entry-specific source/provider type enforcement
# ---------------------------------------------------------------------------

class TestEntrySpecificSourceProvider(unittest.TestCase):
    """Each entry mandates a specific source/update class, not merely a compatible pair."""

    def _expect_inventory_error(self, **overrides: str) -> str:
        toml = minimal_toml(**overrides)
        path = write_toml(toml)
        try:
            with self.assertRaises(InventoryError) as ctx:
                load_inventory(path)
            return str(ctx.exception)
        finally:
            path.unlink()

    # --- Python must be uv-python, not pypi even though pypi↔pypi is compatible ---

    def test_python_rejects_pypi_source(self):
        err = self._expect_inventory_error(
            **{
                "build.stages.toolchain.python.source": 'type = "pypi"\npackage = "cpython"\n',
                "build.stages.toolchain.python.update": 'provider = "pypi"\nstable_only = true\n',
            }
        )
        self.assertIn("uv-python", err)

    def test_python_rejects_npm_update(self):
        err = self._expect_inventory_error(
            **{
                "build.stages.toolchain.python.update": (
                    'provider = "npm"\nstable_only = true\n'
                ),
            }
        )
        self.assertIn("uv-python", err)

    # --- ty must be pypi, not npm ---

    def test_ty_rejects_npm_source(self):
        err = self._expect_inventory_error(
            **{
                "build.stages.toolchain.ty.source": 'type = "npm"\npackage = "ty"\n',
                "build.stages.toolchain.ty.update": 'provider = "npm"\nstable_only = true\n',
            }
        )
        self.assertIn("pypi", err)

    # --- Rust must be rust-channel ---

    def test_rust_rejects_github_source(self):
        err = self._expect_inventory_error(
            **{
                "build.stages.toolchain.rust.source": (
                    'type = "github-release"\n'
                    'repository = "rust-lang/rust"\n'
                    'tag = "1.0.0"\n'
                ),
                "build.stages.toolchain.rust.update": (
                    'provider = "github-release"\n'
                    'stable_only = true\n'
                    'required_platforms = ["linux-amd64"]\n'
                ),
            }
        )
        self.assertIn("rust-channel", err.lower())

    # --- pi extensions must be npm ---

    def test_pi_read_rejects_pypi_source(self):
        err = self._expect_inventory_error(
            **{
                "runtime.pi-extensions.pi-read.source": (
                    'type = "pypi"\npackage = "pi-read"\n'
                ),
                "runtime.pi-extensions.pi-read.update": (
                    'provider = "pypi"\nstable_only = true\n'
                ),
            }
        )
        self.assertIn("npm", err)

    def test_pi_read_rejects_github_update(self):
        err = self._expect_inventory_error(
            **{
                "runtime.pi-extensions.pi-read.update": (
                    'provider = "github-release"\n'
                    'stable_only = true\n'
                ),
            }
        )
        self.assertIn("npm", err)

    # --- npm tools (pi, openspec) must be npm ---

    def test_pi_tool_rejects_pypi_source(self):
        err = self._expect_inventory_error(
            **{
                "build.stages.pi-tools.pi.source": (
                    'type = "pypi"\npackage = "pi"\n'
                ),
                "build.stages.pi-tools.pi.update": (
                    'provider = "pypi"\nstable_only = true\n'
                ),
            }
        )
        self.assertIn("npm", err)


# ---------------------------------------------------------------------------
# 10. Unknown / misspelled TOML key rejection
# ---------------------------------------------------------------------------

class TestUnknownKeyRejection(unittest.TestCase):
    """Extra keys and typos like 'stabel_only' must raise path-qualified InventoryError."""

    def _expect_inventory_error(self, **overrides: str) -> str:
        toml = minimal_toml(**overrides)
        path = write_toml(toml)
        try:
            with self.assertRaises(InventoryError) as ctx:
                load_inventory(path)
            return str(ctx.exception)
        finally:
            path.unlink()

    def test_typo_stabel_only_rejected(self):
        # Build TOML manually — minimal_toml works with overrides but we need
        # an extra key inside the python.update table.
        toml = minimal_toml(
            **{
                "build.stages.toolchain.python.update": (
                    'provider = "uv-python"\n'
                    'implementation = "cpython"\n'
                    'stable_only = true\n'
                    'stabel_only = true\n'
                ),
            }
        )
        path = write_toml(toml)
        try:
            with self.assertRaises(InventoryError) as ctx:
                load_inventory(path)
            self.assertIn("stabel_only", str(ctx.exception))
        finally:
            path.unlink()

    def test_typo_verison_rejected(self):
        toml = minimal_toml(
            **{
                "build.stages.toolchain.rust": (
                    'version = "1.0.0"\n'
                    'profile = "minimal"\n'
                    'components = ["rustfmt"]\n'
                    'verison = "2.0.0"\n'
                ),
            }
        )
        path = write_toml(toml)
        try:
            with self.assertRaises(InventoryError) as ctx:
                load_inventory(path)
            self.assertIn("verison", str(ctx.exception))
        finally:
            path.unlink()

    def test_unknown_top_level_key_rejected(self):
        # Build a TOML with an extra top-level key
        toml = minimal_toml() + '\nstages_typo = 1\n'
        path = write_toml(toml)
        try:
            with self.assertRaises(InventoryError) as ctx:
                load_inventory(path)
            self.assertIn("stages_typo", str(ctx.exception))
        finally:
            path.unlink()

    def test_unknown_stage_key_rejected(self):
        toml = minimal_toml() + '\n[build.stages.toolchain_typo]\nversion = "1.0.0"\n'
        path = write_toml(toml)
        try:
            with self.assertRaises(InventoryError) as ctx:
                load_inventory(path)
            self.assertIn("toolchain_typo", str(ctx.exception))
        finally:
            path.unlink()

    def test_misspelled_tool_name_in_stage_rejected(self):
        toml = minimal_toml() + '\n[build.stages.rtk-prebuilt.rrtk]\nversion = "v1.0.0"\n'
        path = write_toml(toml)
        try:
            with self.assertRaises(InventoryError) as ctx:
                load_inventory(path)
            self.assertIn("rrtk", str(ctx.exception))
        finally:
            path.unlink()

    def test_misspelled_artifact_field_rejected(self):
        # Replace artifact section with one containing sh256 (typo)
        toml = minimal_toml()
        toml = toml.replace(
            'sha256 = "0a1b2c3d4e5f67890a1b2c3d4e5f67890a1b2c3d4e5f67890a1b2c3d4e5f6789"',
            'sh256 = "0a1b2c3d4e5f67890a1b2c3d4e5f67890a1b2c3d4e5f67890a1b2c3d4e5f6789"'
        )
        path = write_toml(toml)
        try:
            with self.assertRaises(InventoryError) as ctx:
                load_inventory(path)
            self.assertIn("sh256", str(ctx.exception))
        finally:
            path.unlink()

    def test_misspelled_artifact_field_in_second_platform_rejected(self):
        """linux-ppc64le artifact with sh256 typo must be caught via __ANY__ wildcard."""
        toml = minimal_toml()
        # Add another platform entry with misspelled sha256 field
        toml += """
[build.stages.toolchain.uv.artifacts.linux-ppc64le]
url = "https://example.invalid/uv-0.1.0-ppc64le.tar.gz"
sh256 = "b1a2c3d4e5f67890a1b2c3d4e5f67890a1b2c3d4e5f67890a1b2c3d4e5f6789"
"""
        path = write_toml(toml)
        try:
            with self.assertRaises(InventoryError) as ctx:
                load_inventory(path)
            self.assertIn("sh256", str(ctx.exception))
        finally:
            path.unlink()


# ---------------------------------------------------------------------------
# 11. Exact-version validation for Rust and npm tools
# ---------------------------------------------------------------------------

class TestExactVersionValidation(unittest.TestCase):
    """Rust, npm tools, UV, prebuilt tools, and extensions must all use pinned exact versions."""

    def _expect_inventory_error(self, **overrides: str) -> str:
        toml = minimal_toml(**overrides)
        path = write_toml(toml)
        try:
            with self.assertRaises(InventoryError) as ctx:
                load_inventory(path)
            return str(ctx.exception)
        finally:
            path.unlink()

    # --- Rust ---

    def test_rust_rejects_arbitrary_string(self):
        err = self._expect_inventory_error(
            **{"build.stages.toolchain.rust": 'version = "latest"\nprofile = "minimal"\ncomponents = ["rustfmt"]\n'}
        )
        self.assertIn("X.Y.Z", err)

    def test_rust_rejects_semver_prerelease(self):
        err = self._expect_inventory_error(
            **{"build.stages.toolchain.rust": 'version = "1.88.0-beta"\nprofile = "minimal"\ncomponents = ["rustfmt"]\n'}
        )
        self.assertIn("X.Y.Z", err)

    def test_rust_accepts_exact_version(self):
        toml = minimal_toml()
        path = write_toml(toml)
        try:
            load_inventory(path)  # must not raise
        finally:
            path.unlink()

    # --- npm tools ---

    def test_npm_tool_rejects_latest_tag(self):
        err = self._expect_inventory_error(
            **{"build.stages.pi-tools.pi": 'version = "latest"\n'}
        )
        self.assertIn("X.Y.Z", err)

    def test_npm_tool_rejects_range(self):
        err = self._expect_inventory_error(
            **{"build.stages.pi-tools.pi": 'version = "^1.0.0"\n'}
        )
        self.assertIn("X.Y.Z", err)

    # --- UV ---

    def test_uv_rejects_latest(self):
        err = self._expect_inventory_error(
            **{
                "build.stages.toolchain.uv": 'version = "latest"',
                "build.stages.toolchain.uv.source": (
                    'type = "github-release"\n'
                    'repository = "astral-sh/uv"\n'
                    'tag = "latest"\n'
                ),
            }
        )
        self.assertIn("X.Y.Z", err)

    def test_uv_rejects_v_prefix(self):
        err = self._expect_inventory_error(
            **{
                "build.stages.toolchain.uv": 'version = "v0.1.0"',
                "build.stages.toolchain.uv.source": (
                    'type = "github-release"\n'
                    'repository = "astral-sh/uv"\n'
                    'tag = "v0.1.0"\n'
                ),
            }
        )
        self.assertIn("X.Y.Z", err)

    def test_uv_accepts_numeric(self):
        toml = minimal_toml()  # "0.1.0"
        path = write_toml(toml)
        try:
            load_inventory(path)
        finally:
            path.unlink()

    # --- Prebuilt tools ---

    def test_prebuilt_rejects_bare_numeric(self):
        err = self._expect_inventory_error(
            **{
                "build.stages.rtk-prebuilt.rtk": 'version = "1.0.0"',
                "build.stages.rtk-prebuilt.rtk.source": (
                    'type = "github-release"\n'
                    'repository = "rtk-ai/rtk"\n'
                    'tag = "1.0.0"\n'
                ),
            }
        )
        self.assertIn("vX.Y.Z", err)

    def test_prebuilt_rejects_latest(self):
        err = self._expect_inventory_error(
            **{
                "build.stages.rtk-prebuilt.rtk": 'version = "latest"',
                "build.stages.rtk-prebuilt.rtk.source": (
                    'type = "github-release"\n'
                    'repository = "rtk-ai/rtk"\n'
                    'tag = "latest"\n'
                ),
            }
        )
        self.assertIn("vX.Y.Z", err)

    def test_prebuilt_accepts_v_prefix(self):
        toml = minimal_toml()  # "v0.43.0"
        path = write_toml(toml)
        try:
            load_inventory(path)
        finally:
            path.unlink()

    # --- Pi extensions ---

    def test_extension_rejects_latest(self):
        err = self._expect_inventory_error(
            **{"runtime.pi-extensions.pi-read": 'version = "latest"\n'}
        )
        self.assertIn("moving", err.lower())

    def test_extension_rejects_stable_tag(self):
        err = self._expect_inventory_error(
            **{"runtime.pi-extensions.pi-read": 'version = "stable"\n'}
        )
        self.assertIn("moving", err.lower())

    def test_extension_rejects_next_tag(self):
        err = self._expect_inventory_error(
            **{"runtime.pi-extensions.pi-read": 'version = "next"\n'}
        )
        self.assertIn("moving", err.lower())

    def test_extension_accepts_x_y_z(self):
        toml = minimal_toml(**{
            "runtime.pi-extensions.pi-read": 'version = "1.2.3"\n',
            "runtime.pi-extensions.pi-read.artifact": _EXT_ARTIFACT_1_2_3,
        })
        path = write_toml(toml)
        try:
            inv = load_inventory(path)
            self.assertEqual(inv.runtime_pi_extensions["pi-read"].version, "1.2.3")
        finally:
            path.unlink()

    def test_extension_accepts_semver_prerelease(self):
        toml = minimal_toml(**{
            "runtime.pi-extensions.pi-read": 'version = "0.2.0-beta.1"\n',
            "runtime.pi-extensions.pi-read.artifact": _EXT_ARTIFACT_0_2_0,
        })
        path = write_toml(toml)
        try:
            inv = load_inventory(path)
            self.assertEqual(inv.runtime_pi_extensions["pi-read"].version, "0.2.0-beta.1")
        finally:
            path.unlink()

    def test_extension_accepts_build_suffix(self):
        toml = minimal_toml(**{
            "runtime.pi-extensions.pi-read": 'version = "1.0.0+build.1"\n',
            "runtime.pi-extensions.pi-read.artifact": _EXT_ARTIFACT_1_0_0,
        })
        path = write_toml(toml)
        try:
            inv = load_inventory(path)
            self.assertEqual(inv.runtime_pi_extensions["pi-read"].version, "1.0.0+build.1")
        finally:
            path.unlink()

    def test_extension_rejects_malformed_prerelease_bang(self):
        err = self._expect_inventory_error(
            **{"runtime.pi-extensions.pi-read": 'version = "1.0.0-!!!"\n'}
        )
        self.assertIn("invalid", err.lower())

    def test_extension_rejects_dangling_hyphen(self):
        err = self._expect_inventory_error(
            **{"runtime.pi-extensions.pi-read": 'version = "1.0.0-"\n'}
        )
        self.assertIn("invalid", err.lower())

    def test_extension_rejects_dangling_plus(self):
        err = self._expect_inventory_error(
            **{"runtime.pi-extensions.pi-read": 'version = "1.0.0+"\n'}
        )
        self.assertIn("invalid", err.lower())

    def test_extension_rejects_leading_zero_in_identifier(self):
        err = self._expect_inventory_error(
            **{"runtime.pi-extensions.pi-read": 'version = "1.0.0-01"\n'}
        )
        self.assertIn("invalid", err.lower())

    def test_extension_rejects_double_dot(self):
        err = self._expect_inventory_error(
            **{"runtime.pi-extensions.pi-read": 'version = "1.0.0-beta..1"\n'}
        )
        self.assertIn("invalid", err.lower())


# ---------------------------------------------------------------------------
# 12. Immutability
# ---------------------------------------------------------------------------

class TestSchemaTypePreservation(unittest.TestCase):
    """Wrong-type schema values must not be rewritten as missing-key errors."""

    def test_schema_string_reports_type_error(self):
        toml = minimal_toml()
        toml = toml.replace('schema = 1', 'schema = "1"')
        path = write_toml(toml)
        try:
            with self.assertRaises(InventoryError) as ctx:
                load_inventory(path)
            msg = str(ctx.exception)
            self.assertIn("expected integer", msg)
            self.assertIn("str", msg)
            self.assertNotIn("missing", msg.lower())
        finally:
            path.unlink()

    def test_schema_bool_reports_type_error(self):
        toml = minimal_toml()
        toml = toml.replace('schema = 1', 'schema = true')
        path = write_toml(toml)
        try:
            with self.assertRaises(InventoryError) as ctx:
                load_inventory(path)
            msg = str(ctx.exception)
            self.assertIn("expected integer", msg)
            self.assertIn("bool", msg)
            self.assertNotIn("missing", msg.lower())
        finally:
            path.unlink()

    def test_schema_float_reports_type_error(self):
        toml = minimal_toml()
        toml = toml.replace('schema = 1', 'schema = 1.0')
        path = write_toml(toml)
        try:
            with self.assertRaises(InventoryError) as ctx:
                load_inventory(path)
            msg = str(ctx.exception)
            self.assertIn("expected integer", msg)
            self.assertIn("float", msg)
            self.assertNotIn("missing", msg.lower())
        finally:
            path.unlink()

    def test_schema_missing_reports_correctly(self):
        toml = minimal_toml()
        lines = [l for l in toml.split('\n') if not l.startswith('schema')]
        toml = '\n'.join(lines)
        path = write_toml(toml)
        try:
            with self.assertRaises(InventoryError) as ctx:
                load_inventory(path)
            msg = str(ctx.exception)
            self.assertIn("missing", msg.lower())
            self.assertIn("schema", msg.lower())
        finally:
            path.unlink()


class TestImmutability(unittest.TestCase):
    """Loaded inventory values must be immutable — tuples and MappingProxyTypes."""

    def setUp(self):
        toml = minimal_toml()
        path = write_toml(toml)
        self._path = path
        self.inv = load_inventory(path)

    def tearDown(self):
        self._path.unlink()

    def test_rust_components_is_tuple(self):
        self.assertIsInstance(self.inv.stages.toolchain.rust.components, tuple)

    def test_rust_components_rejects_mutation(self):
        with self.assertRaises((TypeError, AttributeError)):
            self.inv.stages.toolchain.rust.components[0] = "miri"  # type: ignore[index]

    def test_artifacts_is_immutable(self):
        from types import MappingProxyType
        self.assertIsInstance(self.inv.stages.toolchain.uv.artifacts, MappingProxyType)

    def test_artifacts_rejects_mutation(self):
        with self.assertRaises((TypeError, AttributeError)):
            self.inv.stages.toolchain.uv.artifacts["new"] = None  # type: ignore[index]

    def test_extensions_is_immutable(self):
        from types import MappingProxyType
        self.assertIsInstance(self.inv.runtime_pi_extensions, MappingProxyType)

    def test_extensions_rejects_mutation(self):
        with self.assertRaises((TypeError, AttributeError)):
            self.inv.runtime_pi_extensions["new-ext"] = None  # type: ignore[index]
