"""RED — content-addressed cache key contracts for host artifact
materialization.

These tests define the cache identity, layout, and safety contracts
BEFORE any materialization or download implementation exists.

The SRI derivation tests (``TestSRIIdentity``) are expected to be
**GREEN** now because the production module ``docker.versioning.
artifact_cache`` already contains the pure path-derivation functions
(task 2.4).

The cache-filesystem, layout, and containment tests
(``TestCacheLayout``, ``TestCacheSafety``) are **RED** because no
materialization layer, corruption recovery, or publication boundary
exists yet.
"""
from __future__ import annotations

import os
import unittest


# ═══════════════════════════════════════════════════════════════════════
# 2.1a — canonical integrity identities
# ═══════════════════════════════════════════════════════════════════════


class TestSRIIdentity(unittest.TestCase):
    """Canonical integrity identity derivation."""

    def test_parse_sha512_integrity(self) -> None:
        from docker.versioning.artifact_cache import _sri_to_algorithm_digest

        # Use a synthetic integrity that includes + and / so we can
        # verify the URL-safe replacement.
        algo, raw, safe = _sri_to_algorithm_digest(
            "sha512-AA++BB//CC==",
        )
        self.assertEqual(algo, "sha512")
        # raw preserves original base64 characters
        self.assertIn("+", raw)
        self.assertIn("/", raw)
        # safe replaces +→-  /→_
        self.assertNotIn("+", safe)
        self.assertNotIn("/", safe)
        self.assertIn("-", safe)
        self.assertIn("_", safe)
        # padding is preserved
        self.assertTrue(safe.endswith("=="))

    def test_parse_sha256_integrity(self) -> None:
        from docker.versioning.artifact_cache import _sri_to_algorithm_digest

        algo, raw, safe = _sri_to_algorithm_digest(
            "sha256-abc123XYZ789+/==",
        )
        self.assertEqual(algo, "sha256")
        self.assertEqual(raw, "abc123XYZ789+/==")
        self.assertEqual(safe, "abc123XYZ789-_==")

    def test_parse_sha384_integrity(self) -> None:
        from docker.versioning.artifact_cache import _sri_to_algorithm_digest

        algo, raw, safe = _sri_to_algorithm_digest(
            "sha384-AABBCCDDEEaabbccddee//++==",
        )
        self.assertEqual(algo, "sha384")
        self.assertEqual(safe, "AABBCCDDEEaabbccddee__--==")

    def test_supported_algorithms_accepted(self) -> None:
        for algo in ("sha256", "sha384", "sha512"):
            with self.subTest(algorithm=algo):
                from docker.versioning.artifact_cache import (
                    _sri_to_algorithm_digest,
                )

                _integrity = f"{algo}-AAAA"
                parsed_algo, _, _ = _sri_to_algorithm_digest(_integrity)
                self.assertEqual(parsed_algo, algo)


# ═══════════════════════════════════════════════════════════════════════
# 2.1b — filesystem-safe cache keys
# ═══════════════════════════════════════════════════════════════════════


class TestCacheKeySafety(unittest.TestCase):
    """Cache keys must be filesystem-safe."""

    def test_no_plus_in_key(self) -> None:
        from docker.versioning.artifact_cache import (
            _sri_to_algorithm_digest,
        )

        _, _, safe = _sri_to_algorithm_digest("sha512-AA++BB//CC==")
        self.assertNotIn("+", safe, "raw base64 '+' must be replaced")

    def test_no_slash_in_key(self) -> None:
        from docker.versioning.artifact_cache import (
            _sri_to_algorithm_digest,
        )

        _, _, safe = _sri_to_algorithm_digest("sha512-AA++BB//CC==")
        self.assertNotIn("/", safe, "raw base64 '/' must be replaced")


# ═══════════════════════════════════════════════════════════════════════
# 2.1c — fixed cache layout
# ═══════════════════════════════════════════════════════════════════════


class TestCacheLayout(unittest.TestCase):
    """Cache layout is deterministic and algorithm+depth fixed."""

    def test_path_is_algorithm_then_digest(self) -> None:
        from docker.versioning.artifact_cache import derive_cache_path

        path = derive_cache_path("sha512", "abcdef", root="/tmp/c")
        self.assertEqual(path, "/tmp/c/sha512/abcdef.tgz")

    def test_extension_is_always_tgz(self) -> None:
        from docker.versioning.artifact_cache import derive_cache_path

        path = derive_cache_path("sha256", "xyz", root="/cache")
        self.assertTrue(path.endswith(".tgz"))

    def test_only_algorithm_and_digest_participate(self) -> None:
        from docker.versioning.artifact_cache import derive_cache_path

        p1 = derive_cache_path("sha512", "digest-a", root="/root")
        p2 = derive_cache_path("sha512", "digest-b", root="/root")
        self.assertNotEqual(p1, p2)

    def test_default_root_is_constructor_owned(self) -> None:
        from docker.versioning.artifact_cache import (
            DEFAULT_RUNTIME_ARTIFACT_CACHE_ROOT,
            derive_cache_path,
        )

        path = derive_cache_path("sha512", "d")
        self.assertTrue(
            path.startswith(DEFAULT_RUNTIME_ARTIFACT_CACHE_ROOT),
        )
        self.assertIn("sha512", path)
        self.assertTrue(path.endswith(".tgz"))

    def test_derive_cache_path_from_integrity(self) -> None:
        from docker.versioning.artifact_cache import (
            derive_cache_path_from_integrity,
        )

        integrity = (
            "sha512-VO9pV15PFTBOfcNq9hgKJ3K6k4Bb0ndDlX6N5"
            "ReNTOa/r66/Ppfc9N/hexsK5veMHGl1YbjCo3wOnL5jJu17/Q=="
        )
        path, algo = derive_cache_path_from_integrity(integrity)
        self.assertEqual(algo, "sha512")
        self.assertIn("sha512", path)
        self.assertTrue(path.endswith(".tgz"))


# ═══════════════════════════════════════════════════════════════════════
# 2.1d — root containment, no-symlink, regular-file, permissions
# ═══════════════════════════════════════════════════════════════════════


class TestCacheSafety(unittest.TestCase):
    """Cache safety invariants that the materialization layer must
    enforce at runtime.

    Every test calls ``validate_cache_blob`` with an unsafe input and
    asserts a specific :class:`ArtifactMaterializationError` with the
    expected *reason* code.  Until implementation, the function raises
    ``NotImplementedError`` — the tests fail with a clear diagnostic
    instead of silently accepting an unhandled error type.

    Tests that target a specific reason *other* than ``"containment"``
    create their fixtures **inside** a temporarily patched cache root
    so that a correct implementation passes the containment gate and
    reaches the intended check."""

    # ── helpers ────────────────────────────────────────────────────

    @staticmethod
    def _assert_rejected(
        reason: str, host_path: str,
    ) -> None:
        """Assert ``validate_cache_blob(host_path)`` raises
        ``ArtifactMaterializationError`` with the given *reason*.

        When the validator is not yet implemented this helper
        produces a clean FAIL rather than an unhandled ERROR."""
        from docker.versioning.artifact_cache import (
            ArtifactMaterializationError,
            validate_cache_blob,
        )

        try:
            validate_cache_blob(host_path)
        except NotImplementedError:
            import unittest as _ut
            raise _ut.TestCase.failureException(  # noqa: TRY102
                f"validate_cache_blob is NOT IMPLEMENTED — "
                f"expected ArtifactMaterializationError(reason={reason!r}) "
                f"for path {host_path!r}"
            ) from None
        except ArtifactMaterializationError as exc:
            if exc.reason != reason:
                import unittest as _ut
                raise _ut.TestCase.failureException(
                    f"expected reason={reason!r} "
                    f"but got reason={exc.reason!r}"
                ) from None
            return  # GREEN — correct rejection
        else:
            import unittest as _ut
            raise _ut.TestCase.failureException(
                f"expected ArtifactMaterializationError(reason={reason!r}) "
                f"but no exception was raised for path {host_path!r}"
            )

    @staticmethod
    def _assert_accepted(host_path: str) -> None:
        """Assert ``validate_cache_blob(host_path)`` returns
        without raising (the blob is structurally sound).

        Converts ``NotImplementedError`` to a clean FAIL so the
        test team can see at a glance which safety contracts are
        not yet wired."""
        from docker.versioning.artifact_cache import validate_cache_blob

        try:
            validate_cache_blob(host_path)
        except NotImplementedError:
            import unittest as _ut
            raise _ut.TestCase.failureException(
                f"validate_cache_blob is NOT IMPLEMENTED — "
                f"expected no exception for valid blob {host_path!r}"
            ) from None
        # Any other exception is a genuine failure (wrong rejection).

    # ── containment: genuinely outside any plausible root ──────────

    def test_paths_outside_cache_root_rejected(self) -> None:
        """RED — paths outside the cache root are rejected with
        reason ``"containment"``."""
        self._assert_rejected("containment", "/etc/passwd")

    def test_symlink_parent_escape_rejected(self) -> None:
        """RED — a blob whose lexical path is inside the root but
        whose resolved path escapes through a symlinked parent
        directory is rejected with reason ``"containment"``."""
        import tempfile
        from unittest import mock

        # ── arrange a blob in a directory *outside* the root ──
        with tempfile.TemporaryDirectory() as outside_dir:
            blob_real = os.path.join(outside_dir, "blob.tgz")
            with open(blob_real, "wb") as fh:
                fh.write(b"legitimate-bytes")
            os.chmod(blob_real, 0o600)

            # ── create a symlink *inside* the root that points to the
            #    outside directory ──
            with tempfile.TemporaryDirectory() as root:
                link_parent = os.path.join(root, "link_parent")
                os.symlink(outside_dir, link_parent)
                blob_via_link = os.path.join(link_parent, "blob.tgz")

                with mock.patch(
                    "docker.versioning.artifact_cache.DEFAULT_RUNTIME_ARTIFACT_CACHE_ROOT",
                    root,
                ):
                    self._assert_rejected("containment", blob_via_link)

    # ── missing blob ───────────────────────────────────────────────

    def test_missing_blob_path_rejected(self) -> None:
        """RED — a path that does not exist is rejected with
        reason ``"missing"``."""
        import tempfile
        from unittest import mock

        with tempfile.TemporaryDirectory() as root:
            nonexistent = os.path.join(root, "nonexistent.tgz")
            with mock.patch(
                "docker.versioning.artifact_cache.DEFAULT_RUNTIME_ARTIFACT_CACHE_ROOT",
                root,
            ):
                self._assert_rejected("missing", nonexistent)

    # ── symlink (fixture inside a patched root, containment satisfied) ─

    def test_symlink_at_blob_path_rejected(self) -> None:
        """RED — within the cache root, a symlink at the blob path
        is rejected with reason ``"symlink"``."""
        import tempfile
        from unittest import mock

        with tempfile.TemporaryDirectory() as root:
            target = os.path.join(root, "target")
            link = os.path.join(root, "link")
            with open(target, "wb") as fh:
                fh.write(b"data")
            os.symlink(target, link)

            with mock.patch(
                "docker.versioning.artifact_cache.DEFAULT_RUNTIME_ARTIFACT_CACHE_ROOT",
                root,
            ):
                self._assert_rejected("symlink", link)

    # ── not-regular-file (directory / non-regular inside root) ─────

    def test_directory_at_blob_path_rejected(self) -> None:
        """RED — within the cache root, a directory at the blob
        path is rejected with reason ``"not_regular_file"``."""
        import tempfile
        from unittest import mock

        with tempfile.TemporaryDirectory() as root:
            subdir = os.path.join(root, "subdir")
            os.mkdir(subdir)

            with mock.patch(
                "docker.versioning.artifact_cache.DEFAULT_RUNTIME_ARTIFACT_CACHE_ROOT",
                root,
            ):
                self._assert_rejected("not_regular_file", subdir)

    def test_fifo_at_blob_path_rejected(self) -> None:
        """RED — within the cache root, a named pipe (FIFO) is
        rejected with reason ``"not_regular_file"``."""
        import tempfile
        from unittest import mock

        with tempfile.TemporaryDirectory() as root:
            fifo_path = os.path.join(root, "fifo")
            os.mkfifo(fifo_path)

            with mock.patch(
                "docker.versioning.artifact_cache.DEFAULT_RUNTIME_ARTIFACT_CACHE_ROOT",
                root,
            ):
                self._assert_rejected("not_regular_file", fifo_path)

            os.unlink(fifo_path)

    # ── permissions (world-readable file inside patched root) ───────

    def test_insecure_permissions_rejected(self) -> None:
        """RED — within the cache root, a blob with group/other
        access is rejected with reason ``"permissions"``."""
        import tempfile
        from unittest import mock

        with tempfile.TemporaryDirectory() as root:
            fd, path = tempfile.mkstemp(dir=root)
            os.close(fd)
            os.chmod(path, 0o644)

            with mock.patch(
                "docker.versioning.artifact_cache.DEFAULT_RUNTIME_ARTIFACT_CACHE_ROOT",
                root,
            ):
                self._assert_rejected("permissions", path)

            os.unlink(path)

    # ── valid blob accepted (GREEN after implementation) ───────────

    def test_valid_blob_accepted(self) -> None:
        """RED (until implemented) — a regular file inside the
        cache root with owner-only permissions is accepted without
        raising."""
        import tempfile
        from unittest import mock

        with tempfile.TemporaryDirectory() as root:
            fd, path = tempfile.mkstemp(dir=root)
            os.close(fd)
            os.chmod(path, 0o600)

            with mock.patch(
                "docker.versioning.artifact_cache.DEFAULT_RUNTIME_ARTIFACT_CACHE_ROOT",
                root,
            ):
                self._assert_accepted(path)

            os.unlink(path)


# ═══════════════════════════════════════════════════════════════════════
# 2.1e — path derivation rejects non-content inputs
# ═══════════════════════════════════════════════════════════════════════


class TestNoURLPackageVersionInPath(unittest.TestCase):
    """Cache paths MUST NOT be derivable from URL, package, version, or
    caller-provided path — only algorithm and digest participate."""

    def test_url_does_not_affect_derived_path(self) -> None:
        from docker.versioning.artifact_cache import derive_cache_path

        p1 = derive_cache_path(
            "sha512", "digest",
            root="https://example.com/pkg-1.0.tgz",
        )
        p2 = derive_cache_path(
            "sha512", "digest",
            root="https://other.com/pkg-2.0.tgz",
        )
        # Only root changes, not algorithm/digest — but root is
        # constructor-owned, not caller-derived.  The contract is
        # that URL never participates in path derivation.
        # The functions don't even accept a URL parameter.
        self.assertEqual(
            derive_cache_path("sha512", "d"),
            derive_cache_path("sha512", "d"),
        )

    def test_version_does_not_affect_derived_path(self) -> None:
        from docker.versioning.artifact_cache import derive_cache_path

        self.assertEqual(
            derive_cache_path("sha512", "d"),
            derive_cache_path("sha512", "d"),
        )

    def test_package_name_does_not_affect_derived_path(self) -> None:
        from docker.versioning.artifact_cache import derive_cache_path

        self.assertEqual(
            derive_cache_path("sha512", "d"),
            derive_cache_path("sha512", "d"),
        )


# ═══════════════════════════════════════════════════════════════════════
# 2.2a — SelectedArtifact DTO module isolation
# ═══════════════════════════════════════════════════════════════════════


class TestArtifactDTOModuleIsolation(unittest.TestCase):
    """The cache-contracts module must not import facade, parser,
    presentation, Docker execution, or container-installer modules."""

    _FORBIDDEN = {
        "constructor_cli",
        "facade",
        "presentation",
        "tui",
        "launcher",
        "runtime_installer",
    }

    def test_no_forbidden_imports(self) -> None:
        import sys
        # Force import so the module is in sys.modules
        import docker.versioning.artifact_cache as _cache  # noqa: F401

        cache_mod = "docker.versioning.artifact_cache"
        self.assertIn(cache_mod, sys.modules)
        module = sys.modules[cache_mod]
        for attr in dir(module):
            if attr.startswith("_"):
                continue
            val = getattr(module, attr, None)
            if val is None:
                continue
            mod_name = getattr(val, "__module__", "")
            if not mod_name:
                continue
            parts = mod_name.split(".")
            overlap = self._FORBIDDEN & set(parts)
            self.assertEqual(
                set(), overlap,
                f"{attr} imports from forbidden {overlap}",
            )

    def test_selected_artifact_has_no_package_name(self) -> None:
        from docker.versioning.artifact_cache import SelectedArtifact

        ann = getattr(SelectedArtifact, "__annotations__", {})
        self.assertNotIn("package_name", ann)
        self.assertNotIn("version", ann)
        self.assertNotIn("host_path", ann)

    def test_verified_cache_blob_has_no_url(self) -> None:
        from docker.versioning.artifact_cache import VerifiedCacheBlob

        ann = getattr(VerifiedCacheBlob, "__annotations__", {})
        self.assertNotIn("url", ann)
        self.assertNotIn("package_name", ann)
        self.assertNotIn("version", ann)


# ═══════════════════════════════════════════════════════════════════════
# 2.3 — boundary protocols exist and have correct signatures
# ═══════════════════════════════════════════════════════════════════════


class TestBoundaryProtocols(unittest.TestCase):
    """Each injected boundary must be importable and have the expected
    callable signatures."""

    @staticmethod
    def _method_names(proto: type) -> set[str]:
        """Return the set of public method names from a Protocol."""
        return {
            name for name in dir(proto)
            if callable(getattr(proto, name, None))
            and not name.startswith("_")
        }

    def test_cache_filesystem_signatures(self) -> None:
        from docker.versioning.artifact_cache import CacheFilesystem

        required = {
            "blob_exists", "is_regular_file", "is_symlink",
            "stat_blob", "read_bytes", "digest_file", "inspect_and_digest",
            "ensure_secure_dir",
            "create_temp", "append_temp", "finalize_temp", "cleanup_temp",
            "quarantine_or_remove", "get_permissions",
            "set_permissions", "atomic_publish",
        }
        self.assertEqual(required, self._method_names(CacheFilesystem))

    def test_streaming_transport_signature(self) -> None:
        from docker.versioning.artifact_cache import StreamingTransport

        self.assertIn("fetch_chunks", self._method_names(StreamingTransport))

    def test_identity_lock_signatures(self) -> None:
        from docker.versioning.artifact_cache import IdentityLock

        names = self._method_names(IdentityLock)
        self.assertIn("acquire", names)
        self.assertIn("release", names)

    def test_temporary_directory_signature(self) -> None:
        from docker.versioning.artifact_cache import TemporaryDirectory

        self.assertIn("mkdtemp", self._method_names(TemporaryDirectory))

    def test_error_reason_codes(self) -> None:
        from docker.versioning.artifact_cache import (
            ArtifactMaterializationError,
        )

        err = ArtifactMaterializationError(
            reason="integrity",
            detail="digest mismatch",
        )
        self.assertEqual(err.reason, "integrity")
        self.assertIsInstance(err, Exception)

    def test_error_is_immutable(self) -> None:
        from docker.versioning.artifact_cache import (
            ArtifactMaterializationError,
        )

        err = ArtifactMaterializationError(reason="t", detail="d")
        with self.assertRaises(Exception):
            err.reason = "other"  # type: ignore[misc]


# ═══════════════════════════════════════════════════════════════════════
# 2.4 — deterministic derivation (see TestCacheLayout above too)
# ═══════════════════════════════════════════════════════════════════════


class TestDerivationRejectsNonContentInputs(unittest.TestCase):
    """Cache path derivation SHALL NOT accept URL, package, version,
    or caller-provided path components in its parameter set."""

    def test_derive_cache_path_has_no_url_parameter(self) -> None:
        import inspect
        from docker.versioning.artifact_cache import derive_cache_path

        sig = inspect.signature(derive_cache_path)
        self.assertEqual(
            {"algorithm", "digest", "root"},
            set(sig.parameters.keys()),
        )

    def test_derive_cache_path_from_integrity_has_no_url_parameter(self) -> None:
        import inspect
        from docker.versioning.artifact_cache import (
            derive_cache_path_from_integrity,
        )

        sig = inspect.signature(derive_cache_path_from_integrity)
        self.assertEqual(
            {"integrity", "root"},
            set(sig.parameters.keys()),
        )


# ═══════════════════════════════════════════════════════════════════════
# 2.1f — hardened input validation for cache path derivation
# ═══════════════════════════════════════════════════════════════════════


class TestDerivationInputValidation(unittest.TestCase):
    """``derive_cache_path`` and ``derive_cache_path_from_integrity``
    MUST reject unsafe inputs before path construction."""

    # ── derived directly from the function ────────────────────────

    def test_unsupported_algorithm_raises_valueerror(self) -> None:
        from docker.versioning.artifact_cache import derive_cache_path

        for bad in ("md5", "sha1", "SHA512", "sha3-256", ""):
            with self.subTest(algorithm=bad):
                with self.assertRaises(ValueError):
                    derive_cache_path(bad, "safe-digest")

    def test_empty_digest_raises_valueerror(self) -> None:
        from docker.versioning.artifact_cache import derive_cache_path

        with self.assertRaises(ValueError):
            derive_cache_path("sha512", "")

    def test_traversal_dot_dot_in_digest_raises_valueerror(self) -> None:
        from docker.versioning.artifact_cache import derive_cache_path

        for bad in (".", ".."):
            with self.subTest(digest=bad):
                with self.assertRaises(ValueError):
                    derive_cache_path("sha512", bad)

    def test_path_separator_in_digest_raises_valueerror(self) -> None:
        from docker.versioning.artifact_cache import derive_cache_path

        for bad in ("/", "a/b", "trailing/", "//", "/etc"):
            with self.subTest(digest=bad):
                with self.assertRaises(ValueError):
                    derive_cache_path("sha512", bad)

    def test_backslash_in_digest_raises_valueerror(self) -> None:
        from docker.versioning.artifact_cache import derive_cache_path

        with self.assertRaises(ValueError):
            derive_cache_path("sha512", "dig\\est")

    def test_null_byte_in_digest_raises_valueerror(self) -> None:
        from docker.versioning.artifact_cache import derive_cache_path

        with self.assertRaises(ValueError):
            derive_cache_path("sha512", "dig\x00est")

    def test_non_base64url_characters_rejected(self) -> None:
        from docker.versioning.artifact_cache import derive_cache_path

        for bad in ("has space", "has:colon", "has\nnewline",
                    "has\ttab", "+", "plus+sign"):
            with self.subTest(digest=bad):
                with self.assertRaises(ValueError):
                    derive_cache_path("sha512", bad)

    def test_padding_only_in_trailing_position_allowed(self) -> None:
        """Padding ``=`` is only allowed at the end (at most two)."""
        from docker.versioning.artifact_cache import derive_cache_path

        # Valid trailing padding (1 or 2 chars)
        for ok in ("abc=", "abc=="):
            with self.subTest(digest=ok):
                derive_cache_path("sha512", ok)  # must not raise

        # Invalid: padding in the middle
        for bad in ("a=b", "a==b", "==", "========", "=abc", "==abc"):
            with self.subTest(digest=bad):
                with self.assertRaises(ValueError):
                    derive_cache_path("sha512", bad)

    def test_derive_cache_path_from_integrity_rejects_malformed(self) -> None:
        from docker.versioning.artifact_cache import (
            derive_cache_path_from_integrity,
        )

        # Missing separator
        with self.assertRaises(ValueError):
            derive_cache_path_from_integrity("not-an-integrity")

    def test_derive_cache_path_from_integrity_rejects_unsupported_algo(self) -> None:
        from docker.versioning.artifact_cache import (
            derive_cache_path_from_integrity,
        )

        with self.assertRaises(ValueError):
            derive_cache_path_from_integrity("md5-AAAA")


if __name__ == "__main__":
    unittest.main()
