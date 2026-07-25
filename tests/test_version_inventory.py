"""Tests for docker-constructor.toml inventory loading and validation."""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))  # tests/ for versioning support
from docker.versions import (
    InventoryError,
    VersionConfigError,
    load_inventory,
)

from versioning.support.inventory_builder import minimal_toml, write_toml, FIXTURES

# Re-export helpers for test methods that already reference them as _minimal_toml, _write_toml
_minimal_toml = minimal_toml
_write_toml = write_toml
# ---------------------------------------------------------------------------
# Valid inventory — core values
# ---------------------------------------------------------------------------

class TestValidInventory(unittest.TestCase):
    """Valid inventory loads without errors."""

    def test_valid_minimal(self):
        inv = load_inventory(FIXTURES / "valid-minimal.toml")
        self.assertEqual(inv.schema, 1)
        self.assertIsNotNone(inv.stages.base)
        self.assertIsNotNone(inv.stages.toolchain)
        self.assertEqual(inv.stages.toolchain.rust.version, "1.88.0")
        self.assertEqual(inv.stages.toolchain.uv.version, "0.11.29")
        self.assertEqual(inv.stages.toolchain.python.version, "3.14.6")

    def test_node_tag(self):
        inv = load_inventory(FIXTURES / "valid-minimal.toml")
        self.assertEqual(inv.stages.base.node.tag, "24-trixie-slim")

    def test_node_digest(self):
        inv = load_inventory(FIXTURES / "valid-minimal.toml")
        self.assertEqual(
            inv.stages.base.node.digest,
            "sha256:ae91dcc111a68c9d2d81ff2a17bda61be126426176fde6fe7d08ab13b7f50573",
        )

    def test_rust_version(self):
        inv = load_inventory(FIXTURES / "valid-minimal.toml")
        self.assertEqual(inv.stages.toolchain.rust.version, "1.88.0")

    def test_rust_profile(self):
        inv = load_inventory(FIXTURES / "valid-minimal.toml")
        self.assertEqual(inv.stages.toolchain.rust.profile, "minimal")

    def test_rust_components(self):
        inv = load_inventory(FIXTURES / "valid-minimal.toml")
        self.assertEqual(
            inv.stages.toolchain.rust.components, ("rustfmt", "clippy")
        )

    def test_python_exact_version(self):
        inv = load_inventory(FIXTURES / "valid-minimal.toml")
        self.assertEqual(inv.stages.toolchain.python.version, "3.14.6")

    def test_python_override_policy(self):
        inv = load_inventory(FIXTURES / "valid-minimal.toml")
        policy = inv.stages.toolchain.python.override
        self.assertIsNotNone(policy)
        self.assertEqual(policy.scheme, "numeric")
        self.assertFalse(policy.allow_prerelease)
        self.assertEqual(str(policy.constraint), ">=3.14.6")

    def test_rtk_artifact(self):
        inv = load_inventory(FIXTURES / "valid-minimal.toml")
        rtk = inv.stages.rtk_prebuilt.rtk
        self.assertEqual(rtk.version, "v0.43.0")
        art = rtk.artifacts["linux-amd64"]
        self.assertIn("v0.43.0", art.url)
        self.assertEqual(len(art.sha256), 64)

    def test_fd_artifact(self):
        inv = load_inventory(FIXTURES / "valid-minimal.toml")
        fd = inv.stages.fd_prebuilt.fd
        self.assertEqual(fd.version, "v10.4.2")
        art = fd.artifacts["linux-amd64"]
        self.assertIn("v10.4.2", art.url)
        self.assertEqual(len(art.sha256), 64)

    def test_pi_version(self):
        inv = load_inventory(FIXTURES / "valid-minimal.toml")
        self.assertEqual(inv.stages.pi_tools.pi.version, "0.80.10")

    def test_openspec_version(self):
        inv = load_inventory(FIXTURES / "valid-minimal.toml")
        self.assertEqual(inv.stages.openspec_tools.openspec.version, "1.6.0")

    def test_oh_my_zsh_revision(self):
        inv = load_inventory(FIXTURES / "valid-minimal.toml")
        self.assertEqual(
            inv.stages.runtime.oh_my_zsh.revision,
            "70ad5e3df8f7bed68aa6672029496926e632aedd",
        )

    def test_pi_read_extension(self):
        inv = load_inventory(FIXTURES / "valid-minimal.toml")
        ext = inv.runtime_pi_extensions["pi-read"]
        self.assertEqual(ext.version, "0.2.0")
        self.assertEqual(ext.source.package, "@arcanemachine/pi-read")


# ---------------------------------------------------------------------------
# Valid inventory — source/update metadata on every versioned entry
# ---------------------------------------------------------------------------

class TestSourceMetadata(unittest.TestCase):
    """Every versioned entry exposes source and update metadata."""

    def test_node_source(self):
        inv = load_inventory(FIXTURES / "valid-minimal.toml")
        s = inv.stages.base.node.source
        self.assertEqual(s.type, "docker-registry")
        self.assertEqual(s.registry, "docker.io")
        self.assertEqual(s.repository, "library/node")

    def test_node_update(self):
        inv = load_inventory(FIXTURES / "valid-minimal.toml")
        u = inv.stages.base.node.update
        self.assertEqual(u.provider, "docker-registry")
        self.assertTrue(u.stable_only)
        self.assertEqual(u.track, "tag-digest")

    def test_rust_source(self):
        inv = load_inventory(FIXTURES / "valid-minimal.toml")
        s = inv.stages.toolchain.rust.source
        self.assertEqual(s.type, "rust-channel")
        self.assertIn("rust-1.88.0.toml", s.manifest)

    def test_rust_update(self):
        inv = load_inventory(FIXTURES / "valid-minimal.toml")
        u = inv.stages.toolchain.rust.update
        self.assertEqual(u.provider, "rust-channel")
        self.assertEqual(u.channel, "stable")
        self.assertTrue(u.stable_only)

    def test_uv_source(self):
        inv = load_inventory(FIXTURES / "valid-minimal.toml")
        s = inv.stages.toolchain.uv.source
        self.assertEqual(s.type, "github-release")
        self.assertEqual(s.repository, "astral-sh/uv")
        self.assertEqual(s.tag, "0.11.29")

    def test_uv_update(self):
        inv = load_inventory(FIXTURES / "valid-minimal.toml")
        u = inv.stages.toolchain.uv.update
        self.assertEqual(u.provider, "github-release")
        self.assertTrue(u.stable_only)
        self.assertIn("linux-amd64", u.required_platforms)

    def test_uv_artifact_under_artifacts(self):
        inv = load_inventory(FIXTURES / "valid-minimal.toml")
        art = inv.stages.toolchain.uv.artifacts["linux-amd64"]
        self.assertIn("uv-x86_64-unknown-linux-gnu.tar.gz", art.url)

    def test_rtk_source(self):
        inv = load_inventory(FIXTURES / "valid-minimal.toml")
        s = inv.stages.rtk_prebuilt.rtk.source
        self.assertEqual(s.type, "github-release")
        self.assertEqual(s.repository, "rtk-ai/rtk")
        self.assertEqual(s.tag, "v0.43.0")

    def test_rtk_update(self):
        inv = load_inventory(FIXTURES / "valid-minimal.toml")
        u = inv.stages.rtk_prebuilt.rtk.update
        self.assertEqual(u.provider, "github-release")
        self.assertTrue(u.stable_only)
        self.assertEqual(u.tag_prefix, "v")
        self.assertIn("linux-amd64", u.required_platforms)

    def test_fd_source(self):
        inv = load_inventory(FIXTURES / "valid-minimal.toml")
        s = inv.stages.fd_prebuilt.fd.source
        self.assertEqual(s.type, "github-release")
        self.assertEqual(s.repository, "sharkdp/fd")
        self.assertEqual(s.tag, "v10.4.2")

    def test_fd_update(self):
        inv = load_inventory(FIXTURES / "valid-minimal.toml")
        u = inv.stages.fd_prebuilt.fd.update
        self.assertEqual(u.provider, "github-release")
        self.assertTrue(u.stable_only)
        self.assertEqual(u.tag_prefix, "v")

    def test_pi_source(self):
        inv = load_inventory(FIXTURES / "valid-minimal.toml")
        s = inv.stages.pi_tools.pi.source
        self.assertEqual(s.type, "npm")
        self.assertEqual(s.package, "@earendil-works/pi-coding-agent")

    def test_pi_update(self):
        inv = load_inventory(FIXTURES / "valid-minimal.toml")
        u = inv.stages.pi_tools.pi.update
        self.assertEqual(u.provider, "npm")
        self.assertTrue(u.stable_only)

    def test_openspec_source(self):
        inv = load_inventory(FIXTURES / "valid-minimal.toml")
        s = inv.stages.openspec_tools.openspec.source
        self.assertEqual(s.type, "npm")
        self.assertEqual(s.package, "@fission-ai/openspec")

    def test_openspec_update(self):
        inv = load_inventory(FIXTURES / "valid-minimal.toml")
        u = inv.stages.openspec_tools.openspec.update
        self.assertEqual(u.provider, "npm")
        self.assertTrue(u.stable_only)

    def test_oh_my_zsh_source(self):
        inv = load_inventory(FIXTURES / "valid-minimal.toml")
        s = inv.stages.runtime.oh_my_zsh.source
        self.assertEqual(s.type, "git")
        self.assertEqual(s.repository, "https://github.com/ohmyzsh/ohmyzsh.git")

    def test_oh_my_zsh_update(self):
        inv = load_inventory(FIXTURES / "valid-minimal.toml")
        u = inv.stages.runtime.oh_my_zsh.update
        self.assertEqual(u.provider, "git-ref")
        self.assertEqual(u.ref, "master")


# ---------------------------------------------------------------------------
# Provider/source compatibility table
# ---------------------------------------------------------------------------

PROVIDER_COMPAT_TABLE = {
    "github-release":    {"github-release", "github-release"},
    "npm":               {"npm"},
    "pypi":              {"pypi"},
    "rust-channel":      {"rust-channel"},
    "docker-registry":   {"docker-registry"},
    "git":               {"git-ref"},
}


class TestProviderCompatibility(unittest.TestCase):
    """Provider must be compatible with source type."""

    # Which TOML dot-path to inject source/update overrides into for each source type
    _ENTRY_FOR_SOURCE: dict[str, str] = {
        "github-release": "build.stages.toolchain.uv",
        "npm": "build.stages.pi-tools.pi",
        "pypi": "build.stages.toolchain.ty",
        "rust-channel": "build.stages.toolchain.rust",
        "docker-registry": "build.stages.base.node",
        "git": "build.stages.runtime.oh-my-zsh",
    }

    def _load_with_compat(self, source_type: str, update_provider: str) -> object:
        """Create a TOML where the correct entry uses source_type and update_provider, then load."""
        entry = self._ENTRY_FOR_SOURCE.get(source_type, "build.stages.toolchain.uv")
        src_extra = ""
        if source_type == "github-release":
            src_extra = 'repository = "owner/repo"\ntag = "0.1.0"'
        elif source_type in ("npm", "pypi"):
            src_extra = 'package = "example"'
        elif source_type == "rust-channel":
            src_extra = 'manifest = "https://example.invalid/channel-rust-1.0.0.toml"'
        elif source_type == "docker-registry":
            src_extra = 'registry = "docker.io"\nrepository = "library/node"'
        elif source_type == "git":
            src_extra = 'repository = "https://example.invalid/repo.git"'

        upd_extra = ""
        if update_provider == "github-release":
            upd_extra = 'stable_only = true\nrequired_platforms = ["linux-amd64"]'
        elif update_provider in ("npm", "pypi"):
            upd_extra = 'stable_only = true'
        elif update_provider == "rust-channel":
            upd_extra = 'channel = "stable"\nstable_only = true'
        elif update_provider == "docker-registry":
            upd_extra = 'stable_only = true\ntrack = "tag-digest"'
        elif update_provider == "git-ref":
            upd_extra = 'ref = "master"'

        toml = _minimal_toml(
            **{
                f"{entry}.source": f'type = "{source_type}"\n{src_extra}',
                f"{entry}.update": f'provider = "{update_provider}"\n{upd_extra}',
            }
        )
        path = _write_toml(toml)
        try:
            return load_inventory(path)
        finally:
            path.unlink()

    def test_compatible_pairs(self):
        """Every source→provider pair in the table MUST load."""
        for source_type, providers in PROVIDER_COMPAT_TABLE.items():
            for provider in providers:
                with self.subTest(source=source_type, provider=provider):
                    try:
                        self._load_with_compat(source_type, provider)
                    except InventoryError as e:
                        self.fail(f"{source_type}→{provider} should be compatible: {e}")

    def test_incompatible_pairs(self):
        """Mis-matched source→provider MUST raise InventoryError."""
        incompatible = [
            ("npm", "github-release"),
            ("github-release", "npm"),
            ("docker-registry", "git-ref"),
            ("git", "docker-registry"),
            ("rust-channel", "npm"),
        ]
        for source_type, provider in incompatible:
            with self.subTest(source=source_type, provider=provider):
                with self.assertRaises(InventoryError):
                    self._load_with_compat(source_type, provider)


# ---------------------------------------------------------------------------
# Invalid fixtures — source / update metadata
# ---------------------------------------------------------------------------

class TestMissingSource(unittest.TestCase):
    """Versioned entries without [source] must be rejected."""

    def test_missing_source(self):
        with self.assertRaises(InventoryError) as ctx:
            load_inventory(FIXTURES / "missing-source.toml")
        self.assertIn("source", str(ctx.exception))


class TestMissingUpdate(unittest.TestCase):
    """Versioned entries without [update] must be rejected."""

    def test_missing_update(self):
        with self.assertRaises(InventoryError) as ctx:
            load_inventory(FIXTURES / "missing-update.toml")
        self.assertIn("update", str(ctx.exception))


class TestUnknownSourceType(unittest.TestCase):
    """Unknown source.type must be rejected."""

    def test_unknown_source_type(self):
        with self.assertRaises(InventoryError) as ctx:
            load_inventory(FIXTURES / "unknown-source-type.toml")
        self.assertIn("bitbucket-tarball", str(ctx.exception))


class TestUnknownUpdateProvider(unittest.TestCase):
    """Unknown update.provider must be rejected."""

    def test_unknown_update_provider(self):
        with self.assertRaises(InventoryError) as ctx:
            load_inventory(FIXTURES / "unknown-update-provider.toml")
        self.assertIn("apt-get", str(ctx.exception))


class TestMissingProviderField(unittest.TestCase):
    """Missing required field for a source type must be rejected."""

    def test_missing_provider_field(self):
        with self.assertRaises(InventoryError) as ctx:
            load_inventory(FIXTURES / "missing-provider-field.toml")
        self.assertIn("repository", str(ctx.exception).lower())


class TestSourceTagVersionMismatch(unittest.TestCase):
    """github-release source.tag must equal declared version."""

    def test_tag_version_mismatch(self):
        with self.assertRaises(VersionConfigError) as ctx:
            load_inventory(FIXTURES / "source-tag-version-mismatch.toml")
        self.assertIn("source.tag", str(ctx.exception))


class TestMissingRequiredPlatform(unittest.TestCase):
    """required_platforms must have corresponding artifact entries."""

    def test_required_platform_missing(self):
        with self.assertRaises(VersionConfigError) as ctx:
            load_inventory(FIXTURES / "missing-required-platform.toml")
        self.assertIn("linux-amd64", str(ctx.exception))


class TestPlaceholderSha256(unittest.TestCase):
    """All-zeros checksum (placeholder) must be rejected."""

    def test_placeholder_sha256(self):
        with self.assertRaises(InventoryError) as ctx:
            load_inventory(FIXTURES / "placeholder-sha256.toml")
        self.assertIn("placeholder", str(ctx.exception).lower())


class TestMovingRustVersion(unittest.TestCase):
    """Rust version must be explicit X.Y.Z, not 'stable'."""

    def test_moving_rust_version(self):
        with self.assertRaises(InventoryError) as ctx:
            load_inventory(FIXTURES / "moving-rust-version.toml")
        self.assertIn("stable", str(ctx.exception).lower())


# ---------------------------------------------------------------------------
# Stage 1 invalid fixtures (carried forward with source/update metadata)
# ---------------------------------------------------------------------------

class TestMissingRequiredField(unittest.TestCase):
    """Missing required fields raise InventoryError with dot path."""

    def test_missing_python_version(self):
        with self.assertRaises(InventoryError) as ctx:
            load_inventory(FIXTURES / "missing-required-field.toml")
        self.assertIn("build.stages.toolchain.python.version", str(ctx.exception))


class TestMalformedDigest(unittest.TestCase):
    """Malformed SHA-256 digest raises InventoryError."""

    def test_too_short(self):
        with self.assertRaises(InventoryError) as ctx:
            load_inventory(FIXTURES / "malformed-digest.toml")
        self.assertIn("64 lowercase hex", str(ctx.exception))

    def test_wrong_prefix(self):
        """x:<64hex> — wrong algorithm prefix."""
        with self.assertRaises(InventoryError) as ctx:
            load_inventory(FIXTURES / "wrong-digest-prefix.toml")
        self.assertIn("sha256:<64 lowercase hex>", str(ctx.exception))

    def test_no_colon(self):
        """bare 64 hex chars without sha256: prefix raises InventoryError, not IndexError."""
        toml = _minimal_toml(
            **{"base.node": 'digest = "ae91dcc111a68c9d2d81ff2a17bda61be126426176fde6fe7d08ab13b7f50573"'}
        )
        path = _write_toml(toml)
        try:
            with self.assertRaises(InventoryError) as ctx:
                load_inventory(path)
            self.assertIn("missing colon", str(ctx.exception))
        finally:
            path.unlink()


class TestInconsistentUrl(unittest.TestCase):
    """URL not containing the declared version raises InventoryError."""

    def test_url_diverges_from_version(self):
        with self.assertRaises(InventoryError) as ctx:
            load_inventory(FIXTURES / "inconsistent-url.toml")
        self.assertIn("build.stages.toolchain.uv.artifacts.linux-amd64.url", str(ctx.exception))


class TestRustupBadUrl(unittest.TestCase):
    """Non-https rustup artifact URL raises InventoryError."""

    def test_rustup_url_not_admissible(self):
        with self.assertRaises(InventoryError) as ctx:
            load_inventory(FIXTURES / "rustup-bad-url.toml")
        self.assertIn("build.stages.toolchain.rust.rustup.artifacts.linux-amd64.url", str(ctx.exception))

    def test_rustup_url_no_hostname(self):
        """URL like https:///rustup-init (no hostname) is rejected."""
        with self.assertRaises(InventoryError) as ctx:
            load_inventory(FIXTURES / "rustup-no-host.toml")
        self.assertIn("hostname", str(ctx.exception))

    def test_rustup_url_no_path(self):
        """URL like https://example.com (no path) is rejected."""
        with self.assertRaises(InventoryError) as ctx:
            load_inventory(FIXTURES / "rustup-no-path.toml")
        self.assertIn("path", str(ctx.exception))


class TestUnsupportedPlatform(unittest.TestCase):
    """Missing linux-amd64 artifact raises InventoryError."""

    def test_no_linux_amd64(self):
        with self.assertRaises(InventoryError) as ctx:
            load_inventory(FIXTURES / "unsupported-platform.toml")
        self.assertIn("linux-amd64", str(ctx.exception))


class TestInvalidConstraint(unittest.TestCase):
    """Invalid constraint raises error."""

    def test_prerelease_in_numeric_scheme(self):
        with self.assertRaises(VersionConfigError):
            load_inventory(FIXTURES / "invalid-constraint.toml")


class TestContradictoryConstraint(unittest.TestCase):
    """Contradictory constraint raises error."""

    def test_contradictory(self):
        with self.assertRaises(VersionConfigError):
            load_inventory(FIXTURES / "contradictory-constraint.toml")


# ---------------------------------------------------------------------------
# Additional invalid cases — inline generated TOML
# ---------------------------------------------------------------------------

class TestAdditionalInvalidCases(unittest.TestCase):
    """Generated invalid TOML cases that don't need separate fixture files."""

    def test_no_schema(self):
        toml = _minimal_toml().replace("schema = 1", "", 1)
        path = _write_toml(toml)
        try:
            with self.assertRaises(InventoryError):
                load_inventory(path)
        finally:
            path.unlink()

    def test_sha256_non_hex(self):
        toml = _minimal_toml(
            **{"base.node": 'digest = "sha256:ae91dcc111a68c9d2d81ff2a17bda61be126426176fde6fe7d08ab13b7f5057g"'}
        )
        path = _write_toml(toml)
        try:
            with self.assertRaises(InventoryError):
                load_inventory(path)
        finally:
            path.unlink()

    def test_exact_version_fails_own_policy(self):
        toml = _minimal_toml(
            **{
                "build.stages.toolchain.python": """\
version = "3.14.5"
[build.stages.toolchain.python.override]
constraint = ">=3.14.6"
allow_prerelease = false
scheme = "numeric"
"""
            }
        )
        path = _write_toml(toml)
        try:
            with self.assertRaises(VersionConfigError):
                load_inventory(path)
        finally:
            path.unlink()

    def test_allow_prerelease_with_numeric_scheme(self):
        toml = _minimal_toml(
            **{
                "build.stages.toolchain.python": """\
version = "3.14.6"
[build.stages.toolchain.python.override]
constraint = ">=3.14.6"
allow_prerelease = true
scheme = "numeric"
"""
            }
        )
        path = _write_toml(toml)
        try:
            with self.assertRaises(InventoryError):
                load_inventory(path)
        finally:
            path.unlink()

    def test_unknown_scheme(self):
        toml = _minimal_toml(
            **{
                "build.stages.toolchain.python": """\
version = "3.14.6"
[build.stages.toolchain.python.override]
constraint = ">=3.14.6"
allow_prerelease = false
scheme = "semver"
"""
            }
        )
        path = _write_toml(toml)
        try:
            with self.assertRaises(InventoryError):
                load_inventory(path)
        finally:
            path.unlink()

    def test_range_instead_of_exact(self):
        toml = _minimal_toml(
            **{
                "build.stages.toolchain.python": 'version = ">=3.14.6"'
            }
        )
        path = _write_toml(toml)
        try:
            with self.assertRaises(VersionConfigError):
                load_inventory(path)
        finally:
            path.unlink()

    # ------------------------------------------------------------------
    # Cache config validation
    # ------------------------------------------------------------------

    def test_no_cache_section_yields_none(self):
        """Without [cache], inventory.cache is None."""
        inv = load_inventory(FIXTURES / "valid-minimal.toml")
        self.assertIsNone(inv.cache)

    def test_cache_with_dir_and_ttl(self):
        toml = _minimal_toml() + '\n[cache]\ndir = "/tmp/my-cache"\nttl = 7200\n'
        path = _write_toml(toml)
        try:
            inv = load_inventory(path)
            self.assertIsNotNone(inv.cache)
            self.assertEqual(inv.cache.dir, "/tmp/my-cache")  # type: ignore[union-attr]
            self.assertEqual(inv.cache.ttl, 7200)  # type: ignore[union-attr]
        finally:
            path.unlink()

    def test_cache_dir_must_be_string(self):
        toml = _minimal_toml() + '\n[cache]\ndir = 42\n'
        path = _write_toml(toml)
        try:
            with self.assertRaises(InventoryError) as ctx:
                load_inventory(path)
            self.assertIn("cache.dir", str(ctx.exception))
        finally:
            path.unlink()

    def test_cache_ttl_must_be_positive_int(self):
        toml = _minimal_toml() + '\n[cache]\nttl = 0\n'
        path = _write_toml(toml)
        try:
            with self.assertRaises(InventoryError) as ctx:
                load_inventory(path)
            self.assertIn("cache.ttl", str(ctx.exception))
        finally:
            path.unlink()

    def test_cache_rejects_unknown_key(self):
        toml = _minimal_toml() + '\n[cache]\nunknown = true\n'
        path = _write_toml(toml)
        try:
            with self.assertRaises(InventoryError) as ctx:
                load_inventory(path)
            self.assertIn("unknown", str(ctx.exception))
        finally:
            path.unlink()


if __name__ == "__main__":
    unittest.main()
