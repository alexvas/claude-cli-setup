"""Protected Runtime Extension Installer (Stage 10).

Reads the mounted effective runtime projection
(``/run/pi-cli/docker-constructor.runtime.toml``), verifies artifact
integrity, and installs Pi extensions idempotently into the mounted
Pi home directory.

This module SHALL NOT read:
  - ``docker-constructor.toml`` (reviewed inventory)
  - effective build projection
  - update providers
  - override policy
  - ``docker/versions.py``
"""

from __future__ import annotations

import base64
import binascii
import enum
import hashlib
import hmac
import os
import stat
from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable


# ═══════════════════════════════════════════════════════════════════════
# Mounted artifact lookup (host-side, read-only)
# ═══════════════════════════════════════════════════════════════════════

# Single fixed root for content-addressed artifact blobs materialized on
# the host.  The installer SHALL NOT accept any other root — no env var,
# no constructor argument, no projection field.
_MOUNTED_ARTIFACT_ROOT: str = "/run/pi-cli/runtime-artifacts"


def _mounted_artifact_path(artifact_id: str) -> str:
    """Return the absolute host path for *artifact_id* under the
    single fixed :data:`_MOUNTED_ARTIFACT_ROOT`.

    The result is ``<root>/<artifact_id>``.  *artifact_id* MUST
    be a relative, non-traversal path matching the canonical
    ``<algo>/<digest>.tgz`` form.  Any violation — absolute path,
    ``..`` component, empty string — raises :class:`ProjectionError`
    before touching the filesystem.
    """
    if not artifact_id:
        raise ProjectionError("artifact_id must not be empty")
    if os.path.isabs(artifact_id):
        raise ProjectionError(
            f"artifact_id must be relative, got {artifact_id!r}",
        )
    # Reject ".." as a path component (normalised or not).
    parts = artifact_id.split(os.sep)
    if ".." in parts:
        raise ProjectionError(
            f"artifact_id must not contain '..': {artifact_id!r}",
        )
    # Reject a leading ".." without a separator ("../etc").
    if artifact_id.startswith(".."):
        raise ProjectionError(
            f"artifact_id must not start with '..': {artifact_id!r}",
        )
    return os.path.join(_MOUNTED_ARTIFACT_ROOT, artifact_id)


@runtime_checkable
class MountedBlobReader(Protocol):
    """Read-only, verified access to a materialized artifact blob.

    Implementations SHALL: derive the blob path from the single
    fixed root, open the file with ``O_NOFOLLOW``, verify the
    integrity digest against the streamed bytes, and return the
    complete blob contents as :class:`bytes`.  Any failure —
    missing blob, symlink, wrong permissions, digest mismatch —
    SHALL raise :class:`InstallError`.
    """

    def open_verified(
        self, *, artifact_id: str, integrity: str,
    ) -> bytes:
        """Open, verify, and return the blob identified by
        *artifact_id* and *integrity*.

        The caller SHALL NOT supply a root — the implementation
        uses :data:`_MOUNTED_ARTIFACT_ROOT` exclusively.
        """
        ...


class _MountInspection(Protocol):
    """Inspect whether a path resides on a read-only filesystem
    mount (bind-mount or otherwise).  Checking only Unix permission
    bits on the blob is insufficient — a ``0o600`` file on a
    writable mount can still be mutated by its owner."""

    def is_read_only_mount(self, path: str) -> bool:
        """Return ``True`` if *path* is on a read-only mount."""
        ...


class _StatvfsMountInspection:
    """Production mount inspection using :func:`os.statvfs`.

    Checks ``ST_RDONLY`` in the filesystem flags for the mount
    containing *path*."""

    def is_read_only_mount(self, path: str) -> bool:
        try:
            flags = os.statvfs(path).f_flag
        except OSError:
            return False
        return bool(flags & os.ST_RDONLY)


class RuntimeArtifactReader:
    """Production :class:`MountedBlobReader` that reads
    materialized blobs from :data:`_MOUNTED_ARTIFACT_ROOT`.

    Accepts an optional *mount_inspection* boundary for testing;
    the production default uses :class:`_StatvfsMountInspection`.
    """

    def __init__(
        self,
        *,
        mount_inspection: _MountInspection | None = None,
    ) -> None:
        self._mount_inspection: _MountInspection = (
            mount_inspection or _StatvfsMountInspection()
        )

    def open_verified(
        self, *, artifact_id: str, integrity: str,
    ) -> bytes:
        """Open, verify, and return the blob at the fixed root.

        Order of checks (task 7.3):

        1. Derive and validate *artifact_id* → path.
        2. Reject identity/integrity mismatch.
        3. **Reject writable mount** — the blob path MUST reside
           on a read-only filesystem, not just have restrictive
           permission bits.
        4. Open with ``O_NOFOLLOW``, verify regular file +
           owner-only permissions, stream through SRI digest,
           compare, return exact bytes.
        """
        _path = _mounted_artifact_path(artifact_id)
        # identity agreement will go here (task 7.2 / 7.3)
        # mount check will go here:
        #   if not self._mount_inspection.is_read_only_mount(_path):
        #       raise InstallError("artifact mount is not read-only")
        raise NotImplementedError(
            "RuntimeArtifactReader.open_verified — "
            "production implementation pending (task 7.3)"
        )


# ═══════════════════════════════════════════════════════════════════════
# Shared URL identity validator
# ═══════════════════════════════════════════════════════════════════════


def validate_npm_tarball_url(url: str, package: str, version: str) -> None:
    """Validate *url* against the npm tarball identity contract.

    Delegates to the shared canonical implementation in
    :mod:`docker.versioning.npm_tarball`, then maps
    :class:`~docker.versioning.npm_tarball.NpmTarballUrlError`
    to :class:`ProjectionError` for the installer boundary.

    A valid npm tarball URL::

        https://registry.npmjs.org/<package>/-/<pkg_name>-<base_version>.tgz

    where ``<pkg_name>`` is the last path segment of *package* and
    ``<base_version>`` is *version* with any ``+build`` metadata
    stripped (npm tarball filenames never include build metadata).
    """
    from docker.versioning.npm_tarball import (
        NpmTarballUrlError,
        validate,
    )

    try:
        validate(url, package, version)
    except NpmTarballUrlError as exc:
        raise ProjectionError(str(exc)) from exc


def _reject_path_traversal(value: str, *, field_name: str) -> None:
    """Validate that *value* is a safe relative path with no traversal.

    Rejects:

    * absolute paths (leading ``/`` or platform-absolute)
    * backslashes
    * empty segments (``//``, trailing ``/``, leading ``/``)
    * segments that are exactly ``.`` (same-dir)
    * segments that are exactly ``..`` (parent-dir)
    * normalized paths that escape the logical root (e.g. ``a/../../b``)

    The check is component-aware — ``".."`` is rejected only when it
    appears as a standalone path *segment*, not when it appears inside
    a longer name like ``"a..b"``.
    """
    import os.path

    exc: type[MetadataValidationError | ProjectionError]
    if field_name == "metadata_file":
        exc = MetadataValidationError
    else:
        exc = ProjectionError

    if not value or value.isspace():
        raise exc(f"{field_name} must not be empty")

    if os.path.isabs(value) or value.startswith("/"):
        raise exc(f"{field_name} must not be absolute: {value!r}")

    if "\\" in value:
        raise exc(
            f"{field_name} must not contain backslashes: {value!r}"
        )

    segments = value.split("/")
    for seg in segments:
        if seg == "":
            raise exc(
                f"{field_name} must not contain empty path segments "
                f"(leading/trailing/double slash): {value!r}"
            )
        if seg in (".", ".."):
            raise exc(
                f"{field_name} contains reserved path segment "
                f"{seg!r}: {value!r}"
            )

    # Final: normalized path must remain beneath its logical root.
    normalized = os.path.normpath(value)
    if normalized.startswith("..") or os.path.isabs(normalized):
        raise exc(
            f"{field_name} normalizes to escape root "
            f"({value!r} → {normalized!r})"
        )


def _validate_downloaded_artifact(
    fs: ArtifactFilesystem,
    workspace_dir: str,
    artifact_path: str,
) -> str:
    """Trust-boundary check on a downloaded artifact path.

    The downloader returns an unverified local path.  Before the
    installer reads or hashes anything at that path it MUST prove:

    * the path is absolute
    * the path resolves to a direct child of *workspace_dir*
    * the path refers to a regular file (not a symlink, directory,
      or special file)

    All filesystem queries go through the injected *fs* boundary so
    that tests can prove behaviour with fakes instead of real
    filesystem state.

    Symlinks are always rejected — even if their current target
    is inside the workspace — because accepting and resolving
    them preserves a TOCTOU path-swap window.

    Returns the real (normalized) path that should be used for
    reading, hashing, and installation.

    Raises :class:`InstallError` on any violation.
    """
    import os
    import stat

    if not fs.is_absolute(artifact_path):
        raise InstallError(
            f"downloaded artifact path must be absolute: "
            f"{artifact_path!r}"
        )

    # Resolve workspace directory (could be a symlink itself).
    real_ws = fs.realpath(workspace_dir)

    # Must be a regular file — NOT a symlink, directory, FIFO, etc.
    # os.lstat follows no links, so symlinks are rejected here.
    try:
        if not stat.S_ISREG(fs.lstat_mode(artifact_path)):
            raise InstallError(
                f"downloaded artifact is not a regular file: "
                f"{artifact_path!r}"
            )
    except FileNotFoundError:
        raise InstallError(
            f"downloaded artifact does not exist: {artifact_path!r}"
        )

    # Ensure the artifact (fully normalized, no symlinks followed
    # since we already rejected them) is inside the workspace.
    real_artifact = fs.realpath(artifact_path)
    if not real_artifact.startswith(real_ws + os.sep):
        raise InstallError(
            f"downloaded artifact {artifact_path!r} "
            f"(resolved: {real_artifact!r}) is outside workspace "
            f"{real_ws!r}"
        )

    return real_artifact


# ═══════════════════════════════════════════════════════════════════════
# DTOs
# ═══════════════════════════════════════════════════════════════════════


class InstallStatus(enum.Enum):
    """Per-extension outcome."""
    OK = "ok"                       # installed and verified
    ALREADY_INSTALLED = "already_installed"  # no-op, already present
    FAILED = "failed"               # installation or verification failed
    PLANNED = "planned"             # dry-run: would install or reinstall


@dataclass(frozen=True)
class ExtensionResult:
    """Structured outcome for a single Pi extension."""
    package: str
    version: str
    status: InstallStatus
    detail: str | None = None       # error detail when status == FAILED


@dataclass(frozen=True)
class InstallResult:
    """Structured outcome of :func:`install_extensions`."""
    results: tuple[ExtensionResult, ...]
    dry_run: bool = False

    @property
    def ok(self) -> bool:
        return all(
            r.status != InstallStatus.FAILED
            for r in self.results
        )


@dataclass(frozen=True)
class ProjectionEntry:
    """A single extension entry read from the runtime projection."""
    package: str
    version: str
    artifact_url: str
    artifact_integrity: str
    metadata_file: str

    def __post_init__(self) -> None:
        import base64
        import re

        # -- package ---------------------------------------------------
        pkg = self.package
        _reject_path_traversal(pkg, field_name="package")
        if not pkg:
            raise ProjectionError("package name must not be empty")
        if pkg.startswith("@"):
            if not re.fullmatch(_SAFE_SCOPED_RE, pkg, re.VERBOSE):
                raise ProjectionError(
                    f"invalid scoped package name: {pkg!r}"
                )
        else:
            if "/" in pkg:
                raise ProjectionError(
                    f"unscoped package name must not contain '/': {pkg!r}"
                )
            if not re.fullmatch(_SAFE_PACKAGE_RE, pkg, re.VERBOSE):
                raise ProjectionError(
                    f"invalid package name: {pkg!r}"
                )

        # -- version ---------------------------------------------------
        ver = self.version
        from docker.versioning.semver import (
            SemverError,
            validate as _validate_semver,
        )
        try:
            _validate_semver(ver)
        except SemverError as exc:
            raise ProjectionError(f"version {exc} — want exact semver") from exc

        # -- artifact_url ----------------------------------------------
        validate_npm_tarball_url(self.artifact_url, pkg, ver)

        # -- artifact_integrity ----------------------------------------
        integ = self.artifact_integrity
        m = re.fullmatch(
            r"(sha(?:256|384|512))-(.+)", integ,
        )
        if not m:
            raise ProjectionError(
                f"artifact integrity must be 'shaNNN-<base64>': "
                f"{integ!r}"
            )
        try:
            digest = base64.b64decode(m.group(2), validate=True)
        except Exception:
            raise ProjectionError(
                f"artifact integrity has invalid base64: {integ!r}"
            ) from None
        expected_len = {"sha256": 32, "sha384": 48, "sha512": 64}
        if len(digest) != expected_len[m.group(1)]:
            raise ProjectionError(
                f"artifact integrity digest length {len(digest)} "
                f"!= {expected_len[m.group(1)]} for {m.group(1)}: "
                f"{integ!r}"
            )

        # -- metadata_file ---------------------------------------------
        _reject_path_traversal(self.metadata_file, field_name="metadata_file")


# -- package-name safety regexes (module level, not DTO fields) ---------

_SAFE_PACKAGE_RE = r"""\A
    (?!\.)                          # no leading dot
    [a-z0-9_\-](?:[a-z0-9_\-.]*[a-z0-9_\-])?  # unscoped-npm-name
    \Z
    """

_SAFE_SCOPED_RE = r"""\A
    @
    (?!\.)                          # scope: no leading dot
    [a-z0-9_\-](?:[a-z0-9_\-.]*[a-z0-9_\-])?  # scope-name
    /
    (?!\.)                          # name: no leading dot
    [a-z0-9_\-](?:[a-z0-9_\-.]*[a-z0-9_\-])?  # package-name
    \Z
    """


# ═══════════════════════════════════════════════════════════════════════
# Injectable boundaries (Protocols)
# ═══════════════════════════════════════════════════════════════════════


class MountChecker(Protocol):
    """Verify that *path* is a mount point."""

    def is_mount(self, path: str) -> bool:
        ...


class ArtifactDownloader(Protocol):
    """Download an artifact to a local file.

    Returns the path to the downloaded (unverified) artifact.
    Integrity verification is *not* performed here — it is owned
    by the installer module over the returned bytes.

    Raises :class:`InstallError` on download failure.
    """

    def fetch(self, *, url: str, dest_dir: str) -> str:
        ...


class ArtifactFilesystem(Protocol):
    """Read and manage a downloaded artifact file on disk.

    Provides injectable read/remove/stat operations so that
    installer-owned integrity verification, path validation, and
    cleanup are testable without real filesystem effects.

    The path is the one returned by :meth:`ArtifactDownloader.fetch`.
    """

    def is_absolute(self, path: str) -> bool:
        """Return ``True`` when *path* is absolute."""
        ...

    def lstat_mode(self, path: str) -> int:
        """Return the ``st_mode`` bits of *path* without following
        symlinks (semantics of :func:`os.lstat`).

        Raises :class:`FileNotFoundError` when *path* does not
        exist.
        """
        ...

    def realpath(self, path: str) -> str:
        """Return the canonical path of *path* with all symlinks
        resolved (semantics of :func:`os.path.realpath`).
        """
        ...

    def read_bytes(self, path: str) -> bytes:
        """Read the *entire* artifact file at *path*.

        Raises :class:`InstallError` on failure (missing,
        permissions, truncated).
        """
        ...

    def remove(self, path: str) -> None:
        """Delete the artifact at *path*.

        Called on success (after install), on integrity failure,
        on install failure, and on interruption.
        Must not raise if the file is already absent.
        """
        ...


class TempWorkspace(Protocol):
    """Create and destroy private temp directories for downloads.

    Each call to :meth:`create` returns:

    * **Absolute** — the returned path is an absolute filesystem path.
    * **Unique** — no two calls to ``create`` (across processes or
      threads) may return the same path.
    * **Owner-only** — the directory MUST be created with mode
      ``0o700`` so that only the calling user can read, write, or
      traverse it.

    :meth:`cleanup` removes the directory and all contents.
    """

    def create(self) -> str:
        """Create a unique private temp directory.

        Returns the absolute path.

        Raises :class:`InstallError` on failure (e.g. permission
        denied, no space).
        """
        ...

    def cleanup(self, path: str) -> None:
        """Remove the workspace directory and all contents.

        Must not raise if already removed or if *path* does not
        exist.
        """
        ...


class PackageInstaller(Protocol):
    """Install a Pi extension from already-verified artifact bytes.

    *artifact_bytes* contains the exact bytes whose integrity was
    verified against the projection.  The installer MUST NOT download
    bytes, query registries, or re-open a filesystem path that could
    have been replaced between verification and installation.

    Returns ``None`` on success or raises :class:`InstallError`.
    """

    def install(self, *, package: str, artifact_bytes: bytes) -> None:
        ...


class MetadataReader(Protocol):
    """Read installed package metadata from disk.

    *metadata_file* is the validated relative path from the
    projection (e.g. ``"package.json"``, ``"nested/pkg/package.json"``).
    The caller resolves it against *pi_home*.

    Raises:
        :class:`MetadataNotFoundError`: The package is genuinely
            absent — no metadata file exists.  This is the *only*
            error that triggers a fresh install.
        :class:`InstallError`: Read, parse, or permission failure.
            These are surfaced immediately as installation failures
            and never trigger a download.
    """

    def read(self, *, pi_home: str, metadata_file: str, package: str) -> dict[str, object]:
        ...


class PrivilegeContext(Protocol):
    """Execution-identity and ownership-validation boundary.

    The installer runs as ``dev`` inside the container and must
    verify that identity before performing any mutation.  After
    installing files into *pi_home* it performs a *read-only*
    validation that the installed artefacts are owned by
    ``dev:dev``.  Actual ``chown`` is the responsibility of the
    root entrypoint (Stage 10.4) and happens before the privilege
    drop — ``dev`` cannot mutate ownership.
    """

    def verify_user(self, expected: str) -> None:
        """Raise :class:`InstallError` if the current process owner
        does not match *expected*."""
        ...

    def validate_owner(self, path: str, expected_owner: str) -> None:
        """Read-only check: the file at *path* is owned by *expected_owner*.

        Called after installation (and after the root entrypoint has
        repaired ownership).  Must not attempt ``chown`` — the
        installer process cannot change ownership.

        Raises :class:`InstallError` if ownership does not match.
        """
        ...


@dataclass(frozen=True)
class InstallContext:
    """Injectable boundary implementations for the installer."""

    mount_check: MountChecker
    workspace: TempWorkspace
    download: ArtifactDownloader
    file: ArtifactFilesystem
    installer: PackageInstaller
    metadata: MetadataReader
    privilege: PrivilegeContext

    # ------------------------------------------------------------------
    # Real implementations (used when not injected by tests)
    # ------------------------------------------------------------------

    @staticmethod
    def real_mount_check() -> MountChecker:
        import os
        import stat as st

        class _RealMountCheck:
            @staticmethod
            def is_mount(path: str) -> bool:
                """Return True if *path* is a mount point, False otherwise.

                Uses ``mountpoint -q`` because bind mounts share
                ``st_dev`` with their parent, making device-ID
                comparison unreliable.
                """
                import subprocess
                result = subprocess.run(
                    ["mountpoint", "-q", "--", path],
                    capture_output=True,
                )
                return result.returncode == 0

        return _RealMountCheck()

    @staticmethod
    def real_workspace() -> TempWorkspace:
        import os
        import shutil
        import tempfile

        class _RealTempWorkspace:
            def create(self) -> str:
                path = tempfile.mkdtemp(suffix=".pi-workspace")
                os.chmod(path, 0o700)
                return path

            def cleanup(self, path: str) -> None:
                shutil.rmtree(path, ignore_errors=True)

        return _RealTempWorkspace()

    @staticmethod
    def real_download() -> ArtifactDownloader:
        import subprocess
        import shutil

        class _RealArtifactDownloader:
            def fetch(self, url: str, dest_dir: str) -> str:
                """Download *url* to *dest_dir* via curl.

                Returns the absolute path to the downloaded file.
                The caller owns integrity verification.
                """
                import os
                basename = url.rstrip("/").rsplit("/", 1)[-1] or "artifact"
                dest = os.path.join(dest_dir, basename)
                result = subprocess.run(
                    [
                        "curl", "--fail", "--location",
                        "--silent", "--show-error",
                        "--output", dest,
                        url,
                    ],
                    capture_output=True,
                    text=True,
                )
                if result.returncode != 0:
                    raise InstallError(
                        f"download of {url!r} failed (exit {result.returncode}): "
                        f"{result.stderr.strip()}"
                    )
                return dest

        return _RealArtifactDownloader()

    @staticmethod
    def real_file() -> ArtifactFilesystem:
        import os
        import stat as st

        class _RealArtifactFilesystem:
            def read_bytes(self, path: str) -> bytes:
                with open(path, "rb") as fh:
                    return fh.read()

            def remove(self, path: str) -> None:
                os.unlink(path)

            def is_absolute(self, path: str) -> bool:
                return os.path.isabs(path)

            def lstat_mode(self, path: str) -> int:
                return os.lstat(path).st_mode

            def realpath(self, path: str) -> str:
                return os.path.realpath(path)

        return _RealArtifactFilesystem()

    @staticmethod
    def real_installer() -> PackageInstaller:
        import json
        import subprocess

        class _RealPackageInstaller:
            def install(self, package: str, artifact_bytes: bytes) -> None:
                """Install a Pi extension from verified bytes.

                Writes *artifact_bytes* to a private temp file,
                invokes ``pi install``, and removes the temp file
                on all exit paths.  The bytes are never re-read
                from a mutable filesystem path — closing the TOCTOU
                gap between verification and installation.
                """
                import os
                import tempfile

                fd, tmp_path = tempfile.mkstemp(
                    suffix=".tgz", prefix="pi-install-",
                )
                try:
                    # Write all bytes — os.write() may return after
                    # writing only part of the buffer.
                    data = artifact_bytes
                    while data:
                        written = os.write(fd, data)
                        if written <= 0:
                            raise OSError(
                                f"os.write returned {written}"
                            )
                        data = data[written:]
                    os.close(fd)
                    fd = -1  # guard double-close
                    result = subprocess.run(
                        ["pi", "install", tmp_path],
                        capture_output=True,
                        text=True,
                    )
                    if result.returncode != 0:
                        raise InstallError(
                            f"pi install {package!r} failed (exit {result.returncode}): "
                            f"{result.stderr.strip()}"
                        )
                finally:
                    if fd >= 0:
                        try:
                            os.close(fd)
                        except OSError:
                            pass
                    try:
                        os.unlink(tmp_path)
                    except OSError:
                        pass

        return _RealPackageInstaller()

    @staticmethod
    def real_metadata() -> MetadataReader:
        import json
        import os

        class _RealMetadataReader:
            def read(
                self,
                *,
                pi_home: str,
                metadata_file: str,
                package: str,
            ) -> dict[str, object]:
                """Read and parse installed package metadata.

                Raises :class:`MetadataNotFoundError` when the
                metadata file genuinely does not exist.
                Raises :class:`InstallError` for read, parse,
                or permission failures.
                """
                npm_root = os.path.join(
                    pi_home, "agent", "npm", "node_modules",
                )
                pkg_dir = os.path.join(npm_root, package)
                meta_path = os.path.join(pkg_dir, metadata_file)
                try:
                    with open(meta_path, "rb") as fh:
                        raw = json.loads(fh.read())
                except FileNotFoundError:
                    raise MetadataNotFoundError(
                        f"metadata not found for {package!r} at {meta_path!r}"
                    ) from None
                except json.JSONDecodeError as exc:
                    raise InstallError(
                        f"invalid JSON in {meta_path!r}: {exc}"
                    ) from exc
                except PermissionError as exc:
                    raise InstallError(
                        f"permission denied reading {meta_path!r}: {exc}"
                    ) from exc
                except OSError as exc:
                    raise InstallError(
                        f"failed to read {meta_path!r}: {exc}"
                    ) from exc
                if not isinstance(raw, dict):
                    raise InstallError(
                        f"metadata at {meta_path!r} is not a JSON object"
                    )
                return raw

        return _RealMetadataReader()

    @staticmethod
    def real_privilege() -> PrivilegeContext:
        import os
        import pwd
        import stat as st

        class _RealPrivilegeContext:
            def verify_user(self, expected: str) -> None:
                """Raise :class:`InstallError` if the current process
                user does not match *expected*."""
                try:
                    pw = pwd.getpwuid(os.getuid())
                except KeyError:
                    raise InstallError(
                        f"current uid {os.getuid()} has no passwd entry"
                    )
                if pw.pw_name != expected:
                    raise InstallError(
                        f"running as {pw.pw_name!r}, must be {expected!r}"
                    )

            def validate_owner(self, path: str, expected_owner: str) -> None:
                """Read-only check: the file at *path* is owned by
                *expected_owner* (format ``"user:group"``)."""
                try:
                    st_result = os.lstat(path)
                except OSError as exc:
                    raise InstallError(
                        f"cannot stat {path!r}: {exc}"
                    ) from exc

                user, _, group = expected_owner.partition(":")

                import grp
                try:
                    owner_name = pwd.getpwuid(st_result.st_uid).pw_name
                except KeyError:
                    owner_name = str(st_result.st_uid)
                try:
                    group_name = grp.getgrgid(st_result.st_gid).gr_name
                except KeyError:
                    group_name = str(st_result.st_gid)

                actual = f"{owner_name}:{group_name}"
                if actual != expected_owner:
                    raise InstallError(
                        f"{path!r} is owned by {actual!r}, "
                        f"expected {expected_owner!r}"
                    )

        return _RealPrivilegeContext()

    @staticmethod
    def make_real() -> "InstallContext":
        """Create an :class:`InstallContext` wired to real system
        boundaries (mount-point check, curl download, filesystem,
        pi install, user/group introspection)."""
        return InstallContext(
            mount_check=InstallContext.real_mount_check(),
            workspace=InstallContext.real_workspace(),
            download=InstallContext.real_download(),
            file=InstallContext.real_file(),
            installer=InstallContext.real_installer(),
            metadata=InstallContext.real_metadata(),
            privilege=InstallContext.real_privilege(),
        )


# ═══════════════════════════════════════════════════════════════════════
# Domain errors
# ═══════════════════════════════════════════════════════════════════════


class InstallError(RuntimeError):
    """A recoverable installation failure with structured detail."""


class MetadataNotFoundError(InstallError):
    """The requested package is not installed — no metadata file exists.

    This is distinct from read/parse/permission failures:
    it signals that a fresh install is expected and safe.  All
    other :class:`InstallError` subclasses during metadata
    pre-check are surfaced immediately without invoking
    download or install."""


class IntegrityError(InstallError):
    """Checksum verification failed.

    Fields:
        algorithm: ``"sha256"``, ``"sha384"``, or ``"sha512"``.
        expected:  Hex-encoded expected digest.
        actual:    Hex-encoded actual digest.
    """
    def __init__(
        self,
        message: str,
        *,
        algorithm: str,
        expected: str,
        actual: str,
    ) -> None:
        super().__init__(message)
        self.algorithm = algorithm
        self.expected = expected
        self.actual = actual


class ProjectionError(InstallError):
    """The mounted projection TOML is structurally invalid."""


class MetadataValidationError(InstallError):
    """The projection ``metadata_file`` path is unsafe."""


# ═══════════════════════════════════════════════════════════════════════
# Public API
# ═══════════════════════════════════════════════════════════════════════


def _require_str(value: object, section: str, field: str) -> str:
    """Require *value* to be a :class:`str`, raising
    :class:`ProjectionError` with a focused diagnostic otherwise."""
    if not isinstance(value, str):
        raise ProjectionError(
            f"[extensions.{section}].{field} must be "
            f"a string, not {type(value).__name__}"
        )
    return value


def read_projection(path: str) -> list[ProjectionEntry]:
    """Read and validate the effective runtime projection from *path*.

    Returns a list of :class:`ProjectionEntry` objects in
    deterministic (sorted-by-name) order.

    Raises:
        ProjectionError: the TOML is structurally invalid.
        MetadataValidationError: a ``metadata_file`` value is unsafe.
        IntegrityError: an SRI integrity string is malformed or
            uses an unsupported algorithm.
    """
    import sys

    if sys.version_info >= (3, 11):
        import tomllib
    else:
        import tomli as tomllib  # type: ignore[no-redef]

    raw: dict[str, object]
    try:
        with open(path, "rb") as fh:
            raw = tomllib.load(fh)
    except FileNotFoundError:
        raise ProjectionError(f"projection file not found: {path!r}") from None
    except Exception as exc:
        raise ProjectionError(
            f"failed to parse projection TOML: {exc}"
        ) from None

    # ── closed schema: root table ─────────────────────────────────
    allowed_root = {"extensions"}
    unknown_root = set(raw) - allowed_root
    if unknown_root:
        raise ProjectionError(
            f"unknown top-level key(s) in runtime projection: "
            f"{sorted(unknown_root)!r}"
        )

    ext_table = raw.get("extensions")
    if not isinstance(ext_table, dict):
        raise ProjectionError(
            "[extensions] must be a TOML table"
        )
    ext_table = raw["extensions"]

    # ── allowed per-extension and per-artifact keys ────────────────
    allowed_ext = {"package", "version", "artifact", "metadata_file"}
    allowed_artifact = {"url", "integrity"}

    entries: list[ProjectionEntry] = []
    for ext_name, ext_val in ext_table.items():
        if not isinstance(ext_val, dict):
            raise ProjectionError(
                f"[extensions.{ext_name!s}] must be a TOML table"
            )

        unknown_ext = set(ext_val) - allowed_ext
        if unknown_ext:
            raise ProjectionError(
                f"[extensions.{ext_name!s}]: unknown key(s) "
                f"{sorted(unknown_ext)!r}"
            )

        # ── validate artifact sub-table ──────────────────────────
        artifact_raw = ext_val.get("artifact")
        if not isinstance(artifact_raw, dict):
            raise ProjectionError(
                f"[extensions.{ext_name!s}].artifact must be a TOML inline table"
            )
        unknown_artifact = set(artifact_raw) - allowed_artifact
        if unknown_artifact:
            raise ProjectionError(
                f"[extensions.{ext_name!s}].artifact: unknown key(s) "
                f"{sorted(unknown_artifact)!r}"
            )

        # ── construct validated DTO ───────────────────────────────
        try:
            section = str(ext_name)

            # Require every projected value to already be a string —
            # silently coercing ints, floats, etc. would mask TOML
            # authoring mistakes.
            pkg = _require_str(
                ext_val["package"], section, "package",
            )
            ver = _require_str(
                ext_val["version"], section, "version",
            )
            meta = _require_str(
                ext_val["metadata_file"], section, "metadata_file",
            )
            url = _require_str(
                artifact_raw["url"], section, "artifact.url",
            )
            integrity = _require_str(
                artifact_raw["integrity"], section, "artifact.integrity",
            )

            entry = ProjectionEntry(
                package=pkg,
                version=ver,
                artifact_url=url,
                artifact_integrity=integrity,
                metadata_file=meta,
            )
        except KeyError as exc:
            raise ProjectionError(
                f"[extensions.{ext_name!s}]: missing required key {exc}"
            ) from exc

        entries.append(entry)

    if not entries:
        raise ProjectionError("projection contains no extensions")

    entries.sort(key=lambda e: e.package)

    # ── reject duplicate package identities ────────────────────────
    for i in range(1, len(entries)):
        if entries[i].package == entries[i - 1].package:
            raise ProjectionError(
                f"duplicate package in projection: "
                f"{entries[i].package!r}"
            )

    return entries


def install_extensions(
    ctx: InstallContext,
    *,
    entries: list[ProjectionEntry],
    pi_home: str,
    dry_run: bool = False,
) -> InstallResult:
    """Install Pi extensions into *pi_home*.

    Operates in strict order per entry:
      1. mount check + user-identity verification (once, before any work)
      2. for each extension:
         a. metadata check (skip if already correctly installed)
         b. download (unverified bytes)
         c. **integrity verification** (installer-owned, over file bytes)
         d. install from verified local artifact path
         e. post-install metadata match
         f. read-only owner validation (dev:dev)

    Integrity verification is performed by this module between
    download and install — the downloader never sees the expected
    checksum and the installer never fetches bytes.

    Reads no files beyond *entries* and *pi_home*.  All I/O goes
    through the injected *ctx* boundaries.

    The temp workspace is cleaned up on **all** exit paths,
    including :class:`KeyboardInterrupt`, :class:`SystemExit`,
    and any other :class:`BaseException`.

    Returns a structured :class:`InstallResult`.
    """

    results: list[ExtensionResult] = []
    workspace_dir: str | None = None

    # ── 1. Mount check + user identity ───────────────────────
    if not ctx.mount_check.is_mount(pi_home):
        raise InstallError(
            f"pi-home is not a mount point: {pi_home!r}"
        )
    ctx.privilege.verify_user("dev")

    if dry_run:
        planned: list[ExtensionResult] = []
        for e in entries:
            try:
                installed = ctx.metadata.read(
                    pi_home=pi_home,
                    metadata_file=e.metadata_file,
                    package=e.package,
                )
            except MetadataNotFoundError:
                # Package genuinely absent — would install fresh.
                planned.append(ExtensionResult(
                    package=e.package,
                    version=e.version,
                    status=InstallStatus.PLANNED,
                ))
                continue
            except InstallError:
                # Read/parse/permission failure — surface without
                # mutation; do not swallow.
                raise

            pkg_name = installed.get("name")
            pkg_version = installed.get("version")
            if pkg_name == e.package and pkg_version == e.version:
                # Name + version match — validate ownership before
                # reporting ALREADY_INSTALLED.
                metadata_path = _npm_metadata_path(
                    pi_home, e.package, e.metadata_file,
                )
                try:
                    ctx.privilege.validate_owner(
                        metadata_path, "dev:dev",
                    )
                except InstallError as exc:
                    raise InstallError(
                        f"owner validation failed for {e.package}: {exc}"
                    ) from exc
                planned.append(ExtensionResult(
                    package=e.package,
                    version=e.version,
                    status=InstallStatus.ALREADY_INSTALLED,
                ))
            else:
                # Name/version mismatch — would reinstall.
                planned.append(ExtensionResult(
                    package=e.package,
                    version=e.version,
                    status=InstallStatus.PLANNED,
                ))
        return InstallResult(results=tuple(planned), dry_run=True)

    # ── 2. Create temp workspace (reused across extensions) ──
    try:
        workspace_dir = ctx.workspace.create()
    except Exception as exc:
        raise InstallError(
            f"failed to create temp workspace: {exc}"
        ) from exc

    # ── 3. Install each extension — cleanup workspace on all exits ──
    try:
        for entry in entries:
            try:
                result = _install_one(
                    ctx, entry, pi_home, workspace_dir,
                )
                results.append(result)
            except InstallError as exc:
                results.append(ExtensionResult(
                    package=entry.package,
                    version=entry.version,
                    status=InstallStatus.FAILED,
                    detail=f"[{entry.package}@{entry.version}] {exc}",
                ))
                # First failure stops subsequent mutations
                break
    finally:
        ctx.workspace.cleanup(workspace_dir)

    return InstallResult(results=tuple(results))


def _install_one(
    ctx: InstallContext,
    entry: ProjectionEntry,
    pi_home: str,
    workspace_dir: str,
) -> ExtensionResult:
    """Install (or skip) a single extension."""

    # ── 2a. Metadata pre-check ────────────────────────────────────
    try:
        installed = ctx.metadata.read(
            pi_home=pi_home,
            metadata_file=entry.metadata_file,
            package=entry.package,
        )
    except MetadataNotFoundError:
        pass  # not installed — proceed to fresh install
    except InstallError:
        # Read / parse / permission failures — surface immediately.
        raise
    else:
        pkg_name = installed.get("name")
        pkg_version = installed.get("version")
        if pkg_name == entry.package and pkg_version == entry.version:
            # Validate metadata ownership before accepting the
            # cached install — root- or foreign-owned metadata
            # must never be reported as ALREADY_INSTALLED.
            metadata_path = _npm_metadata_path(
                pi_home, entry.package, entry.metadata_file,
            )
            try:
                ctx.privilege.validate_owner(metadata_path, "dev:dev")
            except InstallError as exc:
                raise InstallError(
                    f"owner validation failed for {entry.package}: {exc}"
                ) from exc
            return ExtensionResult(
                package=entry.package,
                version=entry.version,
                status=InstallStatus.ALREADY_INSTALLED,
            )
        # Name/version mismatch — fall through to reinstall

    # ── 2b. Download + post-download transaction ──────────────────
    # Wrap the entire download→verify→install sequence so that the
    # artifact is removed on ALL exit paths, including
    # KeyboardInterrupt and SystemExit.
    artifact_path: str | None = None
    try:
        try:
            artifact_path = ctx.download.fetch(
                url=entry.artifact_url,
                dest_dir=workspace_dir,
            )
        except InstallError:
            raise
        except Exception as exc:
            raise InstallError(
                f"download failed for {entry.package}: {exc}"
            ) from exc

        return _install_one_after_download(
            ctx, entry, pi_home, workspace_dir, artifact_path,
        )
    finally:
        if artifact_path is not None:
            _remove_artifact(ctx, artifact_path)


def _install_one_after_download(
    ctx: InstallContext,
    entry: ProjectionEntry,
    pi_home: str,
    workspace_dir: str,
    artifact_path: str,
) -> ExtensionResult:
    """Verify integrity, install, and post-validate — called
    after the artifact has been downloaded to *artifact_path*.

    ``_install_one`` wraps this with artifact-cleanup on all
    exit paths."""

    # ── 2b'. Path-trust validation ───────────────────────────────
    verified_path = _validate_downloaded_artifact(
        ctx.file, workspace_dir, artifact_path,
    )

    # ── 2c. Integrity verification ───────────────────────────────
    try:
        content = ctx.file.read_bytes(verified_path)
    except InstallError:
        raise
    except Exception as exc:
        raise InstallError(
            f"failed to read downloaded artifact for {entry.package}: {exc}"
        ) from exc

    if not content:
        raise InstallError(
            f"downloaded artifact for {entry.package} is empty"
        )

    algo, _, b64 = entry.artifact_integrity.partition("-")
    hasher: "hashlib._Hash"
    if algo == "sha256":
        hasher = hashlib.sha256()
    elif algo == "sha384":
        hasher = hashlib.sha384()
    elif algo == "sha512":
        hasher = hashlib.sha512()
    else:
        raise IntegrityError(
            f"unsupported integrity algorithm: {algo!r}",
            algorithm=algo,
            expected=entry.artifact_integrity,
            actual="<none>",
        )

    hasher.update(content)
    actual_digest = hasher.digest()

    try:
        expected_digest = base64.b64decode(b64, validate=True)
    except Exception:
        raise IntegrityError(
            f"invalid base64 in projected integrity for {entry.package}",
            algorithm=algo,
            expected=entry.artifact_integrity,
            actual="<invalid-base64>",
        ) from None

    if not hmac.compare_digest(actual_digest, expected_digest):
        raise IntegrityError(
            f"integrity check failed for {entry.package}: "
            f"expected {algo}:{binascii.hexlify(expected_digest).decode()}, "
            f"got {algo}:{binascii.hexlify(actual_digest).decode()}",
            algorithm=algo,
            expected=binascii.hexlify(expected_digest).decode(),
            actual=binascii.hexlify(actual_digest).decode(),
        )

    # ── 2d. Install from verified bytes ──────────────────────────
    try:
        ctx.installer.install(
            package=entry.package,
            artifact_bytes=content,
        )
    except InstallError:
        raise
    except Exception as exc:
        raise InstallError(
            f"install failed for {entry.package} ({entry.version}): {exc}"
        ) from exc

    # ── 2e. Post-install metadata verification ───────────────────
    try:
        new_meta = ctx.metadata.read(
            pi_home=pi_home,
            metadata_file=entry.metadata_file,
            package=entry.package,
        )
    except InstallError as exc:
        raise InstallError(
            f"post-install metadata read failed for {entry.package} "
            f"({entry.version}): {exc}"
        ) from exc

    new_name = new_meta.get("name")
    new_version = new_meta.get("version")
    if new_name != entry.package or new_version != entry.version:
        raise InstallError(
            f"post-install metadata mismatch for {entry.package}: "
            f"expected name={entry.package!r} version={entry.version!r}, "
            f"got name={new_name!r} version={new_version!r}"
        )

    # ── 2g. Owner validation ─────────────────────────────────────
    metadata_path = _npm_metadata_path(
        pi_home, entry.package, entry.metadata_file,
    )
    try:
        ctx.privilege.validate_owner(metadata_path, "dev:dev")
    except InstallError as exc:
        raise InstallError(
            f"owner validation failed for {entry.package}: {exc}"
        ) from exc

    return ExtensionResult(
        package=entry.package,
        version=entry.version,
        status=InstallStatus.OK,
    )


def _remove_artifact(ctx: InstallContext, path: str) -> None:
    """Best-effort artifact removal."""
    try:
        ctx.file.remove(path)
    except Exception:
        pass  # removal is best-effort; failures are swallowed


def _npm_metadata_path(pi_home: str, package: str, metadata_file: str) -> str:
    """Resolve the installed metadata path in the Pi CLI npm layout."""
    import os
    return os.path.join(
        pi_home, "agent", "npm", "node_modules", package, metadata_file,
    )


# ═══════════════════════════════════════════════════════════════════════
# Exit-code mapping (shell wrapper owned)
# ═══════════════════════════════════════════════════════════════════════

_EXIT_OK = 0
_EXIT_MOUNT = 10
_EXIT_PROJECTION = 11
_EXIT_INTEGRITY = 12
_EXIT_INSTALL = 13
_EXIT_VERIFY = 14
_EXIT_USAGE = 2


def exit_code_for(result: InstallResult | InstallError | Exception) -> int:
    """Map an installer outcome to a process exit code.

    Shell wrappers call this after :func:`install_extensions`.
    """
    if isinstance(result, InstallResult):
        return _EXIT_OK if result.ok else _EXIT_INSTALL
    if isinstance(result, InstallError):
        return _EXIT_INSTALL
    return _EXIT_USAGE


# ═══════════════════════════════════════════════════════════════════════
# CLI entry point
# ═══════════════════════════════════════════════════════════════════════

_FIXED_PROJECTION = "/run/pi-cli/docker-constructor.runtime.toml"
_FIXED_PI_HOME = "/home/dev/.pi"


def main(argv: list[str] | None = None) -> int:
    """Thin CLI entry point invoked by the shell wrapper.

    Accepts the fixed runtime projection path and Pi home;
    exposes ``--dry-run`` for pre-flight inspection.
    """
    import argparse

    parser = argparse.ArgumentParser(
        description="Protected runtime extension installer",
    )
    parser.add_argument(
        "command",
        choices=("install",),
        default="install",
        nargs="?",
        help="Command (default: install)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate projection and inspect metadata; do not download or install",
    )

    args = parser.parse_args(argv)

    try:
        entries = read_projection(_FIXED_PROJECTION)
    except ProjectionError as exc:
        import sys
        print(f"ERROR: {exc}", file=sys.stderr)
        return _EXIT_PROJECTION

    if not entries:
        print("Nothing to install.", file=sys.stderr)
        return _EXIT_OK

    ctx = InstallContext.make_real()

    try:
        result = install_extensions(
            ctx,
            entries=entries,
            pi_home=_FIXED_PI_HOME,
            dry_run=args.dry_run,
        )
    except InstallError as exc:
        import sys
        print(f"ERROR: {exc}", file=sys.stderr)
        return _EXIT_INSTALL

    if result.dry_run:
        ok_count = sum(
            1 for r in result.results
            if r.status == InstallStatus.ALREADY_INSTALLED
        )
        planned = sum(
            1 for r in result.results
            if r.status == InstallStatus.PLANNED
        )
        print(
            f"Dry-run: {ok_count} already installed, "
            f"{planned} would be installed",
        )

    return _EXIT_OK if result.ok else _EXIT_INSTALL


if __name__ == "__main__":
    raise SystemExit(main())
