## Why

The content-addressed runtime-artifact cache is currently stored beneath the repository checkout. Rootless Docker can create this directory under a mapped container identity, leaving an otherwise accessible group-owned directory that the host constructor cannot secure with owner-only permissions. Persistent user cache state must not depend on checkout ownership or be confused with generated projections and evidence.

## What Changes

- Move the HTTP update-discovery cache from the legacy `${XDG_CACHE_HOME:-~/.cache}/pi-cli/versioning` path to `XDG_CACHE_HOME/docker-constructor/versioning` when `XDG_CACHE_HOME` is non-empty and absolute, creating a missing directory with `0700` or requiring an existing writable directory; otherwise use `~/.cache/docker-constructor/versioning` only for empty or non-absolute XDG values.
- Move the default runtime-artifact cache from `.docker-generated/runtime-artifacts/blobs` to the validated XDG root's `runtime-artifacts/blobs` child when `XDG_CACHE_HOME` is non-empty and absolute, creating a missing directory with `0700` or requiring an existing writable directory; use `~/.cache/docker-constructor/runtime-artifacts/blobs` only when XDG is empty or non-absolute, and fail for an unusable explicit absolute XDG path without fallback.
- Define the validated XDG root or `~/.cache/docker-constructor` fallback as the shared default root for persistent constructor caches.
- **BREAKING:** Remove the HTTP-only `check-updates --cache-dir` and `check-updates --cache-ttl` options. Configure the shared cache root through local `[cache].dir` and configure HTTP cache TTL only through reviewed `[cache].ttl`; retain `--no-cache` for one-off cache bypass.
- Apply and verify owner-only permissions for constructor-owned cache directories and cache files; fail with actionable recovery guidance when an existing cache cannot be secured by the invoking user.
- Keep `.docker-generated/runtime/` projections and `.docker-generated/evidence/` outputs repository-local because they are generated run/evidence state, not reusable user caches.
- Document the active cache layout, dedicated local-root rules, and permission recovery without adding legacy cache paths to maintained README guidance.

## Capabilities

### New Capabilities

- `user-cache-storage`: Defines the shared XDG cache layout, ownership and permission contract, migration behavior, and active-cache guidance for persistent constructor caches.

### Modified Capabilities

- `docker-runtime`: Changes the host location of the verified runtime-artifact cache while preserving individual read-only artifact mounts and repository-local runtime projections.
- `docker-build-reproducibility`: Changes the default machine-local cache layout while retaining a dedicated local cache-root override and reviewed TTL semantics.
- `runtime-host-access`: Clarifies that local cache configuration selects a dedicated machine-local constructor cache root for all cache consumers.

## Impact

- Adds `docker/versioning/cache_storage.py` as the acyclic owner of shared cache-root resolution, namespaced paths, and private-directory hardening; removes `--cache-dir` and `--cache-ttl` parsing and propagation; affects `constructor_cli.py`, `readonly_service.py`, `artifact_cache.py`, `cache.py`, `transports.py`, `launcher.py`, cache-path rendering, tests, maintenance scripts, and maintained README translations.
- Existing callers that pass `--cache-ttl` must move the value to reviewed `[cache].ttl` in `docker-constructor.toml`; callers that pass `--cache-dir` must move the path to `[cache].dir` in the resolved local companion.
- Entries formerly held by either legacy cache may be rebuilt once at the new default location; neither the legacy HTTP cache nor the legacy checkout-local artifact cache is automatically read, copied, deleted, or trusted.
- Does not change cache contents, artifact identity, network policy, container mount targets, reviewed configuration, or Docker invocation semantics.
