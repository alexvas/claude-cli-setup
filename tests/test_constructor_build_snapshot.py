from __future__ import annotations

import hashlib
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from docker.versioning.build_materialization import SelectedBuildArtifact
from docker.versioning.build_snapshot import create_artifact_snapshot, cleanup_artifact_snapshot
from docker.versioning.digest_identity import DigestIdentity


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
        with tempfile.TemporaryDirectory() as td, patch("docker.versioning.build_snapshot.os.link", side_effect=OSError("cross-device")):
            root = Path(td); pairs = self._selected(root)
            snapshot = create_artifact_snapshot((x[0] for x in pairs), (x[1] for x in pairs), checkout_root=root)
            self.assertNotEqual(pairs[0][1].stat().st_ino, (snapshot.path / "rustup-init").stat().st_ino)
            cleanup_artifact_snapshot(snapshot)

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
