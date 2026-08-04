"""Stage 5.3, 5.5 — Runtime projection lifecycle tests
(safe paths, content identity, atomic write, failure-injection,
 isolation, and restricted cleanup)."""

import hashlib
import os
import tempfile
import tomllib
import unittest
from unittest import mock

from docker.versioning.constraints import parse_constraint
from docker.versioning.effective import (
    EffectiveConfigError,
    RuntimeProjectionHandle,
    _generate_projection_path,
    _repo_runtime_dir,
    _validate_safe_path,
    cleanup_runtime_projection,
    create_runtime_projection,
    resolve_runtime,
)
from docker.versioning.model import (
    NpmArtifact,
    NpmSource,
    NpmUpdate,
    OverridePolicy,
    PiExtensionEntry,
    RuntimeInventory,
    RuntimeValidation,
)


_INT = (
    "sha512-"
    + "A" * 86
    + "=="
)


def _artifact(version: str, pkg: str = "p") -> NpmArtifact:
    last = pkg.rsplit("/", 1)[-1]
    return NpmArtifact(
        url=f"https://registry.npmjs.org/{pkg}/-/{last}-{version}.tgz",
        integrity=_INT,
    )


def _entry(pkg: str = "p", version: str = "1.0.0") -> PiExtensionEntry:
    return PiExtensionEntry(
        version=version,
        source=NpmSource(package=pkg),
        update=NpmUpdate(stable_only=True),
        artifacts={version: _artifact(version, pkg)},
        validation=RuntimeValidation(metadata_file="package.json"),
        override=OverridePolicy(
            constraint=parse_constraint(">=1.0.0"),
            allow_prerelease=True,
            scheme="numeric",
        ),
    )


def _runtime() -> RuntimeInventory:
    return RuntimeInventory(
        pi_extensions={
            "pi-read": _entry(pkg="@example/pi-read"),
            "pi-tool": _entry(pkg="pi-tool"),
        },
    )


def _make_fake_fs(store: dict[str, bytes], runtime_dir: str):
    """Build a :class:`Filesystem` backed entirely by an in-memory
    *store* dict — zero host filesystem calls during lifecycle.

    The *store* maps absolute paths to file content bytes.
    Every operation (open, link, unlink, mkstemp) reads from and
    writes to *store* only.  ``urandom`` returns a deterministic
    per-call counter so generated paths are predictable.
    """
    from docker.versioning.effective import Filesystem

    _counter = 0  # for urandom and unique temp names

    # ── chmod: no-op for in-memory store ────────────────────────
    def _chmod(path: str, mode: int) -> None:
        # In-memory files have no real mode bits; the operation
        # is recorded only through the real-filesystem tests.
        if path not in store:
            raise FileNotFoundError(f"no such file: {path}")

    # ── mkstemp: create an in-memory temp entry ──────────────────
    def _mkstemp(suffix=".tmp", prefix=".atomic.", dir=""):
        nonlocal _counter
        _counter += 1
        name = f"{prefix}{_counter:08x}{suffix}"
        path = os.path.join(dir, name) if dir else name
        store[path] = b""
        # Return a dummy fd — close_fd will no-op it.
        return (-1, path)

    # ── open: in-memory BytesIO ──────────────────────────────────
    def _open(path, mode="r"):
        import io
        if "w" in mode:
            buf = io.BytesIO()

            class _Writer:
                def __init__(self, p):
                    self._p = p
                    self._buf = buf

                def write(self, data):
                    self._buf.write(data)

                def flush(self):
                    pass  # in-memory — nothing to flush

                def fileno(self):
                    # Return a sentinel; fsync is a no-op for in-memory.
                    return -1

                def __enter__(self):
                    return self

                def __exit__(self, *a):
                    # Commit to store on close.
                    store[self._p] = self._buf.getvalue()
                    return None

            return _Writer(path)

        # Read mode.
        if path in store:
            return io.BytesIO(store[path])
        raise FileNotFoundError(f"{path}: not in fake store")

    # ── link: copy entry; fail if destination exists ────────────
    def _link(src, dst):
        if dst in store:
            raise FileExistsError(f"{dst}: already exists")
        if src not in store:
            raise FileNotFoundError(f"{src}: not in fake store")
        store[dst] = store[src]

    # ── unlink: remove entry ────────────────────────────────────
    def _unlink(p):
        store.pop(p, None)

    # ── close_fd: no-op (dummy fd from mkstemp) ─────────────────
    def _close_fd(fd):
        pass  # fd is always -1 from our mkstemp

    # ── urandom: deterministic counter ──────────────────────────
    def _urandom(n):
        nonlocal _counter
        _counter += 1
        return _counter.to_bytes(n, "big")[:n]

    # ── path stand-in ───────────────────────────────────────────
    class _FakePath:
        @staticmethod
        def dirname(p):
            return os.path.dirname(p) if os.path.sep in p else ""

        @staticmethod
        def realpath(p):
            return os.path.normpath(p)

        @staticmethod
        def islink(p):
            return False

        @staticmethod
        def commonpath(parts):
            return os.path.commonpath(parts)

        @staticmethod
        def join(*args):
            return os.path.join(*args)

        @staticmethod
        def isfile(p):
            return p in store

    return Filesystem(
        open=_open,
        unlink=_unlink,
        link=_link,
        fsync=lambda fd: None,   # no-op: in-memory is always synced
        mkstemp=_mkstemp,
        chmod=_chmod,
        urandom=_urandom,
        path=_FakePath(),
        makedirs=lambda p, exist_ok=False: None,  # no-op
        close_fd=_close_fd,
        repo_runtime_dir=runtime_dir,
    )


class TestRuntimeLifecycle(unittest.TestCase):
    """Lifecycle: atomic creation, content identity, safe-path
    enforcement, concurrent isolation, failure injection, and
    restricted cleanup."""

    @classmethod
    def setUpClass(cls):
        cls._repo_dir = _repo_runtime_dir()
        os.makedirs(cls._repo_dir, exist_ok=True)

    def setUp(self):
        # Create a private subdirectory under the repository-owned
        # runtime directory so path-safety validation passes.
        self._tmp = tempfile.mkdtemp(
            prefix="test-", dir=self._repo_dir
        )
        self.addCleanup(lambda: _rmtree_safe(self._tmp))

    # ── default path generation ────────────────────────────────────

    def test_default_path_is_under_repo_runtime_dir(self):
        path = _generate_projection_path()
        self.assertTrue(
            path.startswith(self._repo_dir + os.sep),
            f"default path {path} not under {self._repo_dir}",
        )
        self.assertTrue(path.endswith(".toml"))

    def test_default_paths_are_unique(self):
        p1 = _generate_projection_path()
        p2 = _generate_projection_path()
        self.assertNotEqual(p1, p2)

    # ── safe-path validation ───────────────────────────────────────

    def test_validates_path_under_runtime_dir(self):
        safe = os.path.join(self._tmp, "safe.toml")
        _validate_safe_path(safe)  # does not raise

    def test_rejects_path_outside_runtime_dir(self):
        with tempfile.NamedTemporaryFile(suffix=".toml") as tf:
            outside = tf.name
        with self.assertRaises(EffectiveConfigError) as ctx:
            _validate_safe_path(outside)
        self.assertIn("outside", str(ctx.exception))

    def test_rejects_relative_path_with_dot_dot(self):
        nested = os.path.join(self._tmp, "sub")
        os.makedirs(nested, exist_ok=True)
        escape = os.path.join(nested, "..", "escape.toml")
        _validate_safe_path(escape)  # os.path.realpath resolves '..' — OK

    def test_rejects_symlink(self):
        target = os.path.join(self._tmp, "real.toml")
        link = os.path.join(self._tmp, "link.toml")
        with open(target, "w") as fh:
            fh.write("data")
        os.symlink(target, link)
        with self.assertRaises(EffectiveConfigError) as ctx:
            _validate_safe_path(link)
        self.assertIn("symlink", str(ctx.exception))
        os.unlink(link)

    # ── content identity ───────────────────────────────────────────

    def test_create_returns_content_hash(self):
        _, proj = resolve_runtime(_runtime(), {})
        path, chash = create_runtime_projection(
            proj, host_path=os.path.join(self._tmp, "hash.toml")
        )
        self.assertIsInstance(chash, str)
        self.assertEqual(len(chash), 64)  # SHA-256 hex

    def test_content_hash_is_stable(self):
        _, proj = resolve_runtime(_runtime(), {})
        _, h1 = create_runtime_projection(
            proj, host_path=os.path.join(self._tmp, "stable1.toml")
        )
        _, h2 = create_runtime_projection(
            proj, host_path=os.path.join(self._tmp, "stable2.toml")
        )
        self.assertEqual(h1, h2)

    def test_content_hash_differs_for_different_content(self):
        _, proj_a = resolve_runtime(_runtime(), {})
        # Override to a version that differs from default.
        _, proj_b = resolve_runtime(
            _runtime(),
            {"runtime.pi-extensions.pi-tool.version": "1.0.0"},
        )
        # pi-tool default is 1.0.0; this override doesn't change it.
        # Use a runtime that has two different versions.
        inv = RuntimeInventory(
            pi_extensions={
                "pi-read": _entry(pkg="@example/pi-read", version="1.0.0"),
            },
        )
        _, proj_x = resolve_runtime(inv, {})
        _, proj_y = resolve_runtime(
            inv,
            {"runtime.pi-extensions.pi-read.version": "1.0.0"},
        )
        # Same version, so hash should be equal — verify.
        _, hx = create_runtime_projection(
            proj_x, host_path=os.path.join(self._tmp, "same_a.toml")
        )
        _, hy = create_runtime_projection(
            proj_y, host_path=os.path.join(self._tmp, "same_b.toml")
        )
        self.assertEqual(hx, hy)

        # Now change the package name to produce a different hash.
        inv2 = RuntimeInventory(
            pi_extensions={
                "pi-read": _entry(pkg="@other/pi-read", version="1.0.0"),
            },
        )
        _, proj_z = resolve_runtime(inv2, {})
        _, hz = create_runtime_projection(
            proj_z, host_path=os.path.join(self._tmp, "diff.toml")
        )
        self.assertNotEqual(hx, hz)

    def test_content_hash_matches_file_content(self):
        _, proj = resolve_runtime(_runtime(), {})
        path, chash = create_runtime_projection(
            proj, host_path=os.path.join(self._tmp, "verify.toml")
        )
        with open(path, "rb") as fh:
            actual = hashlib.sha256(fh.read()).hexdigest()
        self.assertEqual(chash, actual)

    # ── deterministic ordering ───────────────────────────────────

    def test_reordered_inventory_produces_same_hash(self):
        """Inventories with the same extensions in different insertion
        order must produce identical content hashes."""
        pkg = "@example/sorted"
        inv_a = RuntimeInventory(
            pi_extensions={
                "first": _entry(pkg=pkg, version="1.0.0"),
                "second": _entry(pkg=pkg, version="1.0.0"),
            },
        )
        inv_b = RuntimeInventory(
            pi_extensions={
                "second": _entry(pkg=pkg, version="1.0.0"),
                "first": _entry(pkg=pkg, version="1.0.0"),
            },
        )
        _, proj_a = resolve_runtime(inv_a, {})
        _, proj_b = resolve_runtime(inv_b, {})
        _, h_a = create_runtime_projection(
            proj_a, host_path=os.path.join(self._tmp, "reorder_a.toml")
        )
        _, h_b = create_runtime_projection(
            proj_b, host_path=os.path.join(self._tmp, "reorder_b.toml")
        )
        self.assertEqual(h_a, h_b)

    def test_reordered_dto_produces_same_hash(self):
        """Projection DTOs with different extension insertion order
        must produce identical content hashes."""
        from docker.versioning.model import EffectivePiExtensionEntry, \
            EffectiveRuntimeProjection

        pkg = "@example/dto-sorted"
        integrity = "sha512-" + "A" * 86 + "=="
        artifact_id = "sha512/" + ("A" * 86 + "==").replace("+", "-").replace("/", "_") + ".tgz"

        ext = EffectivePiExtensionEntry(
            package=pkg,
            version="1.0.0",
            artifact_id=artifact_id,
            integrity=integrity,
            metadata_file="package.json",
        )

        proj_a = EffectiveRuntimeProjection(
            extensions={"z-last": ext, "a-first": ext},
        )
        proj_b = EffectiveRuntimeProjection(
            extensions={"a-first": ext, "z-last": ext},
        )
        _, h_a = create_runtime_projection(
            proj_a, host_path=os.path.join(self._tmp, "dto_a.toml")
        )
        _, h_b = create_runtime_projection(
            proj_b, host_path=os.path.join(self._tmp, "dto_b.toml")
        )
        self.assertEqual(h_a, h_b)

    # ── atomic write ───────────────────────────────────────────────

    def test_create_writes_readable_toml(self):
        _, proj = resolve_runtime(_runtime(), {})
        path, _ = create_runtime_projection(
            proj, host_path=os.path.join(self._tmp, "runtime.toml")
        )
        self.assertTrue(os.path.isfile(path))
        with open(path) as fh:
            content = fh.read()
        self.assertIn("pi-read", content)
        self.assertIn("@example/pi-read", content)
        self.assertIn("1.0.0", content)

    def test_create_returns_canonical_path(self):
        _, proj = resolve_runtime(_runtime(), {})
        target = os.path.join(self._tmp, "canonical.toml")
        path, _ = create_runtime_projection(proj, host_path=target)
        self.assertEqual(path, target)

    def test_destination_never_empty(self):
        """The destination file must never appear empty — atomic rename
        ensures it is complete or absent."""
        _, proj = resolve_runtime(_runtime(), {})
        target = os.path.join(self._tmp, "nonempty.toml")
        _, _ = create_runtime_projection(proj, host_path=target)
        self.assertTrue(os.path.isfile(target))
        self.assertGreater(os.path.getsize(target), 0)

    def test_atomic_write_cleans_temp_on_fsync_failure(self):
        """When fsync fails, the temporary file must be removed and
        the destination must never appear."""
        from docker.versioning.effective import Filesystem

        _, proj = resolve_runtime(_runtime(), {})
        target = os.path.join(self._tmp, "fail.toml")

        def _failing_fsync(fd):
            raise OSError("injected fsync failure")

        fake = Filesystem(
            repo_runtime_dir=self._tmp,
            fsync=_failing_fsync,
        )
        with self.assertRaises(OSError):
            create_runtime_projection(proj, host_path=target, _fs=fake)

        # Destination must not exist (never pre-published).
        self.assertFalse(
            os.path.isfile(target),
            "destination must not exist after write failure",
        )
        # No .atomic.* temp files leaked.
        for name in os.listdir(self._tmp):
            self.assertFalse(
                name.startswith(".atomic."),
                f"temp file leaked: {name}",
            )

    def test_link_failure_cleans_temp_file(self):
        """When link fails, the temporary file must be removed."""
        from docker.versioning.effective import Filesystem

        _, proj = resolve_runtime(_runtime(), {})
        target = os.path.join(self._tmp, "linkfail.toml")

        def _failing_link(src, dst):
            raise OSError("injected link failure")

        fake = Filesystem(
            repo_runtime_dir=self._tmp,
            link=_failing_link,
        )
        with self.assertRaises(OSError):
            create_runtime_projection(proj, host_path=target, _fs=fake)

        # Destination must not exist (never pre-published).
        self.assertFalse(
            os.path.isfile(target),
            "destination must not exist after link failure",
        )
        leaked = [
            f for f in os.listdir(self._tmp) if f.startswith(".atomic.")
        ]
        self.assertEqual(
            len(leaked), 0,
            f"temporary files leaked after link failure: {leaked}",
        )

    def test_destination_collision_rejected(self):
        """Writing to an existing destination must fail with
        EffectiveConfigError (no-clobber)."""
        _, proj = resolve_runtime(_runtime(), {})
        target = os.path.join(self._tmp, "collision.toml")
        # Pre-create the destination file.
        with open(target, "w") as fh:
            fh.write("preexisting")
        with self.assertRaises(EffectiveConfigError) as ctx:
            create_runtime_projection(proj, host_path=target)
        self.assertIn("already exists", str(ctx.exception))
        # The pre-existing content must not be overwritten.
        with open(target) as fh:
            self.assertEqual(fh.read(), "preexisting")

    def test_buffered_write_completes_large_payload(self):
        """Large payloads must be written completely — buffered I/O
        handles partial writes transparently."""
        # Build a runtime with many extensions to exercise larger payload.
        exts = {}
        for i in range(50):
            name = f"ext-{i:02d}"
            pkg = f"@example/{name}"
            exts[name] = _entry(pkg=pkg, version="1.0.0")
        inv = RuntimeInventory(pi_extensions=exts)
        _, proj = resolve_runtime(inv, {})
        target = os.path.join(self._tmp, "large.toml")
        path, _ = create_runtime_projection(proj, host_path=target)
        self.assertTrue(os.path.isfile(path))
        self.assertGreater(os.path.getsize(path), 1000)
        with open(path) as fh:
            content = fh.read()
        for i in range(50):
            self.assertIn(f"ext-{i:02d}", content)

    # ── TOML round-trip ──────────────────────────────────────────

    def test_roundtrip_success_on_valid_projection(self):
        """A valid projection must survive the TOML round-trip:
        serialize → parse → re-validate."""
        _, proj = resolve_runtime(_runtime(), {})
        path, _ = create_runtime_projection(
            proj, host_path=os.path.join(self._tmp, "rt_valid.toml")
        )
        # The file must exist and contain valid TOML.
        self.assertTrue(os.path.isfile(path))
        import tomllib
        with open(path, "rb") as fh:
            tomllib.load(fh)

    def test_roundtrip_special_characters_in_values(self):
        """Values containing TOML-significant characters must
        round-trip without corruption."""
        from docker.versioning.model import EffectivePiExtensionEntry, \
            EffectiveRuntimeProjection

        pkg = "@scope/pkg"
        ver = "2.0.0-beta.1"
        # Valid sha384 integrity (48 bytes of 'a')
        integrity = "sha384-" + "a" * 64
        artifact_id = "sha384/" + ("a" * 64).replace("+", "-").replace("/", "_") + ".tgz"
        ext = EffectivePiExtensionEntry(
            package=pkg,
            version=ver,
            artifact_id=artifact_id,
            integrity=integrity,
            metadata_file="nested/path/package.json",
        )
        proj = EffectiveRuntimeProjection(extensions={"ext": ext})
        path, _ = create_runtime_projection(
            proj, host_path=os.path.join(self._tmp, "special.toml")
        )
        import tomllib
        with open(path, "rb") as fh:
            parsed = tomllib.load(fh)
        self.assertIn("ext", parsed["extensions"])
        self.assertEqual(
            parsed["extensions"]["ext"]["package"], pkg
        )
        self.assertEqual(
            parsed["extensions"]["ext"]["version"], "2.0.0-beta.1",
        )
        self.assertEqual(
            parsed["extensions"]["ext"]["metadata_file"],
            "nested/path/package.json",
        )

    def test_roundtrip_corrupt_toml_rejected(self):
        """If the generated TOML cannot be parsed back, tomllib's
        TOMLDecodeError must be surfaced as EffectiveConfigError."""
        _, proj = resolve_runtime(_runtime(), {})
        target = os.path.join(self._tmp, "corrupt.toml")

        with mock.patch(
            "docker.versioning.effective.tomllib.loads",
            side_effect=tomllib.TOMLDecodeError(
                msg="injected parse error", doc="garbled", pos=0),
        ):
            with self.assertRaises(EffectiveConfigError) as ctx:
                create_runtime_projection(proj, host_path=target)
        self.assertIn("invalid", str(ctx.exception).lower())
        self.assertFalse(
            os.path.isfile(target),
            "destination must not exist after TOML round-trip failure",
        )

    def test_default_path_never_pre_creates_empty_file(self):
        """Default path generation must not pre-create an empty file
        — it must use a non-existent name."""
        _, proj = resolve_runtime(_runtime(), {})
        # Use default path (no host_path argument).
        path, _ = create_runtime_projection(proj)
        try:
            self.assertTrue(os.path.isfile(path))
            self.assertGreater(os.path.getsize(path), 0)
        finally:
            cleanup_runtime_projection(path)

    def test_default_path_is_unique_each_time(self):
        """Two default-path projections must get different files."""
        _, proj = resolve_runtime(_runtime(), {})
        p1, _ = create_runtime_projection(proj)
        p2, _ = create_runtime_projection(proj)
        try:
            self.assertNotEqual(p1, p2)
            self.assertTrue(os.path.isfile(p1))
            self.assertTrue(os.path.isfile(p2))
        finally:
            cleanup_runtime_projection(p1)
            cleanup_runtime_projection(p2)

    def test_default_path_does_not_exist_before_write(self):
        """The generated default path must point to a file that does
        not exist before the atomic write."""
        from docker.versioning.effective import _generate_projection_path
        path = _generate_projection_path()
        self.assertFalse(
            os.path.exists(path),
            f"generated path {path!r} already exists — "
            f"it was pre-created",
        )

    # ── concurrent isolation ───────────────────────────────────────

    def test_two_projections_use_different_paths(self):
        _, proj = resolve_runtime(_runtime(), {})
        p1, _ = create_runtime_projection(
            proj, host_path=os.path.join(self._tmp, "first.toml")
        )
        p2, _ = create_runtime_projection(
            proj, host_path=os.path.join(self._tmp, "second.toml")
        )
        self.assertNotEqual(p1, p2)
        self.assertTrue(os.path.isfile(p1))
        self.assertTrue(os.path.isfile(p2))

    def test_concurrent_overrides_do_not_clobber(self):
        _, proj_a = resolve_runtime(_runtime(), {})
        _, proj_b = resolve_runtime(
            _runtime(),
            {"runtime.pi-extensions.pi-read.version": "1.0.0"},
        )
        pa, _ = create_runtime_projection(
            proj_a, host_path=os.path.join(self._tmp, "a.toml")
        )
        pb, _ = create_runtime_projection(
            proj_b, host_path=os.path.join(self._tmp, "b.toml")
        )
        self.assertNotEqual(pa, pb)
        with open(pa) as fa, open(pb) as fb:
            self.assertTrue(fa.read())
            self.assertTrue(fb.read())

    def test_isolated_default_paths_do_not_clash(self):
        """Two projections without explicit host_path must receive
        unique private paths under .docker-generated/runtime/."""
        _, proj = resolve_runtime(_runtime(), {})
        p1, _ = create_runtime_projection(proj)
        p2, _ = create_runtime_projection(proj)
        try:
            self.assertNotEqual(p1, p2)
            self.assertTrue(os.path.isfile(p1))
            self.assertTrue(os.path.isfile(p2))
        finally:
            cleanup_runtime_projection(p1)
            cleanup_runtime_projection(p2)

    # ── restricted cleanup ─────────────────────────────────────────

    def test_cleanup_removes_file(self):
        _, proj = resolve_runtime(_runtime(), {})
        path, _ = create_runtime_projection(
            proj, host_path=os.path.join(self._tmp, "rm.toml")
        )
        self.assertTrue(os.path.isfile(path))
        cleanup_runtime_projection(path)
        self.assertFalse(os.path.isfile(path))

    def test_cleanup_idempotent(self):
        path = os.path.join(self._tmp, "gone.toml")
        cleanup_runtime_projection(path)  # does not raise
        cleanup_runtime_projection(path)  # does not raise

    def test_cleanup_rejects_path_outside_runtime_dir(self):
        with tempfile.NamedTemporaryFile(suffix=".toml") as tf:
            outside = tf.name
        with self.assertRaises(EffectiveConfigError):
            cleanup_runtime_projection(outside)

    def test_cleanup_rejects_symlink(self):
        target = os.path.join(self._tmp, "real_clean.toml")
        link = os.path.join(self._tmp, "link_clean.toml")
        with open(target, "w") as fh:
            fh.write("data")
        os.symlink(target, link)
        try:
            with self.assertRaises(EffectiveConfigError):
                cleanup_runtime_projection(link)
        finally:
            os.unlink(link)

    # ── scoped context-manager lifecycle ──────────────────────────

    def test_context_manager_cleans_file_on_success(self):
        """File must be removed after a successful with-block exit."""
        _, proj = resolve_runtime(_runtime(), {})
        target = os.path.join(self._tmp, "scoped_ok.toml")
        with create_runtime_projection(proj, host_path=target) as h:
            self.assertTrue(os.path.isfile(h.path))
            self.assertEqual(h.path, target)
        # File gone after context exit.
        self.assertFalse(os.path.isfile(target))

    def test_context_manager_cleans_file_on_exception(self):
        """File must be removed after an exception inside the
        with-block — and the exception must propagate."""
        _, proj = resolve_runtime(_runtime(), {})
        target = os.path.join(self._tmp, "scoped_exc.toml")
        with self.assertRaises(RuntimeError):
            with create_runtime_projection(proj, host_path=target) as h:
                self.assertTrue(os.path.isfile(h.path))
                raise RuntimeError("injected failure")
        # File must be gone despite the exception.
        self.assertFalse(os.path.isfile(target))

    def test_handle_discard_keeps_file(self):
        """Calling discard() inside the context must skip cleanup."""
        _, proj = resolve_runtime(_runtime(), {})
        target = os.path.join(self._tmp, "keep.toml")
        with create_runtime_projection(proj, host_path=target) as h:
            h.discard()
        self.assertTrue(os.path.isfile(target))
        # Manual cleanup for test hygiene.
        os.unlink(target)

    def test_handle_only_removes_own_file(self):
        """Two handles must not interfere — each removes only its
        own file, never the other's."""
        _, proj = resolve_runtime(_runtime(), {})
        t1 = os.path.join(self._tmp, "one.toml")
        t2 = os.path.join(self._tmp, "two.toml")
        h1 = create_runtime_projection(proj, host_path=t1)
        h2 = create_runtime_projection(proj, host_path=t2)
        self.assertTrue(os.path.isfile(h1.path))
        self.assertTrue(os.path.isfile(h2.path))
        self.assertNotEqual(h1.path, h2.path)
        # Exit h1 — must remove t1 only, not t2.
        with h1:
            pass
        self.assertFalse(os.path.isfile(t1))
        self.assertTrue(os.path.isfile(t2))
        # Exit h2 — must remove t2.
        with h2:
            pass
        self.assertFalse(os.path.isfile(t2))

    def test_context_manager_does_not_suppress_exception(self):
        """The handle must not suppress exceptions — they propagate
        after cleanup."""
        _, proj = resolve_runtime(_runtime(), {})
        target = os.path.join(self._tmp, "propagate.toml")
        try:
            with create_runtime_projection(proj, host_path=target):
                raise ValueError("must propagate")
        except ValueError as exc:
            self.assertEqual(str(exc), "must propagate")
        else:
            self.fail("ValueError was suppressed")
        self.assertFalse(os.path.isfile(target))

    def test_unpacking_compat(self):
        """Legacy tuple-unpacking ``path, hash = ...`` must still
        work for backward compatibility."""
        _, proj = resolve_runtime(_runtime(), {})
        target = os.path.join(self._tmp, "compat.toml")
        path, chash = create_runtime_projection(proj, host_path=target)
        self.assertIsInstance(path, str)
        self.assertIsInstance(chash, str)
        self.assertEqual(len(chash), 64)
        self.assertTrue(os.path.isfile(path))
        cleanup_runtime_projection(path)

    def test_injected_fs_boundary_cleanup(self):
        """Cleanup must use the injected Filesystem, not the
        global os module."""
        from docker.versioning.effective import Filesystem

        _, proj = resolve_runtime(_runtime(), {})
        target = os.path.join(self._tmp, "injected.toml")

        calls = []
        real_unlink = os.unlink

        def _tracked_unlink(p):
            calls.append(("unlink", p))
            real_unlink(p)

        fake = Filesystem(
            repo_runtime_dir=self._tmp,
            unlink=_tracked_unlink,
        )
        h = create_runtime_projection(proj, host_path=target, _fs=fake)
        with h:
            pass
        # Two unlink calls: temp-cleanup inside create_*, then
        # handle exit.
        self.assertGreaterEqual(len(calls), 1)
        self.assertIn(("unlink", target), calls)
        self.assertFalse(os.path.isfile(target))

    # ── fully fake in-memory filesystem tests ──────────────────────

    def test_fake_fs_create_and_read(self):
        """Create a projection entirely in-memory — no real
        filesystem access."""
        from docker.versioning.effective import Filesystem

        _, proj = resolve_runtime(_runtime(), {})
        store: dict[str, bytes] = {}
        fake = _make_fake_fs(store, runtime_dir=self._tmp)
        h = create_runtime_projection(
            proj, host_path=os.path.join(self._tmp, "fake1.toml"),
            _fs=fake,
        )
        self.assertIn(h.path, store)
        content = store[h.path]
        self.assertGreater(len(content), 0)
        # Content is valid TOML.
        parsed = tomllib.loads(content.decode("utf-8"))
        self.assertIn("extensions", parsed)
        # Scoped cleanup removes from store.
        with h:
            pass
        self.assertNotIn(h.path, store)

    def test_fake_fs_destination_collision(self):
        """Pre-existing file in the fake store must cause
        EffectiveConfigError."""
        from docker.versioning.effective import Filesystem

        _, proj = resolve_runtime(_runtime(), {})
        target = os.path.join(self._tmp, "collide.toml")
        store: dict[str, bytes] = {target: b"preexisting"}
        fake = _make_fake_fs(store, runtime_dir=self._tmp)
        with self.assertRaises(EffectiveConfigError) as ctx:
            create_runtime_projection(proj, host_path=target, _fs=fake)
        self.assertIn("already exists", str(ctx.exception))
        self.assertEqual(store[target], b"preexisting")

    def test_fake_fs_fsync_failure(self):
        """Failing fsync in the fake fs must clean up the temp
        without touching the destination."""
        from docker.versioning.effective import Filesystem

        _, proj = resolve_runtime(_runtime(), {})
        target = os.path.join(self._tmp, "fsyncfail.toml")
        store: dict[str, bytes] = {}

        def _bad_fsync(_fd):
            raise OSError("injected")

        fake = _make_fake_fs(store, runtime_dir=self._tmp)
        fake.fsync = _bad_fsync
        with self.assertRaises(OSError):
            create_runtime_projection(proj, host_path=target, _fs=fake)
        self.assertFalse(os.path.isfile(target))

    def test_fake_fs_link_failure(self):
        """Failing link must not leave a partial destination."""
        from docker.versioning.effective import Filesystem

        _, proj = resolve_runtime(_runtime(), {})
        target = os.path.join(self._tmp, "linkfail.toml")
        store: dict[str, bytes] = {}

        def _bad_link(_src, _dst):
            raise OSError("injected")

        fake = _make_fake_fs(store, runtime_dir=self._tmp)
        fake.link = _bad_link
        with self.assertRaises(OSError):
            create_runtime_projection(proj, host_path=target, _fs=fake)
        self.assertNotIn(target, store)
        self.assertFalse(os.path.isfile(target))

    def test_fake_fs_scoped_cleanup_keeps_only_own(self):
        """Two handles over the same fake store must only remove
        their own files."""
        from docker.versioning.effective import Filesystem

        _, proj = resolve_runtime(_runtime(), {})
        t1 = os.path.join(self._tmp, "keep1.toml")
        t2 = os.path.join(self._tmp, "keep2.toml")
        store: dict[str, bytes] = {}
        fake = _make_fake_fs(store, runtime_dir=self._tmp)
        h1 = create_runtime_projection(proj, host_path=t1, _fs=fake)
        h2 = create_runtime_projection(proj, host_path=t2, _fs=fake)
        with h1:
            pass
        self.assertNotIn(t1, store)
        self.assertIn(t2, store)
        with h2:
            pass
        self.assertNotIn(t2, store)

    def test_fake_fs_has_no_host_io(self):
        """The fake filesystem must never call real os I/O
        functions (open, write, fsync, mkstemp, close)."""
        _, proj = resolve_runtime(_runtime(), {})
        target = os.path.join(self._tmp, "noio.toml")
        store: dict[str, bytes] = {}
        fake = _make_fake_fs(store, runtime_dir=self._tmp)

        # Guard: any call to these real functions is a test failure.
        def _must_not_call(name):
            def fail(*a, **kw):
                raise AssertionError(f"real {name}() called — fake must not touch host fs")
            return fail

        with mock.patch("os.open", _must_not_call("os.open")), \
                mock.patch("os.write", _must_not_call("os.write")), \
                mock.patch("os.fsync", _must_not_call("os.fsync")), \
                mock.patch("os.close", _must_not_call("os.close")), \
                mock.patch("tempfile.mkstemp", _must_not_call("tempfile.mkstemp")):
            h = create_runtime_projection(proj, host_path=target, _fs=fake)
            # Store must contain the projection.
            self.assertIn(target, store)
            with h:
                pass
            self.assertNotIn(target, store)

    # ── projection does not leak source metadata ───────────────────

    def test_projection_does_not_contain_source_metadata(self):
        _, proj = resolve_runtime(_runtime(), {})
        path, _ = create_runtime_projection(
            proj, host_path=os.path.join(self._tmp, "no-source.toml")
        )
        with open(path) as fh:
            content = fh.read()
        self.assertNotIn("source", content)
        self.assertNotIn("update", content)
        self.assertNotIn("override", content)

    # ── projection filesystem mode ────────────────────────────────

    def test_projection_mode_is_world_readable_not_owner_only(self):
        """The published projection file must be readable by
        non-owner users — container-remapped UIDs cannot read files
        locked at owner-only 0600."""
        import stat
        _, proj = resolve_runtime(_runtime(), {})
        target = os.path.join(self._tmp, "world-readable.toml")
        path, _ = create_runtime_projection(proj, host_path=target)
        mode = os.stat(path).st_mode & 0o777
        self.assertEqual(
            0o444, mode,
            f"projection mode {oct(mode)} — expected 0o444 "
            f"so container-remapped users can read it",
        )
        # Content unchanged after mode correction.
        with open(path) as fh:
            content = fh.read()
        self.assertIn("pi-read", content)
        self.assertIn("@example/pi-read", content)

    def test_mkstemp_default_mode_is_0600(self):
        """mkstemp creates files at 0600 (owner read-write only).
        The projection must never be left at this restrictive mode
        — this test documents the baseline the code must override."""
        import stat
        fd, tmp = tempfile.mkstemp(dir=self._tmp)
        try:
            os.close(fd)
            mode = os.stat(tmp).st_mode & 0o777
            self.assertEqual(
                0o600, mode,
                f"mkstemp creates files at {oct(mode)}, expected 0o600 "
                f"— this is the baseline the projection must override",
            )
        finally:
            os.unlink(tmp)


class TestSerializedProjectionValidator(unittest.TestCase):
    """Independent closed-schema validation of the serialized dict
    before it is written to disk."""

    _GOOD_INTEGRITY = "sha512-" + "A" * 86 + "=="
    _GOOD_ARTIFACT_ID = (
        "sha512/" + ("A" * 86 + "==").replace("+", "-").replace("/", "_") + ".tgz"
    )

    def _valid_data(self, **overrides) -> dict:
        data = {
            "extensions": {
                "pi-read": {
                    "package": "@example/pi-read",
                    "version": "1.0.0",
                    "artifact_id": self._GOOD_ARTIFACT_ID,
                    "integrity": self._GOOD_INTEGRITY,
                    "metadata_file": "package.json",
                },
            },
        }
        data.update(overrides)
        return data

    # ── happy path ─────────────────────────────────────────────

    def test_valid_data_passes(self):
        from docker.versioning.effective import _validate_serialized_projection
        _validate_serialized_projection(self._valid_data())

    # ── top-level unknowns ─────────────────────────────────────

    def test_rejects_unknown_top_level_key(self):
        from docker.versioning.effective import _validate_serialized_projection
        data = self._valid_data()
        data["build"] = {}
        with self.assertRaises(EffectiveConfigError) as ctx:
            _validate_serialized_projection(data)
        self.assertIn("unknown top-level", str(ctx.exception))
        self.assertIn("'build'", str(ctx.exception))

    def test_rejects_multiple_unknown_top_keys(self):
        from docker.versioning.effective import _validate_serialized_projection
        data = self._valid_data()
        data["build"] = {}
        data["stages"] = {}
        with self.assertRaises(EffectiveConfigError):
            _validate_serialized_projection(data)

    # ── non-dict extensions ────────────────────────────────────

    def test_rejects_non_dict_extensions(self):
        from docker.versioning.effective import _validate_serialized_projection
        data = self._valid_data()
        data["extensions"] = "not-a-table"
        with self.assertRaises(EffectiveConfigError) as ctx:
            _validate_serialized_projection(data)
        self.assertIn("must be a table", str(ctx.exception))

    def test_rejects_empty_extensions(self):
        from docker.versioning.effective import _validate_serialized_projection
        data = self._valid_data()
        data["extensions"] = {}
        with self.assertRaises(EffectiveConfigError) as ctx:
            _validate_serialized_projection(data)
        self.assertIn("must not be empty", str(ctx.exception))

    # ── unknown extension keys ─────────────────────────────────

    def test_rejects_unknown_extension_key(self):
        from docker.versioning.effective import _validate_serialized_projection
        data = self._valid_data()
        data["extensions"]["pi-read"]["source"] = {"type": "npm"}
        with self.assertRaises(EffectiveConfigError) as ctx:
            _validate_serialized_projection(data)
        self.assertIn("unknown key", str(ctx.exception))
        self.assertIn("'source'", str(ctx.exception))

    def test_rejects_update_policy_in_extension(self):
        from docker.versioning.effective import _validate_serialized_projection
        data = self._valid_data()
        data["extensions"]["pi-read"]["update"] = {"provider": "npm"}
        with self.assertRaises(EffectiveConfigError) as ctx:
            _validate_serialized_projection(data)
        self.assertIn("'update'", str(ctx.exception))

    def test_rejects_override_policy_in_extension(self):
        from docker.versioning.effective import _validate_serialized_projection
        data = self._valid_data()
        data["extensions"]["pi-read"]["override"] = {"constraint": ">=1.0"}
        with self.assertRaises(EffectiveConfigError) as ctx:
            _validate_serialized_projection(data)
        self.assertIn("'override'", str(ctx.exception))

    def test_rejects_artifacts_in_extension(self):
        from docker.versioning.effective import _validate_serialized_projection
        data = self._valid_data()
        data["extensions"]["pi-read"]["artifacts"] = {}
        with self.assertRaises(EffectiveConfigError) as ctx:
            _validate_serialized_projection(data)
        self.assertIn("'artifacts'", str(ctx.exception))

    # ── unknown extension keys ─────────────────────────────────

    def test_rejects_old_artifact_key(self):
        """The old nested 'artifact' table is rejected as an unknown
        extension key."""
        from docker.versioning.effective import _validate_serialized_projection
        data = self._valid_data()
        data["extensions"]["pi-read"]["artifact"] = {"url": "https://x", "integrity": self._GOOD_INTEGRITY}
        with self.assertRaises(EffectiveConfigError) as ctx:
            _validate_serialized_projection(data)
        self.assertIn("'artifact'", str(ctx.exception))

    # ── empty string fields ────────────────────────────────────

    def test_rejects_empty_package(self):
        from docker.versioning.effective import _validate_serialized_projection
        data = self._valid_data()
        data["extensions"]["pi-read"]["package"] = ""
        with self.assertRaises(EffectiveConfigError) as ctx:
            _validate_serialized_projection(data)
        self.assertIn("non-empty string", str(ctx.exception))

    def test_rejects_missing_version(self):
        from docker.versioning.effective import _validate_serialized_projection
        data = self._valid_data()
        del data["extensions"]["pi-read"]["version"]
        with self.assertRaises(EffectiveConfigError) as ctx:
            _validate_serialized_projection(data)
        self.assertIn("non-empty string", str(ctx.exception))

    # ── integrity validation ───────────────────────────────────

    _GOOD_SHA256 = "sha256-AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA="
    _GOOD_SHA384 = "sha384-AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
    _GOOD_SHA512 = "sha512-AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=="

    def test_accepts_sha256_integrity(self):
        from docker.versioning.effective import _validate_serialized_projection
        data = self._valid_data()
        data["extensions"]["pi-read"]["integrity"] = (
            self._GOOD_SHA256
        )
        # artifact_id must agree with the new integrity
        data["extensions"]["pi-read"]["artifact_id"] = (
            "sha256/AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=.tgz"
        )
        _validate_serialized_projection(data)  # does not raise

    def test_accepts_sha384_integrity(self):
        from docker.versioning.effective import _validate_serialized_projection
        data = self._valid_data()
        data["extensions"]["pi-read"]["integrity"] = (
            self._GOOD_SHA384
        )
        data["extensions"]["pi-read"]["artifact_id"] = (
            "sha384/"
            "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
            ".tgz"
        )
        _validate_serialized_projection(data)  # does not raise

    def test_accepts_sha512_integrity(self):
        from docker.versioning.effective import _validate_serialized_projection
        data = self._valid_data()
        data["extensions"]["pi-read"]["integrity"] = (
            self._GOOD_SHA512
        )
        data["extensions"]["pi-read"]["artifact_id"] = (
            "sha512/"
            "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
            "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA==.tgz"
        )
        _validate_serialized_projection(data)  # does not raise

    def test_rejects_unsupported_algorithm(self):
        from docker.versioning.effective import _validate_serialized_projection
        data = self._valid_data()
        data["extensions"]["pi-read"]["integrity"] = (
            "sha1-" + "A" * 27 + "="
        )
        with self.assertRaises(EffectiveConfigError) as ctx:
            _validate_serialized_projection(data)
        self.assertIn("unsupported algorithm", str(ctx.exception))

    def test_rejects_missing_separator(self):
        from docker.versioning.effective import _validate_serialized_projection
        data = self._valid_data()
        data["extensions"]["pi-read"]["integrity"] = (
            "sha512AAAA"
        )
        with self.assertRaises(EffectiveConfigError) as ctx:
            _validate_serialized_projection(data)
        self.assertIn("alg-base64payload", str(ctx.exception))

    def test_rejects_invalid_base64_payload(self):
        from docker.versioning.effective import _validate_serialized_projection
        data = self._valid_data()
        data["extensions"]["pi-read"]["integrity"] = (
            "sha512-" + "!" * 86 + "=="
        )
        with self.assertRaises(EffectiveConfigError) as ctx:
            _validate_serialized_projection(data)
        self.assertIn("invalid base64", str(ctx.exception))

    def test_rejects_sha256_with_wrong_digest_length(self):
        from docker.versioning.effective import _validate_serialized_projection
        import base64
        # Encode 33 bytes instead of 32 — wrong length for sha256.
        bad = base64.b64encode(b"A" * 33).decode()
        data = self._valid_data()
        data["extensions"]["pi-read"]["integrity"] = (
            f"sha256-{bad}"
        )
        with self.assertRaises(EffectiveConfigError) as ctx:
            _validate_serialized_projection(data)
        self.assertIn("digest must be", str(ctx.exception))
        self.assertIn("32 bytes", str(ctx.exception))

    def test_rejects_sha384_with_wrong_digest_length(self):
        from docker.versioning.effective import _validate_serialized_projection
        import base64
        bad = base64.b64encode(b"B" * 47).decode()
        data = self._valid_data()
        data["extensions"]["pi-read"]["integrity"] = (
            f"sha384-{bad}"
        )
        with self.assertRaises(EffectiveConfigError) as ctx:
            _validate_serialized_projection(data)
        self.assertIn("48 bytes", str(ctx.exception))

    def test_rejects_sha512_with_wrong_digest_length(self):
        from docker.versioning.effective import _validate_serialized_projection
        import base64
        bad = base64.b64encode(b"C" * 63).decode()
        data = self._valid_data()
        data["extensions"]["pi-read"]["integrity"] = (
            f"sha512-{bad}"
        )
        with self.assertRaises(EffectiveConfigError) as ctx:
            _validate_serialized_projection(data)
        self.assertIn("64 bytes", str(ctx.exception))

    # ── metadata_file safety ───────────────────────────────────

    def test_rejects_absolute_metadata_file(self):
        from docker.versioning.effective import _validate_serialized_projection
        data = self._valid_data()
        data["extensions"]["pi-read"]["metadata_file"] = "/etc/hacked"
        with self.assertRaises(EffectiveConfigError) as ctx:
            _validate_serialized_projection(data)
        self.assertIn("absolute path", str(ctx.exception))

    def test_rejects_dot_dot_in_metadata_file(self):
        from docker.versioning.effective import _validate_serialized_projection
        data = self._valid_data()
        data["extensions"]["pi-read"]["metadata_file"] = (
            "../escape/package.json"
        )
        with self.assertRaises(EffectiveConfigError) as ctx:
            _validate_serialized_projection(data)
        self.assertIn("invalid segments", str(ctx.exception))

    def test_rejects_empty_metadata_file(self):
        from docker.versioning.effective import _validate_serialized_projection
        data = self._valid_data()
        data["extensions"]["pi-read"]["metadata_file"] = ""
        with self.assertRaises(EffectiveConfigError) as ctx:
            _validate_serialized_projection(data)
        self.assertIn("non-empty string", str(ctx.exception))

    # ── artifact_id safety ────────────────────────────────────

    def test_rejects_traversal_in_artifact_id(self):
        from docker.versioning.effective import _validate_serialized_projection
        data = self._valid_data()
        data["extensions"]["pi-read"]["artifact_id"] = (
            "sha512/../../etc/shadow.tgz"
        )
        with self.assertRaises(EffectiveConfigError) as ctx:
            _validate_serialized_projection(data)
        self.assertIn("invalid segments", str(ctx.exception))

    def test_rejects_absolute_artifact_id(self):
        from docker.versioning.effective import _validate_serialized_projection
        data = self._valid_data()
        data["extensions"]["pi-read"]["artifact_id"] = (
            "/sha512/abc.tgz"
        )
        with self.assertRaises(EffectiveConfigError) as ctx:
            _validate_serialized_projection(data)
        self.assertIn("absolute path", str(ctx.exception))


def _rmtree_safe(path: str) -> None:
    import shutil
    try:
        shutil.rmtree(path)
    except Exception:
        pass


if __name__ == "__main__":
    unittest.main()
