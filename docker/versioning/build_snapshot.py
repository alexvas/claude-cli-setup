"""Immutable, minimal BuildKit named-context snapshots for build artifacts."""
from __future__ import annotations

import errno
import hashlib
import json
import os
import shutil
import stat
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from .build_cache import prepare_build_cache, validate_host_owner_traversal
from .build_materialization import SelectedBuildArtifact
from .project_state import ProjectState
from docker.npm_environment.errors import LockedNpmError
from docker.npm_environment.evidence import AssemblerEvidence, parse_evidence
from docker.npm_environment.tree import (
    TreeManifest,
    build_tree_manifest,
    canonical_tree_digest,
)
from docker.versioning.pi_consumer import PiConsumerError, validate_launcher_evidence

_LOGICAL_NAMES = {
    "rustup": "rustup-init",
    "uv": "uv.tar.gz",
    "rtk": "rtk.deb",
    "fd": "fd.deb",
}

# Derived-environment admission layout inside the snapshot.  All Pi-derived
# files (the assembled tree, the consumer launcher, and both evidence sets)
# live beneath one isolated, immutable directory so the prebuilt artifacts and
# the manifest remain the only other top-level entries in the named context.
_PI_ISOLATION_DIR = Path("derived-environments/pi")
_PI_TREE_DIR = _PI_ISOLATION_DIR / "opt/pi"
_PI_LAUNCHER = _PI_TREE_DIR / "bin/pi"
_PI_ASSEMBLER_EVIDENCE = _PI_ISOLATION_DIR / "pi-assembler-evidence.json"
_PI_LAUNCHER_EVIDENCE = _PI_ISOLATION_DIR / "pi-launcher-evidence.json"

# Read-only, no-follow open for descriptor-based payload validation.
_NOFOLLOW_RDONLY = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)

# Read-only, no-follow directory open for descriptor-relative staging.
_NOFOLLOW_DIR = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)

# Hard-link failure modes that mean hard linking is unavailable, not unsafe.
# Only these fall back to descriptor-based copying.  EPERM/EACCES (protected
# hard links), ELOOP (a replaced symlink), a vanished source, or any other
# error fails closed instead of silently copying an unverified payload.
_HARD_LINK_UNAVAILABLE = frozenset({
    errno.EXDEV,
    errno.EOPNOTSUPP,
    getattr(errno, "ENOTSUP", errno.EOPNOTSUPP),
})


class SnapshotError(RuntimeError):
    """A snapshot cannot safely be created or imported."""


@dataclass(frozen=True)
class DerivedEnvironmentSource:
    """Immutable inputs for admitting the host-assembled Pi environment.

    Carries the raw assembled tree, launcher, and both evidence sets, plus
    the complete derived-environment attestation so the snapshot admission
    re-validates every binding before any copy.
    """

    environment_root: Path
    """Published assembler tree (contains ``node_modules/``)."""

    launcher_contents: bytes
    launcher_mode: int
    assembler_evidence: bytes
    launcher_evidence: bytes

    assembler_evidence_digest: str
    """Canonical digest of the parsed assembler evidence body."""

    assembler_evidence_bytes_digest: str
    """SHA-256 of the exact assembler-evidence bytes."""

    launcher_evidence_digest: str
    """SHA-256 of the exact launcher-evidence bytes."""

    assembled_output_identity: str
    """Evidence-bound assembled output identity."""

    canonical_tree_digest: str
    """Evidence-bound canonical published-tree digest."""


@dataclass(frozen=True)
class MaterializedSnapshot:
    path: Path
    manifest: Path


def _hash_descriptor(fd: int) -> str:
    digest = hashlib.sha256()
    while True:
        chunk = os.read(fd, 1024 * 1024)
        if not chunk:
            return digest.hexdigest()
        digest.update(chunk)


def _open_validated_source(blob: Path, expected: str) -> int:
    """Open and validate a source blob, returning its retained descriptor.

    The source must be a regular file owned by the invoking user with mode
    exactly 0444 and the expected digest.  Missing, symlinked, foreign-owned,
    writable, non-regular, or digest-mismatched sources raise ``SnapshotError``
    and are never chmodded, chowned, deleted, or repaired.  The descriptor is
    kept open so the validated bytes are reused for hard-link publication or
    descriptor-based copying without reopening an untrusted pathname.
    """
    try:
        fd = os.open(blob, _NOFOLLOW_RDONLY)
    except OSError as exc:
        raise SnapshotError(f"cannot open snapshot source blob {blob}: {exc}") from exc
    try:
        st = os.fstat(fd)
        if not stat.S_ISREG(st.st_mode):
            raise SnapshotError(f"snapshot source blob {blob} is not a regular file")
        if st.st_uid != os.geteuid():
            raise SnapshotError(f"snapshot source blob {blob} is not owned by the invoking user")
        if stat.S_IMODE(st.st_mode) != 0o444:
            raise SnapshotError(f"snapshot source blob {blob} must be mode 0444")
        if _hash_descriptor(fd) != expected:
            raise SnapshotError(f"snapshot source blob {blob} failed digest verification")
        return fd
    except BaseException:
        os.close(fd)
        raise


def _copy_source_fd_to_destination(
    source_fd: int, destination_name: str, dir_fd: int, expected: str,
) -> None:
    """Copy a validated source descriptor to a descriptor-relative destination.

    The destination is created with ``O_WRONLY | O_CREAT | O_EXCL |
    O_NOFOLLOW``, its bytes are copied from the retained validated descriptor
    (never a reopened pathname) and hashed as they stream, the copied digest
    must match, and only the independent destination inode is finalized to
    0444 before being flushed.
    """
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(destination_name, flags, 0o444, dir_fd=dir_fd)
    except OSError as exc:
        raise SnapshotError(f"cannot create snapshot payload {destination_name!r}: {exc}") from exc
    try:
        os.lseek(source_fd, 0, os.SEEK_SET)
        digest = hashlib.sha256()
        while True:
            chunk = os.read(source_fd, 1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
            view = memoryview(chunk)
            while view:
                written = os.write(fd, view)
                view = view[written:]
        if digest.hexdigest() != expected:
            raise SnapshotError(f"snapshot payload {destination_name!r} failed digest verification")
        os.fchmod(fd, 0o444)
        os.fsync(fd)
    except BaseException:
        os.close(fd)
        try:
            os.unlink(destination_name, dir_fd=dir_fd)
        except OSError:
            pass
        raise
    os.close(fd)


def _validate_hard_link_destination(
    destination_name: str, dir_fd: int, source_stat: os.stat_result, expected: str,
) -> None:
    """Open and revalidate a hard-linked destination descriptor-relatively.

    The destination must reference the same inode (``st_dev``/``st_ino``) as
    the validated source and itself be a regular, invoking-user-owned 0444
    file with the expected digest.  On any failure the descriptor is closed
    and the original ``SnapshotError`` propagates; the caller removes the
    unsafe destination name without mutating the source inode.
    """
    try:
        fd = os.open(destination_name, _NOFOLLOW_RDONLY, dir_fd=dir_fd)
    except OSError as exc:
        raise SnapshotError(
            f"cannot open hard-linked snapshot payload {destination_name!r}: {exc}"
        ) from exc
    try:
        st = os.fstat(fd)
        if st.st_dev != source_stat.st_dev or st.st_ino != source_stat.st_ino:
            raise SnapshotError(
                f"hard-linked snapshot payload {destination_name!r} does not "
                "reference the validated source inode"
            )
        if not stat.S_ISREG(st.st_mode):
            raise SnapshotError(f"hard-linked snapshot payload {destination_name!r} is not a regular file")
        if st.st_uid != os.geteuid():
            raise SnapshotError(f"hard-linked snapshot payload {destination_name!r} is not owned by the invoking user")
        if stat.S_IMODE(st.st_mode) != 0o444:
            raise SnapshotError(f"hard-linked snapshot payload {destination_name!r} must be mode 0444")
        if _hash_descriptor(fd) != expected:
            raise SnapshotError(f"hard-linked snapshot payload {destination_name!r} failed digest verification")
    finally:
        os.close(fd)


def _readonly_tree(root: Path, hard_linked: set[Path], *, derived_root: Path | None = None) -> None:
    # Files first: directory permissions must not prevent traversal during
    # finalisation.  Hard-linked payloads already share the cache blob's
    # required 0444 inode and must never be chmodded (that would mutate the
    # cached blob).  Copy-fallback payloads and snapshot-owned files such as
    # ``manifest.json`` have independent inodes and are finalized to 0444 here.
    # The derived Pi isolation directory is finalized during admission
    # (preserving executable bits) and preserves contained symlinks, so it is
    # skipped here.
    for path in root.rglob("*"):
        rel = path.relative_to(root)
        if derived_root is not None and (rel == derived_root or derived_root in rel.parents):
            continue
        if path.is_symlink():
            raise SnapshotError("selected prebuilt-artifact snapshot contains a symlink")
        if path.is_file() and rel not in hard_linked:
            os.chmod(path, 0o444)
    for path in sorted((p for p in root.rglob("*") if p.is_dir()), key=lambda p: len(p.parts), reverse=True):
        rel = path.relative_to(root)
        if derived_root is not None and (rel == derived_root or derived_root in rel.parents):
            continue
        os.chmod(path, 0o555)
    os.chmod(root, 0o555)


def _copy_contained_tree(source: Path, destination: Path) -> None:
    """Copy the assembled tree into the snapshot preserving executable bits
    and contained symlinks, removing every write bit.

    Symlinks are copied as symlinks (never followed); each one must resolve
    inside the source tree and not be dangling.  Special files are rejected.
    """
    source_real = Path(os.path.realpath(source))
    destination.mkdir(parents=True)
    entries = sorted(source.rglob("*"), key=lambda p: len(p.parts))
    for entry in entries:
        rel = entry.relative_to(source)
        dest = destination / rel
        if entry.is_symlink():
            target = os.readlink(entry)
            resolved = Path(os.path.realpath(entry))
            if resolved == source_real or source_real not in resolved.parents:
                raise SnapshotError(f"Pi tree symlink {rel} escapes the environment")
            if not resolved.exists():
                raise SnapshotError(f"Pi tree symlink {rel} is dangling")
            os.symlink(target, dest)
        elif entry.is_dir():
            dest.mkdir()
        elif entry.is_file():
            exec_bits = stat.S_IMODE(entry.stat().st_mode) & 0o111
            shutil.copyfile(entry, dest)
            os.chmod(dest, 0o444 | exec_bits)
        else:
            raise SnapshotError(
                f"Pi tree entry {rel} is not a regular file, directory, or symlink"
            )
    for entry in sorted((p for p in destination.rglob("*") if p.is_dir()), key=lambda p: len(p.parts), reverse=True):
        os.chmod(entry, 0o555)


def _exclude_launcher(manifest: TreeManifest, launcher_rel: Path) -> TreeManifest:
    """Return *manifest* minus the consumer launcher and an emptied parent.

    The assembler's published tree has no launcher; the admitted tree adds
    exactly ``bin/pi``.  Dropping the launcher (and its parent directory when
    it holds nothing else) reconstructs the assembler's canonical published
    view so the digest can be compared against the evidence.
    """
    launcher_path = launcher_rel.as_posix()
    parent_path = launcher_rel.parent.as_posix()
    entries = [e for e in manifest.entries if e.path != launcher_path]
    if parent_path != ".":
        has_children = any(
            e.path != parent_path and e.path.startswith(parent_path + "/")
            for e in entries
        )
        if not has_children:
            entries = [e for e in entries if e.path != parent_path]
    return TreeManifest(
        entries=tuple(entries),
        digest=canonical_tree_digest(entries),
    )


def _content_signature(entries: Iterable) -> tuple:
    """Content signature per entry: path, kind, digest, target, file exec bits.

    Mode/UID/GID are deliberately excluded because the copy normalizes write
    bits and directory modes, and re-owns the tree; only content identity and
    file executable bits are meaningful for the copy.
    """
    return tuple(
        (
            e.path,
            e.kind,
            e.digest,
            e.target,
            e.mode & 0o111 if e.kind == "file" else None,
        )
        for e in entries
    )


def _validate_derived_environment(derived: DerivedEnvironmentSource) -> AssemblerEvidence:
    """Validate every derived-environment binding before any copy occurs.

    Re-verifies the assembler-evidence byte digest and its parsed
    output-identity and tree-digest bindings, re-maps the source tree against
    the evidence, and re-verifies the launcher-evidence byte digest plus the
    launcher contents, mode, resolved target, and containment.  Raises
    :class:`SnapshotError` on any mismatch before a single byte is copied.
    """
    try:
        if (
            hashlib.sha256(derived.assembler_evidence).hexdigest()
            != derived.assembler_evidence_bytes_digest
        ):
            raise SnapshotError(
                "assembler evidence digest does not match the attestation"
            )
        evidence = parse_evidence(derived.assembler_evidence)
        if evidence.evidence_digest != derived.assembler_evidence_digest:
            raise SnapshotError(
                "assembler evidence body digest does not match the attestation"
            )
        if evidence.output_identity != derived.assembled_output_identity:
            raise SnapshotError(
                "assembler evidence output identity does not match the attestation"
            )
        if evidence.tree_digest != derived.canonical_tree_digest:
            raise SnapshotError(
                "assembler evidence tree digest does not match the attestation"
            )
        source_manifest = build_tree_manifest(derived.environment_root)
        if source_manifest.entries != evidence.body.tree_entries:
            raise SnapshotError(
                "assembled Pi source tree does not match the assembler evidence"
            )
        if source_manifest.digest != evidence.tree_digest:
            raise SnapshotError(
                "assembled Pi source tree digest does not match the assembler evidence"
            )

        if (
            hashlib.sha256(derived.launcher_evidence).hexdigest()
            != derived.launcher_evidence_digest
        ):
            raise SnapshotError(
                "launcher evidence digest does not match the attestation"
            )
        launcher_evidence_obj = validate_launcher_evidence(
            derived.launcher_evidence,
            launcher_contents=derived.launcher_contents,
            environment_root=derived.environment_root,
        )
        if launcher_evidence_obj.mode != derived.launcher_mode:
            raise SnapshotError("launcher mode does not match the launcher evidence")
        return evidence
    except (LockedNpmError, PiConsumerError, OSError, ValueError) as exc:
        raise SnapshotError(f"derived environment validation failed: {exc}") from exc


def admit_derived_environment(staging: Path, derived: DerivedEnvironmentSource) -> dict[str, object]:
    """Validate, copy, and re-validate the Pi environment into *staging*.

    Returns canonical manifest entries for the admitted set.  The complete
    derived-environment attestation is validated against the source tree, both
    evidence sets, and the launcher before any copy; the tree is then copied
    (executable bits preserved, write bits removed), the launcher and evidence
    are written, and the copied staging tree is recomputed and re-validated
    against the evidence before publication.  Any mismatch raises
    :class:`SnapshotError` and the caller removes staging.
    """
    evidence = _validate_derived_environment(derived)

    launcher_rel = Path("bin/pi")
    isolation = staging / _PI_ISOLATION_DIR
    tree_dest = staging / _PI_TREE_DIR
    _copy_contained_tree(derived.environment_root, tree_dest)
    launcher = staging / _PI_LAUNCHER
    launcher.parent.mkdir(parents=True, exist_ok=True)
    launcher.write_bytes(derived.launcher_contents)
    os.chmod(launcher, derived.launcher_mode)
    assembler_evidence = staging / _PI_ASSEMBLER_EVIDENCE
    assembler_evidence.write_bytes(derived.assembler_evidence)
    os.chmod(assembler_evidence, 0o444)
    launcher_evidence = staging / _PI_LAUNCHER_EVIDENCE
    launcher_evidence.write_bytes(derived.launcher_evidence)
    os.chmod(launcher_evidence, 0o444)

    # Recompute the copied staging tree (launcher excluded) and re-validate it
    # against the evidence, closing the validation-to-copy race.
    copied_view = _exclude_launcher(build_tree_manifest(tree_dest), launcher_rel)
    if copied_view.digest != derived.canonical_tree_digest:
        raise SnapshotError("copied Pi tree digest does not match the attestation")
    if _content_signature(copied_view.entries) != _content_signature(
        evidence.body.tree_entries
    ):
        raise SnapshotError("copied Pi tree differs from the validated source")

    # Finalize the launcher directory, the tree root, its parent, and the
    # isolation directory itself now that the launcher and evidence have been
    # written beneath them, making the entire isolated directory immutable.
    os.chmod(launcher.parent, 0o555)
    os.chmod(tree_dest, 0o555)
    os.chmod(isolation / "opt", 0o555)
    os.chmod(isolation, 0o555)
    return {
        "isolation_dir": _PI_ISOLATION_DIR.as_posix(),
        "tree": {"path": _PI_TREE_DIR.as_posix()},
        "launcher": {
            "path": _PI_LAUNCHER.as_posix(),
            "sha256": hashlib.sha256(derived.launcher_contents).hexdigest(),
            "mode": f"0o{derived.launcher_mode:o}",
        },
        "assembler_evidence": {
            "path": _PI_ASSEMBLER_EVIDENCE.as_posix(),
            "sha256": hashlib.sha256(derived.assembler_evidence).hexdigest(),
        },
        "launcher_evidence": {
            "path": _PI_LAUNCHER_EVIDENCE.as_posix(),
            "sha256": hashlib.sha256(derived.launcher_evidence).hexdigest(),
        },
    }


def create_artifact_snapshot(
    selected: Iterable[SelectedBuildArtifact], blobs: Iterable[Path], *, checkout_root: str | Path,
    cache_root: str | Path | None = None, project_state: ProjectState | None = None,
    derived: DerivedEnvironmentSource | None = None,
) -> MaterializedSnapshot:
    """Create a narrow immutable snapshot, preferring hard links to blobs.

    The manifest is canonical JSON and contains no cache paths or URLs.  Each
    source blob is opened and validated through a no-follow descriptor before
    publication; a copied fallback streams from that retained descriptor.  A
    hard link is accepted only after the linked destination is opened
    descriptor-relatively and its identity (``st_dev``/``st_ino``) is compared
    against the validated source inode, closing the pathname-replacement
    window between linking and publication.
    """
    entries = tuple(zip(selected, blobs, strict=True))
    if {entry.name for entry, _ in entries} != set(_LOGICAL_NAMES):
        raise SnapshotError("snapshot requires exactly the selected reviewed artifacts")
    paths = prepare_build_cache(checkout_root, cache_root=cache_root, project_state=project_state)
    staging = Path(tempfile.mkdtemp(prefix="transaction-", dir=paths.generated_root))
    try:
        staging_fd = os.open(staging, _NOFOLLOW_DIR)
    except OSError as exc:
        try:
            cleanup_artifact_snapshot(staging)
        except BaseException:
            pass
        raise SnapshotError(f"cannot open snapshot staging directory {staging}: {exc}") from exc
    try:
        manifest_entries: list[dict[str, str]] = []
        hard_linked: set[Path] = set()
        for item, blob in sorted(entries, key=lambda pair: _LOGICAL_NAMES[pair[0].name]):
            destination_name = _LOGICAL_NAMES[item.name]
            expected = item.identity.hex_digest()
            source_fd = _open_validated_source(blob, expected)
            try:
                source_stat = os.fstat(source_fd)
                try:
                    os.link(blob, destination_name, follow_symlinks=False, dst_dir_fd=staging_fd)
                except OSError as exc:
                    if exc.errno not in _HARD_LINK_UNAVAILABLE:
                        raise SnapshotError(
                            f"cannot hard link snapshot payload {destination_name!r} "
                            f"from source blob {blob}: {exc}"
                        ) from exc
                    _copy_source_fd_to_destination(source_fd, destination_name, staging_fd, expected)
                else:
                    try:
                        _validate_hard_link_destination(
                            destination_name, staging_fd, source_stat, expected)
                    except BaseException:
                        try:
                            os.unlink(destination_name, dir_fd=staging_fd)
                        except OSError:
                            pass
                        raise
                    hard_linked.add(Path(destination_name))
            finally:
                os.close(source_fd)
            manifest_entries.append({"name": item.name, "filename": destination_name,
                                     "sha256": item.identity.hex_digest()})
        manifest = staging / "manifest.json"
        manifest_body: dict[str, object] = {"artifacts": manifest_entries}
        if derived is not None:
            manifest_body["pi"] = admit_derived_environment(staging, derived)
        manifest.write_bytes((json.dumps(manifest_body, sort_keys=True,
                                         separators=(",", ":")) + "\n").encode())
        _readonly_tree(staging, hard_linked,
                       derived_root=_PI_ISOLATION_DIR if derived is not None else None)
        validate_host_owner_traversal(staging)
        return MaterializedSnapshot(path=staging, manifest=manifest)
    except BaseException:
        # Preserve the construction failure even if best-effort cleanup meets
        # an unrelated filesystem error after finalisation.
        try:
            cleanup_artifact_snapshot(staging)
        except BaseException:
            pass
        raise
    finally:
        os.close(staging_fd)


def cleanup_artifact_snapshot(snapshot: MaterializedSnapshot | Path | None) -> None:
    if snapshot is None:
        return
    path = snapshot.path if isinstance(snapshot, MaterializedSnapshot) else snapshot
    # A readonly tree is removable only after its parent control directory
    # unlinks it; shutil handles the child permissions on supported hosts.
    try:
        shutil.rmtree(path)
    except FileNotFoundError:
        return
    except PermissionError:
        # Unlinking a file requires write permission on its parent directory,
        # not on the file itself. Snapshot payloads may be hard links to
        # immutable cache blobs, so chmodding files here would also corrupt the
        # cached blob mode and make the next build reject an otherwise valid
        # hit. Restore write/traverse permission only on snapshot directories.
        for entry in sorted(path.rglob("*"), key=lambda p: len(p.parts), reverse=True):
            if entry.is_dir() and not entry.is_symlink():
                try: os.chmod(entry, 0o700)
                except OSError: pass
        try: os.chmod(path, 0o700)
        except OSError: pass
        shutil.rmtree(path, ignore_errors=True)
        if path.exists() or path.is_symlink():
            raise SnapshotError(f"failed to remove transaction snapshot: {path}")
