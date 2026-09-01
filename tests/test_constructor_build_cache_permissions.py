"""RED — host-owner-private build-cache permission contracts.

Phase 1 (``materialize-build-artifacts-on-host``) proves that published
verified build blobs are exactly ``0444``, that ordinary mutation attempts
fail, that the invoking host owner can read state beneath a ``0700``
checkout parent while a differing UID cannot traverse it, and that path
preparation never repairs checkout, ancestor, home, or unrelated cache
permissions.

These tests are expected to FAIL while no build-cache boundary exists.
"""

from __future__ import annotations

import base64
import hashlib
import os
import stat
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock


def _build_cache_module():
    from docker.versioning import build_cache

    return build_cache


def _identity_module():
    from docker.versioning import digest_identity

    return digest_identity


def _mode(path: Path) -> int:
    return stat.S_IMODE(os.stat(path).st_mode)


def _fd_path(fd: int) -> str | None:
    """Return the normalized path an open descriptor refers to, or ``None``."""
    try:
        return os.path.normpath(os.readlink(f"/proc/self/fd/{fd}"))
    except OSError:
        return None


def _foreign_uid_fstat(target: Path, foreign_uid: int):
    """Build an ``os.fstat`` fake that reports *foreign_uid* for *target*."""
    real_fstat = os.fstat
    target_norm = os.path.normpath(str(target))

    def fake_fstat(fd, *args, **kwargs):
        st = real_fstat(fd, *args, **kwargs)
        if _fd_path(fd) == target_norm:
            return types.SimpleNamespace(
                st_mode=st.st_mode, st_uid=foreign_uid, st_gid=st.st_gid
            )
        return st

    return fake_fstat


class _PermissionTestCase(unittest.TestCase):
    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory(prefix="build-cache-perm-")
        self.addCleanup(tmp.cleanup)
        self.base = Path(tmp.name)

    def _publish(self, data: bytes, checkout: Path | None = None) -> Path:
        mod = _build_cache_module()
        identity_mod = _identity_module()
        checkout = checkout or (self.base / "checkout")
        checkout.mkdir(parents=True, exist_ok=True)
        identity = identity_mod.DigestIdentity.from_hex(
            "sha256", hashlib.sha256(data).hexdigest(),
        )
        return mod.publish_verified_blob(identity, data, checkout_root=checkout)


class TestPublishedBlobMode(_PermissionTestCase):
    """Published verified blobs are exactly ``0444`` and unwritable."""

    def test_published_blob_is_exactly_0444(self) -> None:
        path = self._publish(b"verified-blob-bytes")
        self.assertEqual(_mode(path), 0o444)

    def test_owner_ordinary_write_fails(self) -> None:
        path = self._publish(b"immutable-blob")
        with self.assertRaises(PermissionError):
            os.open(path, os.O_WRONLY)

    def test_group_and_other_have_no_write_bits(self) -> None:
        path = self._publish(b"no-group-other-write")
        self.assertEqual(_mode(path) & 0o022, 0)

    def test_owner_ordinary_truncation_fails(self) -> None:
        path = self._publish(b"truncation-target")
        with self.assertRaises(PermissionError):
            open(path, "w").close()

    def test_mismatched_payload_is_never_published(self) -> None:
        mod = _build_cache_module()
        identity_mod = _identity_module()
        checkout = self.base / "checkout"
        checkout.mkdir()
        identity = identity_mod.DigestIdentity.from_hex(
            "sha256", hashlib.sha256(b"expected").hexdigest(),
        )
        with self.assertRaises(mod.BuildCacheError):
            mod.publish_verified_blob(identity, b"wrong-bytes", checkout_root=checkout)
        self.assertFalse(
            (checkout / ".docker-cache" / "build-artifacts" / "blobs").exists(),
        )


class TestDescriptorRelativeRevalidation(_PermissionTestCase):
    """Published blobs are re-opened through no-follow stable descriptors."""

    def _identity_and_paths(self, data: bytes):
        mod = _build_cache_module()
        identity = _identity_module().DigestIdentity.from_hex(
            "sha256", hashlib.sha256(data).hexdigest(),
        )
        checkout = self.base / "checkout"
        checkout.mkdir()
        paths = mod.prepare_build_cache(checkout)
        return mod, identity, paths

    def test_rejects_blob_replaced_with_symlink_before_revalidation(self) -> None:
        data = b"verified"
        mod, identity, paths = self._identity_and_paths(data)
        blob = mod.publish_verified_blob(identity, data, checkout_root=paths.checkout_root)
        target = self.base / "outside"
        target.write_bytes(data)
        blob.unlink()
        blob.symlink_to(target)

        with self.assertRaises(mod.BuildCacheError):
            mod._verify_published_blob(identity, paths)

    def test_race_replacement_never_follows_symlink(self) -> None:
        data = b"verified"
        mod, identity, paths = self._identity_and_paths(data)
        blob = mod.publish_verified_blob(identity, data, checkout_root=paths.checkout_root)
        target = self.base / "outside"
        target.write_bytes(data)
        real_open = os.open
        replaced = False

        def replace_before_blob_open(name, flags, *args, **kwargs):
            nonlocal replaced
            if name == blob.name and not replaced:
                replaced = True
                blob.unlink()
                blob.symlink_to(target)
            return real_open(name, flags, *args, **kwargs)

        with mock.patch("os.open", side_effect=replace_before_blob_open):
            with self.assertRaises(mod.BuildCacheError):
                mod._verify_published_blob(identity, paths)
        self.assertTrue(replaced)

    def test_rejects_symlinked_algorithm_directory(self) -> None:
        data = b"verified"
        mod, identity, paths = self._identity_and_paths(data)
        blob = mod.publish_verified_blob(identity, data, checkout_root=paths.checkout_root)
        algorithm = blob.parent
        relocated = algorithm.with_name("sha256-real")
        algorithm.rename(relocated)
        algorithm.symlink_to(relocated, target_is_directory=True)

        with self.assertRaises(mod.BuildCacheError):
            mod._verify_published_blob(identity, paths)

    def test_rejects_foreign_owned_algorithm_directory_and_blob(self) -> None:
        data = b"verified"
        mod, identity, paths = self._identity_and_paths(data)
        blob = mod.publish_verified_blob(identity, data, checkout_root=paths.checkout_root)
        foreign_uid = os.geteuid() + 1

        with mock.patch("os.fstat", _foreign_uid_fstat(blob.parent, foreign_uid)):
            with self.assertRaises(mod.BuildCacheError):
                mod._verify_published_blob(identity, paths)
        with mock.patch("os.fstat", _foreign_uid_fstat(blob, foreign_uid)):
            with self.assertRaises(mod.BuildCacheError):
                mod._verify_published_blob(identity, paths)


class TestHostOwnerTraversal(_PermissionTestCase):
    """The invoking host owner can read cache state beneath a ``0700`` parent."""

    def test_host_owner_reads_beneath_0700_checkout_parent(self) -> None:
        parent = self.base / "private-parent"
        parent.mkdir()
        os.chmod(parent, 0o700)
        checkout = parent / "checkout"
        checkout.mkdir()
        os.chmod(checkout, 0o700)

        data = b"host-owner-can-read"
        path = self._publish(data, checkout=checkout)

        self.assertEqual(path.read_bytes(), data)

    def test_validate_host_owner_traversal_accepts_0700_ancestor(self) -> None:
        mod = _build_cache_module()
        parent = self.base / "private-parent"
        parent.mkdir()
        os.chmod(parent, 0o700)
        checkout = parent / "checkout"
        checkout.mkdir()
        os.chmod(checkout, 0o700)

        # Must not raise.
        mod.validate_host_owner_traversal(checkout)

    def test_inaccessible_ancestor_fails_without_repair(self) -> None:
        mod = _build_cache_module()
        parent = self.base / "blocked-parent"
        parent.mkdir()
        checkout = parent / "checkout"
        checkout.mkdir()
        os.chmod(parent, 0o000)
        self.addCleanup(os.chmod, parent, 0o700)

        with self.assertRaises(mod.BuildCacheError) as raised:
            mod.prepare_build_cache(checkout)

        self.assertIn(str(parent), str(raised.exception))
        # Strict no-repair: the inaccessible ancestor mode is unchanged.
        self.assertEqual(_mode(parent), 0o000)
        self.assertFalse((checkout / ".docker-cache").exists())


class TestDifferingUidDenial(_PermissionTestCase):
    """A differing UID cannot traverse host build-cache paths."""

    def test_constructor_dirs_are_owner_only(self) -> None:
        mod = _build_cache_module()
        checkout = self.base / "checkout"
        checkout.mkdir()
        paths = mod.prepare_build_cache(checkout)
        for path in (paths.persistent_root, paths.blobs_root, paths.tmp_root, paths.generated_root):
            self.assertEqual(_mode(path), 0o700)
            self.assertEqual(_mode(path) & 0o077, 0)

    def test_foreign_owned_cache_dir_rejected(self) -> None:
        mod = _build_cache_module()
        checkout = self.base / "checkout"
        checkout.mkdir()
        cache_dir = checkout / ".docker-cache"
        cache_dir.mkdir()

        with mock.patch("os.fstat", _foreign_uid_fstat(cache_dir, os.geteuid() + 1)):
            with self.assertRaises(mod.BuildCacheError):
                mod.prepare_build_cache(checkout)

    def test_foreign_owned_generated_root_rejected(self) -> None:
        mod = _build_cache_module()
        checkout = self.base / "checkout"
        checkout.mkdir()
        generated = checkout / ".docker-generated" / "build-artifacts"
        generated.mkdir(parents=True)

        with mock.patch("os.fstat", _foreign_uid_fstat(generated, os.geteuid() + 1)):
            with self.assertRaises(mod.BuildCacheError):
                mod.prepare_build_cache(checkout)


class TestUmaskIndependence(_PermissionTestCase):
    """Modes are explicit, never derived from the ambient umask."""

    def test_prepare_and_publish_are_umask_independent(self) -> None:
        mod = _build_cache_module()
        identity_mod = _identity_module()
        checkout = self.base / "checkout"
        checkout.mkdir()

        old = os.umask(0o777)
        self.addCleanup(os.umask, old)

        paths = mod.prepare_build_cache(checkout)
        for path in (paths.persistent_root, paths.blobs_root, paths.tmp_root, paths.generated_root):
            self.assertEqual(_mode(path), 0o700, f"{path} must be 0700 regardless of umask")

        identity = identity_mod.DigestIdentity.from_hex(
            "sha256", hashlib.sha256(b"umask-proof").hexdigest(),
        )
        blob = mod.publish_verified_blob(
            identity, b"umask-proof", checkout_root=checkout,
        )
        self.assertEqual(_mode(blob), 0o444)


class TestAncestorModesUnchanged(_PermissionTestCase):
    """Path preparation never repairs checkout, parent, home, or other caches."""

    def test_preparation_leaves_ancestor_modes_unchanged(self) -> None:
        mod = _build_cache_module()
        home = self.base / "home"
        home.mkdir()
        os.chmod(home, 0o755)
        parent = home / "parent"
        parent.mkdir()
        os.chmod(parent, 0o700)
        checkout = parent / "checkout"
        checkout.mkdir()
        os.chmod(checkout, 0o755)
        unrelated = home / "unrelated-cache"
        unrelated.mkdir()
        os.chmod(unrelated, 0o755)

        before = {
            "home": _mode(home),
            "parent": _mode(parent),
            "checkout": _mode(checkout),
            "unrelated": _mode(unrelated),
        }
        mod.prepare_build_cache(checkout)
        mod.publish_verified_blob(
            _identity_module().DigestIdentity.from_hex(
                "sha256", hashlib.sha256(b"x").hexdigest(),
            ),
            b"x",
            checkout_root=checkout,
        )

        self.assertEqual(_mode(home), before["home"])
        self.assertEqual(_mode(parent), before["parent"])
        self.assertEqual(_mode(checkout), before["checkout"])
        self.assertEqual(_mode(unrelated), before["unrelated"])

    def test_existing_generated_parent_mode_unchanged(self) -> None:
        mod = _build_cache_module()
        checkout = self.base / "checkout"
        checkout.mkdir()
        generated_parent = checkout / ".docker-generated"
        generated_parent.mkdir()
        os.chmod(generated_parent, 0o755)

        mod.prepare_build_cache(checkout)

        self.assertEqual(_mode(generated_parent), 0o755)
        self.assertEqual(
            _mode(generated_parent / "build-artifacts"), 0o700,
        )


if __name__ == "__main__":
    unittest.main()
