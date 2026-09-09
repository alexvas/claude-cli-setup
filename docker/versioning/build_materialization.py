"""Host-side selection and streaming materialization of reviewed build artifacts."""
from __future__ import annotations

import hashlib
import os
import ssl
import stat
import tempfile
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Protocol

from docker.versioning.build_cache import (
    BLOB_EXTENSION, BuildCacheError, ConstructorProjectBuildLock, build_blob_path,
    mark_uncommitted_blob, prepare_build_cache,
)
from docker.versioning.digest_identity import DigestIdentity
from docker.versioning.project_state import ProjectState
from docker.versioning.model import EffectiveBuildProjection


class MaterializationError(RuntimeError):
    """Artifact selection, transport, or integrity failure safe for display."""


@dataclass(frozen=True)
class SelectedBuildArtifact:
    name: str
    url: str
    identity: DigestIdentity


@dataclass(frozen=True)
class HostNetworkPolicy:
    proxy_url: str | None = None
    ca_bundle: Path | None = None


class StreamingTransport(Protocol):
    def stream(self, url: str) -> Iterable[bytes]: ...


class UrllibStreamingTransport:
    """One host HTTP policy implementation; response bodies are never buffered."""
    def __init__(self, policy: HostNetworkPolicy = HostNetworkPolicy()) -> None:
        handlers: list[urllib.request.BaseHandler] = []
        if policy.proxy_url is not None:
            handlers.append(urllib.request.ProxyHandler({
                "http": policy.proxy_url, "https": policy.proxy_url,
            }))
        if policy.ca_bundle is not None:
            try:
                context = ssl.create_default_context(cafile=os.fspath(policy.ca_bundle))
            except (OSError, ssl.SSLError):
                raise MaterializationError(
                    "host artifact transport configuration failed"
                ) from None
            handlers.append(urllib.request.HTTPSHandler(context=context))
        self._opener = urllib.request.build_opener(*handlers)

    def stream(self, url: str) -> Iterable[bytes]:
        try:
            with self._opener.open(url) as response:
                while chunk := response.read(1024 * 1024):
                    yield chunk
        except Exception as exc:
            # Never include the request URL (or proxy URL) in diagnostics.
            raise MaterializationError(
                f"artifact transport failed ({type(exc).__name__})"
            ) from None


def select_build_artifacts(projection: EffectiveBuildProjection) -> tuple[SelectedBuildArtifact, ...]:
    """Select exactly the four effective artifacts supported by this change."""
    if projection.platform != "linux-amd64":
        raise MaterializationError(
            f"unsupported build-artifact platform {projection.platform!r}; expected 'linux-amd64'"
        )
    values = (
        ("rustup", projection.rust.rustup),
        ("uv", projection.uv.artifact),
        ("rtk", projection.rtk.artifact),
        ("fd", projection.fd.artifact),
    )
    try:
        return tuple(SelectedBuildArtifact(
            name=name, url=artifact.url,
            identity=DigestIdentity.from_hex("sha256", artifact.sha256),
        ) for name, artifact in values)
    except (TypeError, ValueError) as exc:
        raise MaterializationError(f"invalid reviewed build-artifact digest: {exc}") from None


def _verify_hit(path: Path, identity: DigestIdentity) -> bool:
    try:
        st = path.lstat()
        if not stat.S_ISREG(st.st_mode) or stat.S_IMODE(st.st_mode) != 0o444:
            return False
        digest = hashlib.new(identity.algorithm)
        with path.open("rb") as source:
            while chunk := source.read(1024 * 1024):
                digest.update(chunk)
        return digest.digest() == identity.digest_bytes
    except (FileNotFoundError, OSError):
        return False


def materialize_artifact(
    selected: SelectedBuildArtifact, *, constructor_project_root: str | Path,
    transport: StreamingTransport, cache_root: str | Path | None = None,
    project_state: ProjectState | None = None, lock: ConstructorProjectBuildLock | None = None,
) -> Path:
    """Reuse a verified hit or stream, verify, and atomically publish a miss."""
    paths = prepare_build_cache(constructor_project_root, cache_root=cache_root, project_state=project_state)
    destination = build_blob_path(paths.blobs_root, selected.identity)
    if _verify_hit(destination, selected.identity):
        return destination
    if destination.exists() or destination.is_symlink():
        raise MaterializationError(f"unsafe or corrupt cached artifact {selected.name!r}")

    destination.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    fd, temporary_name = tempfile.mkstemp(prefix=".materialize-", dir=paths.tmp_root)
    temporary = Path(temporary_name)
    digest = hashlib.new(selected.identity.algorithm)
    try:
        with os.fdopen(fd, "wb") as output:
            for chunk in transport.stream(selected.url):
                if not isinstance(chunk, bytes):
                    raise MaterializationError("artifact transport yielded non-byte data")
                output.write(chunk)
                digest.update(chunk)
            output.flush()
            os.fsync(output.fileno())
        if digest.digest() != selected.identity.digest_bytes:
            raise MaterializationError(
                f"integrity check failed for artifact {selected.name!r}"
            )
        os.chmod(temporary, 0o444)
        os.replace(temporary, destination)
        if not _verify_hit(destination, selected.identity):
            try: destination.unlink()
            except OSError: pass
            raise MaterializationError(f"published artifact {selected.name!r} failed verification")
        if lock is not None:
            try:
                mark_uncommitted_blob(
                    selected.identity, constructor_project_root, lock=lock,
                    cache_root=cache_root, project_state=project_state,
                )
            except BaseException:
                try: destination.unlink()
                except OSError: pass
                raise
        return destination
    except MaterializationError:
        raise
    except BaseException as exc:
        raise MaterializationError(
            f"artifact materialization failed for {selected.name!r} ({type(exc).__name__})"
        ) from None
    finally:
        try: temporary.unlink()
        except FileNotFoundError: pass


def materialize_build_artifacts(
    projection: EffectiveBuildProjection, *, constructor_project_root: str | Path,
    transport: StreamingTransport, cache_root: str | Path | None = None,
    project_state: ProjectState | None = None, lock: ConstructorProjectBuildLock | None = None,
) -> tuple[Path, ...]:
    results: list[Path] = []
    for selected in select_build_artifacts(projection):
        results.append(materialize_artifact(
            selected, constructor_project_root=constructor_project_root, transport=transport,
            cache_root=cache_root, project_state=project_state, lock=lock,
        ))
    return tuple(results)
