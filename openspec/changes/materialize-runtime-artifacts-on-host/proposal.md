## Why

The runtime installer currently downloads selected npm artifacts inside the container even though the host resolver already knows their exact reviewed URLs and integrity values before `docker run`. Materializing and verifying those artifacts on the host enables cache reuse and offline launches, removes extension-download network access from the container, and lets the installer consume only individually mounted read-only blobs.

## What Changes

- Add a private content-addressed host cache for selected runtime artifacts, keyed by validated integrity identity rather than package name or URL.
- Make `run` ensure every selected artifact is present and verified before any Docker launch effect; cache misses download into private temporary state and publish atomically only after integrity succeeds.
- Mount only the selected cache blobs into the container as individual read-only file mounts at deterministic fixed targets.
- Narrow the effective runtime projection so the container receives mounted artifact identity/integrity and validation metadata, but not downloadable URLs or host cache paths.
- Remove runtime network downloading, downloader/workspace lifecycle, and mutable downloaded-path handling from the container installer.
- Retain defense-in-depth integrity verification inside the container before package execution, plus exact package metadata and ownership validation afterward.
- Define deterministic concurrency, corruption recovery, cancellation, cleanup, dry-run, and offline/cache-hit behavior for host materialization.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `docker-build-reproducibility`: Derive content-addressed runtime artifact identities from reviewed selections, materialize selected blobs on the host, and keep artifact URLs and host cache paths outside the container projection.
- `project-launcher`: Add pre-launch artifact materialization and deterministic individual read-only artifact mounts to the direct `docker run` transaction.
- `docker-runtime`: Replace container-side downloading with integrity verification and installation from fixed read-only mounted artifacts.

## Impact

- Runtime resolution/projection DTOs, host cache and transport boundaries, run planning/orchestration, Docker vector rendering, and launch cleanup.
- `docker/runtime_installer.py` protocols and production implementation; container-side `curl` is no longer used for extension installation.
- `.docker-generated` lifecycle and ignore rules for private content-addressed blobs and temporary downloads.
- Tests for cache identity, atomic publication, concurrency, corruption, offline behavior, mount isolation, projection closure, integrity ordering, and failure recovery.
- The change depends on the direct-Docker runtime projection and installer boundaries established by `replace-compose-with-direct-docker`; it supersedes that change's container-download design rather than duplicating a second installation path.
