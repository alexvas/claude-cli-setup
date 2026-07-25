"""Focused persistence tests for Stage 4 — Effective Build Projection filesystem.

Tests atomic write, validation-before-write, failure modes, and path boundaries.
Uses temporary directories; no Docker, no network.
"""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import dataclasses

from docker.versioning.rendering import (
    EffectiveInventoryOutputError,
    serialize_effective_build,
    validate_effective_build,
    write_effective_build,
)
from docker.versioning.model import (
    EffectiveArtifact,
    EffectiveBuildProjection,
    EffectiveNode,
    EffectiveRust,
    EffectiveTool,
)


def _fake_projection():
    return EffectiveBuildProjection(
        platform="linux-amd64",
        node=EffectiveNode(image="docker.io/library/node:24-trixie-slim@sha256:abc"),
        rust=EffectiveRust(
            version="1.0.0", profile="minimal",
            components=("rustfmt", "clippy"),
            rustup=EffectiveArtifact(url="https://example.com/rustup", sha256="a" * 64),
        ),
        uv=EffectiveTool(
            version="0.1.0",
            artifact=EffectiveArtifact(url="https://example.com/uv.tar.gz", sha256="b" * 64),
        ),
        python_version="3.14.6",
        ty_version="0.0.61",
        rtk=EffectiveTool(
            version="v0.43.0",
            artifact=EffectiveArtifact(url="https://example.com/rtk.deb", sha256="c" * 64),
        ),
        fd=EffectiveTool(
            version="v10.4.2",
            artifact=EffectiveArtifact(url="https://example.com/fd.deb", sha256="d" * 64),
        ),
        pi_version="0.80.10",
        openspec_version="1.6.0",
        oh_my_zsh_revision="abc123",
    )


# ---------------------------------------------------------------------------
# 4.2.1 Canonical output
# ---------------------------------------------------------------------------

class TestCanonicalOutputPath(unittest.TestCase):
    """The canonical output goes to .docker-generated/docker-constructor.build.effective.toml."""

    def _make_tmp_root(self) -> Path:
        d = tempfile.mkdtemp()
        self.addCleanup(lambda: _rmtree(d))
        return Path(d)

    def test_creates_canonical_directory_and_file(self):
        root = self._make_tmp_root()
        expected = root / ".docker-generated" / "docker-constructor.build.effective.toml"
        projection = _fake_projection()

        result = write_effective_build(projection, repo_root=root)
        self.assertTrue(result.exists(), f"output not created at {result}")
        self.assertEqual(result.resolve(), expected.resolve())
        self.assertTrue(result.parent.is_dir())

    def test_existing_dot_docker_generated_reused(self):
        """If .docker-generated already exists, it is reused, not blown away."""
        root = self._make_tmp_root()
        gen = root / ".docker-generated"
        gen.mkdir()
        (gen / "something-else.txt").write_text("keep me")

        write_effective_build(_fake_projection(), repo_root=root)
        self.assertTrue((gen / "something-else.txt").exists(),
                        "existing sibling file was removed")


# ---------------------------------------------------------------------------
# 4.2.2 Atomic replacement
# ---------------------------------------------------------------------------

class TestAtomicReplacement(unittest.TestCase):

    def _make_tmp_root(self) -> Path:
        d = tempfile.mkdtemp()
        self.addCleanup(lambda: _rmtree(d))
        return Path(d)

    def test_writes_to_temp_then_replaces(self):
        """The write must use a temporary sibling, then os.replace."""
        root = self._make_tmp_root()
        expected = root / ".docker-generated" / "docker-constructor.build.effective.toml"

        # Pre-create a fake destination
        expected.parent.mkdir(parents=True)
        expected.write_text("original content")

        # Track calls to os.replace
        with mock.patch("os.replace", wraps=os.replace) as sp:
            write_effective_build(_fake_projection(), repo_root=root)
            sp.assert_called_once()
            src_arg = Path(sp.call_args[0][0])
            dst_arg = Path(sp.call_args[0][1])
            self.assertNotEqual(src_arg, dst_arg,
                                "os.replace src and dst must differ")
            self.assertEqual(dst_arg.resolve(), expected.resolve())
            self.assertIn(".docker-generated", str(src_arg.parent))

    def test_existing_projection_fully_replaced(self):
        """An existing projection must be completely replaced, not appended."""
        root = self._make_tmp_root()
        expected = root / ".docker-generated" / "docker-constructor.build.effective.toml"
        expected.parent.mkdir(parents=True)
        expected.write_text("[node]\nimage = \"old\"")

        write_effective_build(_fake_projection(), repo_root=root)
        content = expected.read_text()
        self.assertNotIn("old", content,
                         "old content survived replacement")


# ---------------------------------------------------------------------------
# 4.2.3 Validation before write
# ---------------------------------------------------------------------------

class TestValidationBeforeWrite(unittest.TestCase):

    def _make_tmp_root(self) -> Path:
        d = tempfile.mkdtemp()
        self.addCleanup(lambda: _rmtree(d))
        return Path(d)

    def test_destination_untouched_when_validation_fails(self):
        """An existing file must remain intact if projection validation fails."""
        root = self._make_tmp_root()
        expected = root / ".docker-generated" / "docker-constructor.build.effective.toml"
        expected.parent.mkdir(parents=True)
        expected.write_text("original")

        # Create a projection that will fail validation
        bad = _fake_projection()

        # Mock validate_effective_build to raise
        with mock.patch(
            "docker.versioning.rendering.validate_effective_build",
            side_effect=ValueError("bad projection"),
        ):
            with self.assertRaises(ValueError):
                write_effective_build(bad, repo_root=root)

        self.assertEqual(expected.read_text(), "original",
                         "destination was modified after validation failure")


# ---------------------------------------------------------------------------
# 4.2.4 Failure modes preserve old file
# ---------------------------------------------------------------------------

class TestFailurePreservation(unittest.TestCase):

    def _make_tmp_root(self) -> Path:
        d = tempfile.mkdtemp()
        self.addCleanup(lambda: _rmtree(d))
        return Path(d)

    def _make_existing_dest(self, root: Path) -> Path:
        dest = root / ".docker-generated" / "docker-constructor.build.effective.toml"
        dest.parent.mkdir(parents=True)
        dest.write_text("original content")
        return dest

    def test_old_file_preserved_on_serialization_failure(self):
        root = self._make_tmp_root()
        dest = self._make_existing_dest(root)

        with mock.patch(
            "docker.versioning.rendering.serialize_effective_build",
            side_effect=RuntimeError("serialization exploded"),
        ):
            with self.assertRaises(RuntimeError):
                write_effective_build(_fake_projection(), repo_root=root)

        self.assertTrue(dest.exists())
        self.assertEqual(dest.read_text(), "original content")

    def test_old_file_preserved_on_flush_failure(self):
        root = self._make_tmp_root()
        dest = self._make_existing_dest(root)

        # Make fsync fail after write/flush succeeds
        with mock.patch("os.fsync", side_effect=OSError("disk full")):
            with self.assertRaises(OSError):
                write_effective_build(_fake_projection(), repo_root=root)

        self.assertTrue(dest.exists())
        self.assertEqual(dest.read_text(), "original content")

    def test_temp_files_cleaned_on_failure(self):
        root = self._make_tmp_root()
        dest = self._make_existing_dest(root)

        # Count files in .docker-generated before
        gen_dir = dest.parent
        before = set(gen_dir.iterdir())

        with mock.patch("os.replace", side_effect=OSError("replace failed")):
            with self.assertRaises(OSError):
                write_effective_build(_fake_projection(), repo_root=root)

        after = set(gen_dir.iterdir())
        # Only the original file should remain; no temp files
        self.assertEqual(after, before,
                         f"temp files leaked: {after - before}")


# ---------------------------------------------------------------------------
# 4.2.5 Canonical path enforcement
# ---------------------------------------------------------------------------

class TestCanonicalPathEnforcement(unittest.TestCase):
    """The canonical output path is always derived from repo_root — never user-specified."""

    def _make_tmp_root(self) -> Path:
        d = tempfile.mkdtemp()
        self.addCleanup(lambda: _rmtree(d))
        return Path(d)

    def test_always_uses_canonical_path(self):
        """The returned path is always .docker-generated/docker-constructor.build.effective.toml."""
        root = self._make_tmp_root()
        result = write_effective_build(_fake_projection(), repo_root=root)
        expected = root / ".docker-generated" / "docker-constructor.build.effective.toml"
        self.assertEqual(result.resolve(), expected.resolve())

    def test_ignores_nested_dot_docker_generated_dirs(self):
        """Even if nested .docker-generated directories exist, the canonical path
        is always at the top-level repo_root / .docker-generated."""
        root = self._make_tmp_root()
        # Create a nested .docker-generated that should have no effect
        nested = root / "sub" / ".docker-generated"
        nested.mkdir(parents=True)
        (nested / "docker-constructor.build.effective.toml").write_text("nested junk")

        result = write_effective_build(_fake_projection(), repo_root=root)
        expected = root / ".docker-generated" / "docker-constructor.build.effective.toml"
        self.assertEqual(result.resolve(), expected.resolve())
        # Nested file must remain untouched
        self.assertEqual((nested / "docker-constructor.build.effective.toml").read_text(),
                         "nested junk")

    def test_repo_root_deep_subdirectory_still_uses_canonical_path(self):
        """When repo_root is a deep path, output is still .docker-generated at that root."""
        root = self._make_tmp_root()
        deep = root / "a" / "b" / "c"
        deep.mkdir(parents=True)

        result = write_effective_build(_fake_projection(), repo_root=deep)
        expected = deep / ".docker-generated" / "docker-constructor.build.effective.toml"
        self.assertEqual(result.resolve(), expected.resolve())

    def test_existing_dot_docker_generated_with_same_name_accepted(self):
        """If the canonical file already exists (e.g. prior build), it is replaced."""
        root = self._make_tmp_root()
        gen = root / ".docker-generated"
        gen.mkdir()
        existing = gen / "docker-constructor.build.effective.toml"
        existing.write_text("stale projection")

        result = write_effective_build(_fake_projection(), repo_root=root)
        self.assertNotEqual(result.read_text(), "stale projection")

    def test_no_destination_parameter_accepted(self):
        """write_effective_build rejects a *destination* keyword argument."""
        root = self._make_tmp_root()
        with self.assertRaises(TypeError):
            write_effective_build(
                _fake_projection(),
                destination=root / "somewhere.toml",  # type: ignore[call-arg]
                repo_root=root,
            )


# ---------------------------------------------------------------------------
# 4.2.6 Symlink escape rejection
# ---------------------------------------------------------------------------

class TestSymlinkEscapeRejection(unittest.TestCase):
    """Both .docker-generated and the leaf file are checked for symlink escapes."""

    def _make_tmp_root(self) -> Path:
        d = tempfile.mkdtemp()
        self.addCleanup(lambda: _rmtree(d))
        return Path(d)

    def test_parent_symlink_outside_repo_rejected(self):
        """If .docker-generated is a symlink outside repo_root, the write is refused."""
        root = self._make_tmp_root()
        outside = self._make_tmp_root()
        # Create the real dir outside root
        real_gen = outside / ".docker-generated"
        real_gen.mkdir()
        # Symlink .docker-generated inside root -> outside
        (root / ".docker-generated").symlink_to(real_gen)

        with self.assertRaises((ValueError, OSError, EffectiveInventoryOutputError)):
            write_effective_build(_fake_projection(), repo_root=root)
        # The symlink itself is inside root, but the write must not have
        # created any *new* file at the canonical destination inside root
        dest = (root / ".docker-generated" / "docker-constructor.build.effective.toml")
        self.assertFalse(dest.exists() and not dest.is_symlink(),
                         "no regular file written inside repo root")

    def test_leaf_symlink_outside_repo_rejected(self):
        """Any leaf symlink is rejected, even if the target is outside the repo."""
        root = self._make_tmp_root()
        outside = self._make_tmp_root()
        gen = root / ".docker-generated"
        gen.mkdir()
        leaf = gen / "docker-constructor.build.effective.toml"
        leaf.symlink_to(outside / "escaped.toml")

        with self.assertRaises((ValueError, OSError, EffectiveInventoryOutputError)):
            write_effective_build(_fake_projection(), repo_root=root)

    def test_parent_absolute_symlink_outside_rejected(self):
        """An absolute symlink for .docker-generated pointing outside is caught."""
        root = self._make_tmp_root()
        outside = self._make_tmp_root()
        real_gen = outside / ".docker-generated"
        real_gen.mkdir()
        (root / ".docker-generated").symlink_to(real_gen.resolve())

        with self.assertRaises((ValueError, OSError, EffectiveInventoryOutputError)):
            write_effective_build(_fake_projection(), repo_root=root)

    def test_leaf_symlink_inside_repo_rejected(self):
        """A leaf symlink targeting a file inside repo_root is still rejected.

        os.replace would overwrite the target, leaving the canonical path as
        a symlink — the canonical path must be a regular file, not a symlink.
        """
        root = self._make_tmp_root()
        gen = root / ".docker-generated"
        gen.mkdir()
        # Create a real file inside the repo
        real_target = root / "some-other-file.toml"
        real_target.write_text("target content")
        # Symlink the leaf to it
        leaf = gen / "docker-constructor.build.effective.toml"
        leaf.symlink_to(real_target)

        with self.assertRaises((ValueError, OSError, EffectiveInventoryOutputError)):
            write_effective_build(_fake_projection(), repo_root=root)
        # The target file must be untouched
        self.assertEqual(real_target.read_text(), "target content")

    def test_symlink_inside_repo_allowed(self):
        """A symlink that stays within repo_root is not an escape."""
        root = self._make_tmp_root()
        # Create real directory inside root
        real_gen = root / "real-docker-generated"
        real_gen.mkdir()
        # Symlink .docker-generated -> real-docker-generated (inside root)
        (root / ".docker-generated").symlink_to(real_gen)

        result = write_effective_build(_fake_projection(), repo_root=root)
        # The file must exist at the resolved location
        self.assertTrue(result.exists())
        self.assertIn("real-docker-generated", str(result.resolve()))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _rmtree(path: str) -> None:
    """Best-effort rmtree for cleanup."""
    import shutil
    try:
        shutil.rmtree(path, ignore_errors=True)
    except Exception:
        pass
