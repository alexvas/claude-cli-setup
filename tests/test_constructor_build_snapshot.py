from __future__ import annotations

import errno
import hashlib
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from docker.versioning.build_materialization import SelectedBuildArtifact, materialize_artifact
from docker.versioning.build_snapshot import (
    SnapshotError,
    cleanup_artifact_snapshot,
    create_artifact_snapshot,
)
from docker.versioning.digest_identity import DigestIdentity
from tests.privilege_helpers import docker_dev_ids, sudo_chown, sudo_maintain_tree


class TestArtifactSnapshot(unittest.TestCase):
    def _selected(self, root: Path):
        result = []
        for name, payload in (("rustup", b"r"), ("uv", b"u"), ("rtk", b"t"), ("fd", b"f")):
            blob = root / f"{name}.blob"
            blob.write_bytes(payload)
            blob.chmod(0o444)
            result.append((SelectedBuildArtifact(name, "https://not-exposed.invalid/", DigestIdentity.from_hex("sha256", hashlib.sha256(payload).hexdigest())), blob))
        return result

    def test_canonical_manifest_stable_names_and_narrow_exposure(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            pairs = self._selected(root)
            one = create_artifact_snapshot((x[0] for x in pairs), (x[1] for x in pairs), checkout_root=root)
            two = create_artifact_snapshot((x[0] for x in pairs), (x[1] for x in pairs), checkout_root=root)
            self.assertEqual(one.manifest.read_bytes(), two.manifest.read_bytes())
            self.assertEqual({"rustup-init", "uv.tar.gz", "rtk.deb", "fd.deb", "manifest.json"}, {p.name for p in one.path.iterdir()})
            self.assertNotIn(".docker-cache", one.manifest.read_text())
            cleanup_artifact_snapshot(one); cleanup_artifact_snapshot(two)

    def test_prefers_hardlink_and_survives_cache_unlink(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); pairs = self._selected(root)
            snapshot = create_artifact_snapshot((x[0] for x in pairs), (x[1] for x in pairs), checkout_root=root)
            source = pairs[0][1]; imported = snapshot.path / "rustup-init"
            self.assertEqual(source.stat().st_ino, imported.stat().st_ino)
            source.unlink()
            self.assertEqual(b"r", imported.read_bytes())
            cleanup_artifact_snapshot(snapshot)

    def test_copy_fallback_rechecks_digest(self):
        # Resolve the external namespace before making snapshot hard links fail;
        # project metadata publication itself uses a no-clobber hard link.
        # EXDEV is the one hard-link failure that may fall back to copying; the
        # copied payload must be descriptor-valid and the source left untouched.
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); pairs = self._selected(root)
            from docker.versioning.project_state import resolve_project_state
            cache = root / "cache"; cache.mkdir(mode=0o700)
            state = resolve_project_state(root, cache_root=cache)
            source = pairs[0][1]
            content = source.read_bytes()
            before = (source.stat().st_uid, source.stat().st_mode & 0o777,
                      source.stat().st_ino, content, hashlib.sha256(content).hexdigest())
            with patch("docker.versioning.build_snapshot.os.link", side_effect=OSError(errno.EXDEV, "cross-device")):
                snapshot = create_artifact_snapshot((x[0] for x in pairs), (x[1] for x in pairs), checkout_root=root, project_state=state)
            imported = snapshot.path / "rustup-init"
            self.assertNotEqual(source.stat().st_ino, imported.stat().st_ino)
            self.assertTrue(imported.is_file())
            self.assertEqual(0o444, imported.stat().st_mode & 0o777)
            self.assertEqual(content, imported.read_bytes())
            self.assertEqual(hashlib.sha256(imported.read_bytes()).hexdigest(), before[4])
            st = source.stat()
            self.assertEqual(st.st_uid, before[0])
            self.assertEqual(st.st_mode & 0o777, before[1])
            self.assertEqual(st.st_ino, before[2])
            self.assertEqual(source.read_bytes(), before[3])
            self.assertEqual(hashlib.sha256(source.read_bytes()).hexdigest(), before[4])
            cleanup_artifact_snapshot(snapshot)

    def test_copy_fallback_payloads_are_finalized_to_0444(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); pairs = self._selected(root)
            from docker.versioning.project_state import resolve_project_state
            cache = root / "cache"; cache.mkdir(mode=0o700)
            state = resolve_project_state(root, cache_root=cache)
            with patch("docker.versioning.build_snapshot.os.link", side_effect=OSError(errno.EXDEV, "cross-device")):
                snapshot = create_artifact_snapshot((x[0] for x in pairs), (x[1] for x in pairs), checkout_root=root, project_state=state)
            for name in ("rustup-init", "uv.tar.gz", "rtk.deb", "fd.deb", "manifest.json"):
                self.assertEqual(0o444, (snapshot.path / name).stat().st_mode & 0o777, name)
            cleanup_artifact_snapshot(snapshot)

    def test_hard_linked_payloads_are_never_chmodded_during_finalization_or_cleanup(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); pairs = self._selected(root)
            from docker.versioning.project_state import resolve_project_state
            cache = root / "cache"; cache.mkdir(mode=0o700)
            state = resolve_project_state(root, cache_root=cache)
            before = {blob: (blob.stat().st_uid, blob.stat().st_mode, blob.stat().st_ino, blob.read_bytes())
                      for _, blob in pairs}
            real_chmod = os.chmod
            calls: list[str] = []
            def spy(path, mode, *args, **kwargs):
                calls.append(os.fspath(path))
                return real_chmod(path, mode, *args, **kwargs)
            with patch("docker.versioning.build_snapshot.os.chmod", side_effect=spy):
                snapshot = create_artifact_snapshot((x[0] for x in pairs), (x[1] for x in pairs), checkout_root=root, project_state=state)
                cleanup_artifact_snapshot(snapshot)
            hard_linked = {"rustup-init", "uv.tar.gz", "rtk.deb", "fd.deb"}
            for call in calls:
                name = os.path.basename(call)
                self.assertNotIn(name, hard_linked, f"chmod must never touch hard-linked payload {name}")
            # Blob owner, mode, inode, content, and digest remain unchanged.
            for _, blob in pairs:
                st = blob.stat()
                self.assertEqual(st.st_uid, before[blob][0])
                self.assertEqual(st.st_mode, before[blob][1])
                self.assertEqual(st.st_ino, before[blob][2])
                self.assertEqual(blob.read_bytes(), before[blob][3])

    def test_nested_file_sharing_hard_link_basename_is_still_finalized(self):
        # A nested snapshot-owned file whose basename collides with a hard-linked
        # payload must still be finalized to 0444: only the exact root-relative
        # hard-linked path is excluded from chmod, never the basename alone.
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); pairs = self._selected(root)
            from docker.versioning.project_state import resolve_project_state
            cache = root / "cache"; cache.mkdir(mode=0o700)
            state = resolve_project_state(root, cache_root=cache)
            real_mkdtemp = tempfile.mkdtemp
            def mkdtemp_with_nested(prefix, dir):
                staging = real_mkdtemp(prefix=prefix, dir=dir)
                nested = Path(staging) / "nested"
                nested.mkdir()
                (nested / "rustup-init").write_bytes(b"nested-own-payload")
                return staging
            with patch("docker.versioning.build_snapshot.tempfile.mkdtemp", side_effect=mkdtemp_with_nested):
                snapshot = create_artifact_snapshot(
                    (x[0] for x in pairs), (x[1] for x in pairs), checkout_root=root, project_state=state)
            nested = snapshot.path / "nested" / "rustup-init"
            linked = snapshot.path / "rustup-init"
            self.assertEqual(0o444, nested.stat().st_mode & 0o777)
            self.assertEqual(0, nested.stat().st_mode & 0o222)
            # Only the exact hard-linked relative path shares the blob inode.
            self.assertEqual(pairs[0][1].stat().st_ino, linked.stat().st_ino)
            self.assertNotEqual(pairs[0][1].stat().st_ino, nested.stat().st_ino)
            self.assertEqual(0o444, linked.stat().st_mode & 0o777)
            cleanup_artifact_snapshot(snapshot)

    def test_unsafe_mode_hard_link_is_rejected_without_repairing_source(self):
        # A readable source that is not already 0444 must be rejected after a
        # successful os.link(), never silently chmodded on the shared inode.
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); pairs = self._selected(root)
            from docker.versioning.project_state import resolve_project_state
            cache = root / "cache"; cache.mkdir(mode=0o700)
            state = resolve_project_state(root, cache_root=cache)
            unsafe = pairs[0][1]
            unsafe.chmod(0o644)
            with self.assertRaises(SnapshotError):
                create_artifact_snapshot(
                    (x[0] for x in pairs), (x[1] for x in pairs), checkout_root=root, project_state=state)
            self.assertEqual(0o644, unsafe.stat().st_mode & 0o777)

    def test_foreign_owner_hard_link_is_rejected_without_adoption(self):
        # A readable foreign-owned source is rejected during source validation,
        # before any link or copy; it is never adopted, chmodded, or repaired.
        # os.link is only ever attempted for invoking-user-owned sources, so no
        # EPERM patch is required: validation rejects the foreign blob first.
        # Only the ownership transfer to docker-dev is delegated to sudo; the
        # snapshot validation itself runs as the invoking user.
        uid, gid = docker_dev_ids()
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); pairs = self._selected(root)
            from docker.versioning.project_state import resolve_project_state
            cache = root / "cache"; cache.mkdir(mode=0o700)
            state = resolve_project_state(root, cache_root=cache)
            foreign = pairs[0][1]
            foreign.chmod(0o444)
            sudo_chown(foreign, uid, gid)
            content = foreign.read_bytes()
            before = (foreign.stat().st_uid, foreign.stat().st_mode & 0o777,
                      foreign.stat().st_ino, content, hashlib.sha256(content).hexdigest())
            real_link = os.link
            linked_sources: list[str] = []
            def spy_link(src, dst, *args, **kwargs):
                linked_sources.append(os.fspath(src))
                return real_link(src, dst, *args, **kwargs)
            with patch("docker.versioning.build_snapshot.os.link", side_effect=spy_link), \
                 patch("docker.versioning.build_snapshot._copy_source_fd_to_destination") as copy:
                with self.assertRaises(SnapshotError):
                    create_artifact_snapshot(
                        (x[0] for x in pairs), (x[1] for x in pairs), checkout_root=root, project_state=state)
            copy.assert_not_called()
            self.assertNotIn(os.fspath(foreign), linked_sources)
            st = foreign.stat()
            self.assertEqual(st.st_uid, before[0])
            self.assertEqual(st.st_mode & 0o777, before[1])
            self.assertEqual(st.st_ino, before[2])
            self.assertEqual(foreign.read_bytes(), before[3])
            self.assertEqual(hashlib.sha256(foreign.read_bytes()).hexdigest(), before[4])

    def test_protected_hardlink_eperm_fails_closed_without_copy(self):
        # A valid source on a host that rejects hard links with EPERM (a
        # protected-hardlink policy) must fail closed and never fall back to
        # copying.  This runs unprivileged on every host.
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); pairs = self._selected(root)
            from docker.versioning.project_state import resolve_project_state
            cache = root / "cache"; cache.mkdir(mode=0o700)
            state = resolve_project_state(root, cache_root=cache)
            before = {blob: (blob.stat().st_uid, blob.stat().st_mode & 0o777, blob.stat().st_ino, blob.read_bytes())
                      for _, blob in pairs}
            with patch("docker.versioning.build_snapshot.os.link", side_effect=OSError(errno.EPERM, "Operation not permitted")), \
                 patch("docker.versioning.build_snapshot._copy_source_fd_to_destination") as copy:
                with self.assertRaises(SnapshotError):
                    create_artifact_snapshot(
                        (x[0] for x in pairs), (x[1] for x in pairs), checkout_root=root, project_state=state)
            copy.assert_not_called()
            for _, blob in pairs:
                st = blob.stat()
                self.assertEqual(st.st_uid, before[blob][0])
                self.assertEqual(st.st_mode & 0o777, before[blob][1])
                self.assertEqual(st.st_ino, before[blob][2])
                self.assertEqual(blob.read_bytes(), before[blob][3])

    def test_source_swap_between_validation_and_link_is_rejected(self):
        # A pathname replacement between source validation and os.link() must
        # be rejected by inode identity comparison, even when the replacement
        # is a safe invoking-user-owned 0444 regular file.  The originally
        # validated inode and the replacement must both survive untouched.
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); pairs = self._selected(root)
            from docker.versioning.project_state import resolve_project_state
            cache = root / "cache"; cache.mkdir(mode=0o700)
            state = resolve_project_state(root, cache_root=cache)
            source = pairs[0][1]  # rustup blob, processed after fd and rtk
            original_content = source.read_bytes()
            original = (source.stat().st_dev, source.stat().st_ino,
                        source.stat().st_uid, source.stat().st_mode & 0o777)
            real_link = os.link
            swapped = source.with_name(source.name + ".swapped")
            replacement_inode: list[tuple[int, int]] = []

            def swap_then_link(src, dst, *args, **kwargs):
                src_path = Path(os.fspath(src))
                if src_path == source:
                    os.rename(src_path, swapped)
                    src_path.write_bytes(b"replacement-not-accepted")
                    src_path.chmod(0o444)
                    st = src_path.stat()
                    replacement_inode.append((st.st_dev, st.st_ino))
                return real_link(src, dst, *args, **kwargs)

            with patch("docker.versioning.build_snapshot.os.link", side_effect=swap_then_link):
                with self.assertRaises(SnapshotError):
                    create_artifact_snapshot(
                        (x[0] for x in pairs), (x[1] for x in pairs),
                        checkout_root=root, project_state=state)
            # No transaction snapshot remains in the external namespace.
            self.assertEqual([], list(state.transactions_root.glob("transaction-*")))
            # The originally validated inode survives, untouched, under its
            # renamed pathname.
            self.assertTrue(swapped.exists())
            self.assertEqual(original_content, swapped.read_bytes())
            st = swapped.stat()
            self.assertEqual((st.st_dev, st.st_ino), original[:2])
            self.assertEqual(st.st_uid, original[2])
            self.assertEqual(st.st_mode & 0o777, original[3])
            # The replacement was not accepted, deleted, or mutated.
            self.assertEqual(b"replacement-not-accepted", source.read_bytes())
            st = source.stat()
            self.assertEqual((st.st_dev, st.st_ino), replacement_inode[0])
            self.assertEqual(st.st_uid, os.geteuid())
            self.assertEqual(st.st_mode & 0o777, 0o444)

    def test_post_finalization_validation_failure_uses_permission_aware_cleanup(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); pairs = self._selected(root)
            with patch("docker.versioning.build_snapshot.validate_host_owner_traversal", side_effect=RuntimeError("traversal failed")):
                with self.assertRaisesRegex(RuntimeError, "traversal failed"):
                    create_artifact_snapshot((x[0] for x in pairs), (x[1] for x in pairs), checkout_root=root)
            generated = root / ".docker-generated/build-artifacts"
            self.assertEqual([], list(generated.glob("transaction-*")))

    def test_finalized_files_and_directories_are_not_writable_and_cleanup_is_unconditional(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); pairs = self._selected(root)
            snapshot = create_artifact_snapshot((x[0] for x in pairs), (x[1] for x in pairs), checkout_root=root)
            self.assertEqual(0o444, (snapshot.path / "fd.deb").stat().st_mode & 0o777)
            self.assertEqual(0, snapshot.path.stat().st_mode & 0o222)
            cleanup_artifact_snapshot(snapshot)
            self.assertFalse(snapshot.path.exists())
            # Snapshot payloads are hard links when possible. Cleanup must not
            # chmod those links because that would mutate the cached inode and
            # make the next build report an unsafe/corrupt cache hit.
            self.assertTrue(all((blob.stat().st_mode & 0o777) == 0o444 for _, blob in pairs))


class TwoBuildOwnershipMaintenanceRegression(unittest.TestCase):
    """Task 4.2: blob reuse survives project-scoped ownership maintenance."""

    def _artifact(self, name, payload):
        return SelectedBuildArtifact(
            name, f"https://{name}.example.invalid/{name}",
            DigestIdentity.from_hex("sha256", hashlib.sha256(payload).hexdigest()),
        )

    def test_two_builds_reuse_blobs_after_project_ownership_maintenance(self):
        artifacts = [
            (self._artifact(name, payload), payload)
            for name, payload in (
                ("rustup", b"rustup-payload"), ("uv", b"uv-payload"),
                ("rtk", b"rtk-payload"), ("fd", b"fd-payload"),
            )
        ]
        class Transport:
            def __init__(self, table):
                self.table, self.calls = table, []
            def stream(self, url):
                self.calls.append(url)
                if url not in self.table:
                    raise AssertionError(f"unexpected network access: {url}")
                yield self.table[url]

        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            work = base / "work"; work.mkdir(mode=0o755)
            project = work / "constructor"; project.mkdir()
            primary = work / "primary-workspace"; primary.mkdir()
            extra = work / "extra-workspace"; extra.mkdir()
            cache = base / "cache"; cache.mkdir(mode=0o700)
            from docker.versioning.project_state import resolve_project_state
            state = resolve_project_state(project, cache_root=cache)

            # First build: streamed misses, immutable snapshot, cleanup.
            first = Transport({a.url: p for a, p in artifacts})
            blobs1 = tuple(materialize_artifact(
                a, checkout_root=project, cache_root=cache, project_state=state,
                transport=first,
            ) for a, _ in artifacts)
            self.assertEqual(len(artifacts), len(first.calls))
            snap1 = create_artifact_snapshot(
                (a for a, _ in artifacts), blobs1, checkout_root=project, project_state=state)
            cleanup_artifact_snapshot(snap1)
            before = {blob: (blob.stat().st_uid, blob.stat().st_mode, blob.stat().st_ino, blob.read_bytes())
                      for blob in blobs1}

            # External host event between invocations: recursive docker-dev
            # ownership transfer plus group read/write/traverse permission,
            # delegated to sudo. Only the project/workspace trees are
            # maintained; the cache and its blobs stay invoking-user-owned.
            uid, gid = docker_dev_ids()
            for root in (project, primary, extra):
                sudo_maintain_tree(root, uid, gid)

            # Second build as the original invoking user: a download-free cache
            # hit whose blobs are byte-, inode-, mode-, and owner-identical.
            second = Transport({})
            blobs2 = tuple(materialize_artifact(
                a, checkout_root=project, cache_root=cache, project_state=state,
                transport=second,
            ) for a, _ in artifacts)
            self.assertEqual([], second.calls)
            self.assertEqual(blobs2, blobs1)
            for blob in blobs1:
                st = blob.stat()
                self.assertEqual(st.st_uid, os.geteuid())
                self.assertEqual(st.st_mode & 0o777, 0o444)
                self.assertEqual(st.st_ino, before[blob][2])
                self.assertEqual(blob.read_bytes(), before[blob][3])
            snap2 = create_artifact_snapshot(
                (a for a, _ in artifacts), blobs2, checkout_root=project, project_state=state)
            cleanup_artifact_snapshot(snap2)


if __name__ == "__main__":
    unittest.main()
