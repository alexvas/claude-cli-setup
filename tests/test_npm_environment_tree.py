"""Phase 2 — canonical hashed tree manifest and no-follow verification
(tasks 2.2 and 2.3).

``build_tree_manifest`` deterministically describes files, directories, and
contained symlinks beneath a tree root in path order and hashes every
regular file.  ``verify_tree`` re-validates a manifest against the live
filesystem without following symlinks and detects every corruption class:
type, hash, permission, ownership, ordering, extra, missing, and escape.
Neither primitive assumes a published output identity or an
assembler-evidence digest.
"""

from __future__ import annotations

import dataclasses
import hashlib
import os
import stat
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

from docker.npm_environment import LockedNpmError
from docker.npm_environment import tree as tree_module
from docker.npm_environment.tree import TreeEntry, TreeManifest


def _mode(path: Path) -> int:
    return stat.S_IMODE(os.stat(path).st_mode)


def _fd_path(fd: int) -> str | None:
    try:
        return os.path.normpath(os.readlink(f"/proc/self/fd/{fd}"))
    except OSError:
        return None


def _foreign_uid_fstat(target: Path, foreign_uid: int):
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


class _TreeTestCase(unittest.TestCase):
    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory(prefix="npm-env-tree-")
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name) / "tree"
        self.root.mkdir()

    def _build(self, *, owner_safe: bool = True) -> TreeManifest:
        return tree_module.build_tree_manifest(self.root)


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class TestCanonicalTreeManifest(_TreeTestCase):
    """2.2 — canonical tree generation."""

    def test_describes_files_directories_and_symlinks_in_path_order(self):
        (self.root / "z.txt").write_text("z")
        (self.root / "a").mkdir()
        (self.root / "a" / "inner.txt").write_text("inner")
        (self.root / "m").mkdir()
        (self.root / "m" / "link").symlink_to("../a/inner.txt")

        manifest = self._build()
        paths = [e.path for e in manifest.entries]
        self.assertEqual(paths, sorted(paths))
        self.assertEqual(
            paths,
            ["a", "a/inner.txt", "m", "m/link", "z.txt"],
        )
        by_path = {e.path: e for e in manifest.entries}
        self.assertEqual(by_path["a"].kind, "directory")
        self.assertEqual(by_path["a"].digest, "")
        self.assertEqual(by_path["a/inner.txt"].kind, "file")
        self.assertEqual(by_path["a/inner.txt"].digest, _sha256(b"inner"))
        self.assertEqual(by_path["z.txt"].digest, _sha256(b"z"))
        self.assertEqual(by_path["m/link"].kind, "symlink")
        self.assertEqual(by_path["m/link"].target, "../a/inner.txt")
        self.assertEqual(by_path["m/link"].digest, "")

    def test_file_hashes_are_deterministic(self):
        (self.root / "f").write_bytes(b"\x00\x01\x02")
        first = self._build()
        second = self._build()
        self.assertEqual(first.digest, second.digest)
        self.assertEqual(first.entries, second.entries)

    def test_contained_relative_symlink_accepted(self):
        (self.root / "sub").mkdir()
        (self.root / "sub" / "target.txt").write_text("t")
        (self.root / "sub" / "up").symlink_to("../sub/target.txt")
        manifest = self._build()
        link = next(e for e in manifest.entries if e.path == "sub/up")
        self.assertEqual(link.target, "../sub/target.txt")

    def test_records_mode_and_ownership(self):
        path = self.root / "f"
        path.write_text("x")
        os.chmod(path, 0o640)
        manifest = self._build()
        entry = next(e for e in manifest.entries if e.path == "f")
        self.assertEqual(entry.mode, 0o640)
        self.assertEqual(entry.uid, os.geteuid())
        self.assertEqual(entry.gid, os.stat(path).st_gid)

    def test_empty_directory_manifest(self):
        manifest = self._build()
        self.assertEqual(manifest.entries, ())
        self.assertEqual(manifest.digest, tree_module.canonical_tree_digest(()))

    def test_digest_is_order_independent_and_content_only(self):
        (self.root / "a").write_text("a")
        (self.root / "b").write_text("b")
        manifest = self._build()
        reordered = dataclasses.replace(
            manifest, entries=tuple(reversed(manifest.entries))
        )
        # Canonical digest is computed over sorted content fields, so a
        # reordered entry tuple yields the same canonical digest.
        self.assertEqual(
            tree_module.canonical_tree_digest(reordered.entries),
            manifest.digest,
        )

    def test_content_change_changes_digest(self):
        (self.root / "f").write_text("one")
        first = self._build()
        (self.root / "f").write_text("two")
        second = self._build()
        self.assertNotEqual(first.digest, second.digest)


class TestCanonicalTreeRejects(_TreeTestCase):
    """2.2 — special files and escaping symlinks are rejected at build."""

    def test_special_file_rejected(self):
        fifo = self.root / "pipe"
        os.mkfifo(fifo)
        with self.assertRaises(LockedNpmError) as ctx:
            self._build()
        self.assertEqual(ctx.exception.reason, "unsupported_entry_type")

    def test_escaping_symlink_rejected(self):
        (self.root / "link").symlink_to("../outside")
        with self.assertRaises(LockedNpmError) as ctx:
            self._build()
        self.assertEqual(ctx.exception.reason, "unsafe_symlink_target")

    def test_absolute_symlink_rejected(self):
        (self.root / "link").symlink_to("/etc/passwd")
        with self.assertRaises(LockedNpmError) as ctx:
            self._build()
        self.assertEqual(ctx.exception.reason, "unsafe_symlink_target")

    def test_symlinked_root_rejected(self):
        real = self.root.parent / "real"
        real.mkdir()
        link = self.root.parent / "tree-link"
        link.symlink_to(real, target_is_directory=True)
        with self.assertRaises(LockedNpmError) as ctx:
            tree_module.build_tree_manifest(link)
        self.assertEqual(ctx.exception.reason, "unsafe_cache_path")


class TestNoFollowVerifier(_TreeTestCase):
    """2.3 — complete no-follow manifest/filesystem revalidation."""

    def _tree(self):
        (self.root / "file.txt").write_text("payload")
        (self.root / "dir").mkdir()
        (self.root / "dir" / "nested.txt").write_text("nested")
        (self.root / "dir" / "self").symlink_to("nested.txt")
        return tree_module.build_tree_manifest(self.root)

    def test_valid_tree_verifies(self):
        manifest = self._tree()
        tree_module.verify_tree(self.root, manifest)

    def test_extra_file_detected(self):
        manifest = self._tree()
        (self.root / "extra.txt").write_text("sneaky")
        with self.assertRaises(LockedNpmError) as ctx:
            tree_module.verify_tree(self.root, manifest)
        self.assertEqual(ctx.exception.reason, "tree_extra_entry")

    def test_extra_directory_detected(self):
        manifest = self._tree()
        (self.root / "extra-dir").mkdir()
        with self.assertRaises(LockedNpmError) as ctx:
            tree_module.verify_tree(self.root, manifest)
        self.assertEqual(ctx.exception.reason, "tree_extra_entry")

    def test_missing_file_detected(self):
        manifest = self._tree()
        (self.root / "file.txt").unlink()
        with self.assertRaises(LockedNpmError) as ctx:
            tree_module.verify_tree(self.root, manifest)
        self.assertEqual(ctx.exception.reason, "tree_missing_entry")

    def test_missing_directory_detected(self):
        manifest = self._tree()
        (self.root / "dir" / "nested.txt").unlink()
        (self.root / "dir" / "self").unlink()
        (self.root / "dir").rmdir()
        with self.assertRaises(LockedNpmError) as ctx:
            tree_module.verify_tree(self.root, manifest)
        self.assertEqual(ctx.exception.reason, "tree_missing_entry")

    def test_type_corruption_file_to_symlink(self):
        manifest = self._tree()
        (self.root / "file.txt").unlink()
        (self.root / "file.txt").symlink_to("dir/nested.txt")
        with self.assertRaises(LockedNpmError) as ctx:
            tree_module.verify_tree(self.root, manifest)
        self.assertEqual(ctx.exception.reason, "tree_type_mismatch")

    def test_type_corruption_directory_to_file(self):
        manifest = self._tree()
        (self.root / "dir" / "nested.txt").unlink()
        (self.root / "dir" / "self").unlink()
        (self.root / "dir").rmdir()
        (self.root / "dir").write_text("was a directory")
        with self.assertRaises(LockedNpmError) as ctx:
            tree_module.verify_tree(self.root, manifest)
        self.assertEqual(ctx.exception.reason, "tree_type_mismatch")

    def test_type_corruption_file_to_special(self):
        manifest = self._tree()
        (self.root / "file.txt").unlink()
        os.mkfifo(self.root / "file.txt")
        with self.assertRaises(LockedNpmError) as ctx:
            tree_module.verify_tree(self.root, manifest)
        self.assertEqual(ctx.exception.reason, "tree_type_mismatch")

    def test_hash_corruption_detected(self):
        manifest = self._tree()
        (self.root / "file.txt").write_text("tampered")
        with self.assertRaises(LockedNpmError) as ctx:
            tree_module.verify_tree(self.root, manifest)
        self.assertEqual(ctx.exception.reason, "tree_hash_mismatch")

    def test_permission_corruption_detected(self):
        manifest = self._tree()
        os.chmod(self.root / "file.txt", 0o600)
        with self.assertRaises(LockedNpmError) as ctx:
            tree_module.verify_tree(self.root, manifest)
        self.assertEqual(ctx.exception.reason, "tree_permission_mismatch")

    def test_ownership_corruption_detected(self):
        manifest = self._tree()
        foreign_uid = os.getuid() + 1
        target = self.root / "file.txt"
        with mock.patch(
            "os.fstat", side_effect=_foreign_uid_fstat(target, foreign_uid)
        ):
            with self.assertRaises(LockedNpmError) as ctx:
                tree_module.verify_tree(self.root, manifest)
        self.assertEqual(ctx.exception.reason, "tree_ownership_mismatch")

    def test_symlink_target_corruption_detected(self):
        manifest = self._tree()
        (self.root / "dir" / "self").unlink()
        (self.root / "dir" / "self").symlink_to("nested.txt.other")
        with self.assertRaises(LockedNpmError) as ctx:
            tree_module.verify_tree(self.root, manifest)
        self.assertEqual(ctx.exception.reason, "tree_symlink_target_mismatch")

    def test_symlink_escape_corruption_detected(self):
        manifest = self._tree()
        (self.root / "dir" / "self").unlink()
        (self.root / "dir" / "self").symlink_to("../../outside")
        with self.assertRaises(LockedNpmError) as ctx:
            tree_module.verify_tree(self.root, manifest)
        self.assertEqual(ctx.exception.reason, "tree_symlink_escape")

    def test_manifest_order_corruption_detected(self):
        manifest = self._tree()
        reordered = dataclasses.replace(
            manifest, entries=tuple(reversed(manifest.entries))
        )
        with self.assertRaises(LockedNpmError) as ctx:
            tree_module.verify_tree(self.root, reordered)
        self.assertEqual(ctx.exception.reason, "tree_order_mismatch")

    def test_manifest_digest_corruption_detected(self):
        manifest = self._tree()
        tampered = dataclasses.replace(manifest, digest="0" * 64)
        with self.assertRaises(LockedNpmError) as ctx:
            tree_module.verify_tree(self.root, tampered)
        self.assertEqual(ctx.exception.reason, "tree_manifest_digest_mismatch")

    def test_verifier_never_follows_symlinks(self):
        # A symlink whose target lives outside the tree must be reported as
        # a symlink escape, never followed to hash the external file.
        outside = self.root.parent / "outside.txt"
        outside.write_text("external")
        manifest = self._tree()
        (self.root / "file.txt").unlink()
        (self.root / "file.txt").symlink_to("../outside.txt")
        with self.assertRaises(LockedNpmError) as ctx:
            tree_module.verify_tree(self.root, manifest)
        self.assertEqual(ctx.exception.reason, "tree_symlink_escape")
        self.assertEqual(outside.read_text(), "external")


class TestVerifierManifestValidation(unittest.TestCase):
    def test_duplicate_path_rejected(self):
        entry = TreeEntry(
            path="a", kind="file", digest="", target="", mode=0, uid=0, gid=0
        )
        manifest = TreeManifest(
            entries=(entry, entry),
            digest=tree_module.canonical_tree_digest((entry, entry)),
        )
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(LockedNpmError) as ctx:
                tree_module.verify_tree(Path(tmp), manifest)
            self.assertEqual(ctx.exception.reason, "tree_order_mismatch")


if __name__ == "__main__":
    unittest.main()
