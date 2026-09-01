"""RED — fixed checkout-local build-cache path contracts.

Phase 1 (``materialize-build-artifacts-on-host``) keeps persistent build
blobs beneath a fixed ignored checkout path (``.docker-cache``) and
per-build transaction snapshots beneath checkout-local generated state
(``.docker-generated``).  These paths are never configurable and never use
the shared XDG constructor cache.

These tests are expected to FAIL while no build-cache path module exists.
"""

from __future__ import annotations

import inspect
import os
import stat
import tempfile
import unittest
from pathlib import Path
from unittest import mock


def _build_cache_module():
    from docker.versioning import build_cache

    return build_cache


def _mode(path: Path) -> int:
    return stat.S_IMODE(os.stat(path).st_mode)


class _PathTestCase(unittest.TestCase):
    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory(prefix="build-cache-path-")
        self.addCleanup(tmp.cleanup)
        self.base = Path(tmp.name)
        self.checkout = self.base / "checkout"
        self.checkout.mkdir()


class TestFixedCheckoutLocalRoots(_PathTestCase):
    """Persistent and generated roots are fixed beneath the checkout."""

    def test_persistent_root_is_fixed_ignored_checkout_path(self) -> None:
        mod = _build_cache_module()
        self.assertEqual(
            mod.resolve_build_cache_root(self.checkout),
            self.checkout / ".docker-cache" / "build-artifacts",
        )

    def test_blobs_and_tmp_are_beneath_persistent_root(self) -> None:
        mod = _build_cache_module()
        persistent = mod.resolve_build_cache_root(self.checkout)
        self.assertEqual(mod.resolve_build_blobs_root(self.checkout), persistent / "blobs")
        self.assertEqual(mod.resolve_build_tmp_root(self.checkout), persistent / "tmp")

    def test_generated_root_is_checkout_local(self) -> None:
        mod = _build_cache_module()
        self.assertEqual(
            mod.resolve_build_generated_root(self.checkout),
            self.checkout / ".docker-generated" / "build-artifacts",
        )

    def test_resolution_is_lexical_and_deterministic(self) -> None:
        mod = _build_cache_module()
        first = mod.resolve_build_cache_root(self.checkout)
        second = mod.resolve_build_cache_root(self.checkout)
        self.assertEqual(first, second)


class TestProhibitedConfigurableOrSharedRoots(_PathTestCase):
    """Build cache paths have no configurable or shared-XDG alternative."""

    def test_resolution_has_no_cache_dir_override_parameter(self) -> None:
        mod = _build_cache_module()
        for function in (
            mod.resolve_build_cache_root,
            mod.resolve_build_blobs_root,
            mod.resolve_build_tmp_root,
            mod.resolve_build_generated_root,
            mod.prepare_build_cache,
        ):
            parameters = list(inspect.signature(function).parameters)
            self.assertEqual(
                parameters,
                ["checkout_root"],
                f"{function.__name__} must accept only checkout_root",
            )

    def test_shared_xdg_cache_home_is_ignored(self) -> None:
        mod = _build_cache_module()
        with mock.patch.dict(os.environ, {"XDG_CACHE_HOME": str(self.base / "xdg")}):
            root = mod.resolve_build_cache_root(self.checkout)
        self.assertEqual(
            root, self.checkout / ".docker-cache" / "build-artifacts",
        )

    def test_local_cache_dir_is_ignored(self) -> None:
        mod = _build_cache_module()
        local = self.base / "local-cache"
        local.mkdir()
        with mock.patch.dict(os.environ, {"XDG_CACHE_HOME": str(self.base / "xdg")}):
            # A local override would live under [cache].dir; build paths
            # have no such input, so resolution cannot drift toward it.
            root = mod.resolve_build_blobs_root(self.checkout)
        self.assertTrue(
            str(root).startswith(str(self.checkout)),
            "build blobs must stay inside the checkout",
        )


class TestContainment(_PathTestCase):
    """Derived blob paths never escape the checkout-local blobs root."""

    def test_blob_path_is_beneath_blobs_root(self) -> None:
        mod = _build_cache_module()
        identity_module = __import__(
            "docker.versioning.digest_identity", fromlist=["DigestIdentity"]
        )
        import hashlib

        identity = identity_module.DigestIdentity.from_hex(
            "sha256", hashlib.sha256(b"blob").hexdigest(),
        )
        blobs = mod.resolve_build_blobs_root(self.checkout)
        path = mod.build_blob_path(blobs, identity)
        self.assertEqual(path.parent, blobs / "sha256")
        self.assertTrue(str(path).startswith(str(blobs) + os.sep))

    def test_blob_path_never_contains_traversal(self) -> None:
        mod = _build_cache_module()
        identity_module = __import__(
            "docker.versioning.digest_identity", fromlist=["DigestIdentity"]
        )
        import hashlib

        identity = identity_module.DigestIdentity.from_hex(
            "sha256", hashlib.sha256(b"blob").hexdigest(),
        )
        path = mod.build_blob_path(self.checkout / "root", identity)
        self.assertNotIn("..", path.parts)


class TestSymlinkAndTypeRejection(_PathTestCase):
    """Unsafe cache/generated paths are rejected before mutation."""

    def test_symlinked_docker_cache_rejected_before_mutation(self) -> None:
        mod = _build_cache_module()
        outside = self.base / "outside-cache"
        outside.mkdir()
        (self.checkout / ".docker-cache").symlink_to(outside, target_is_directory=True)

        with self.assertRaises(mod.BuildCacheError):
            mod.prepare_build_cache(self.checkout)

        # No mutation beneath the symlink target or elsewhere.
        self.assertEqual(list(outside.iterdir()), [])
        self.assertFalse((self.checkout / ".docker-generated" / "build-artifacts").exists())

    def test_non_directory_docker_cache_rejected(self) -> None:
        mod = _build_cache_module()
        (self.checkout / ".docker-cache").write_text("not a directory")

        with self.assertRaises(mod.BuildCacheError):
            mod.prepare_build_cache(self.checkout)

        self.assertFalse((self.checkout / ".docker-generated" / "build-artifacts").exists())

    def test_symlinked_blobs_rejected(self) -> None:
        mod = _build_cache_module()
        outside = self.base / "outside-blobs"
        outside.mkdir()
        blobs = self.checkout / ".docker-cache" / "build-artifacts" / "blobs"
        blobs.parent.mkdir(parents=True)
        blobs.symlink_to(outside, target_is_directory=True)

        with self.assertRaises(mod.BuildCacheError):
            mod.prepare_build_cache(self.checkout)

        self.assertEqual(list(outside.iterdir()), [])

    def test_symlinked_generated_root_rejected(self) -> None:
        mod = _build_cache_module()
        outside = self.base / "outside-generated"
        outside.mkdir()
        generated_parent = self.checkout / ".docker-generated"
        generated_parent.mkdir()
        (generated_parent / "build-artifacts").symlink_to(
            outside, target_is_directory=True,
        )

        with self.assertRaises(mod.BuildCacheError):
            mod.prepare_build_cache(self.checkout)

        self.assertEqual(list(outside.iterdir()), [])


class TestPrepareCreatesPrivateRoots(_PathTestCase):
    """Preparation creates constructor-owned private subtrees."""

    def test_prepare_creates_private_roots(self) -> None:
        mod = _build_cache_module()
        paths = mod.prepare_build_cache(self.checkout)

        for path in (paths.persistent_root, paths.blobs_root, paths.tmp_root, paths.generated_root):
            self.assertTrue(path.is_dir(), f"{path} must be a directory")
            self.assertEqual(_mode(path), 0o700, f"{path} must be 0700")

        self.assertEqual(_mode(self.checkout / ".docker-cache"), 0o700)

    def test_prepare_returns_paths_matching_resolution(self) -> None:
        mod = _build_cache_module()
        paths = mod.prepare_build_cache(self.checkout)
        self.assertEqual(paths.persistent_root, mod.resolve_build_cache_root(self.checkout))
        self.assertEqual(paths.blobs_root, mod.resolve_build_blobs_root(self.checkout))
        self.assertEqual(paths.tmp_root, mod.resolve_build_tmp_root(self.checkout))
        self.assertEqual(paths.generated_root, mod.resolve_build_generated_root(self.checkout))


class TestIgnoreRules(unittest.TestCase):
    """The persistent checkout-local cache is ignored by git."""

    def test_persistent_cache_directory_is_gitignored(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]
        gitignore = (repo_root / ".gitignore").read_text(encoding="utf-8")
        self.assertRegex(
            gitignore,
            r"(?m)^\.docker-cache/$\n",
            ".docker-cache/ must be an ignored checkout-local cache path",
        )

    def test_generated_directory_remains_gitignored(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]
        gitignore = (repo_root / ".gitignore").read_text(encoding="utf-8")
        self.assertRegex(
            gitignore,
            r"(?m)^\.docker-generated/$\n",
            ".docker-generated/ must remain ignored",
        )


if __name__ == "__main__":
    unittest.main()
