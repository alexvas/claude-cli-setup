## Context

The builder declares every Compose build argument before its first `RUN`. BuildKit includes in-scope `ARG` values in subsequent `RUN` cache keys, so changing `OPENSPEC_VERSION` invalidates APT, Rust, uv, Cargo, and every later builder layer. Builder and runtime also start independently from the same Node image and install overlapping Debian packages. The APT cache mounts are emptied at the end of each install, and Cargo does not retain compilation targets.

The runtime copies the complete builder `/usr/local/lib/node_modules` snapshot before later setup. Consequently, changing either Pi or OpenSpec invalidates the same runtime boundary and reruns unrelated setup such as plugin installation.

## Goals / Non-Goals

**Goals:**
- Preserve stable and expensive layers when one tool version changes.
- Install shared operating-system prerequisites once in a reusable stage.
- Make BuildKit dependency caches useful after unavoidable layer invalidation.
- Give Pi and OpenSpec independent invalidation boundaries.
- Preserve the current runtime commands, paths, user, and tool availability.

**Non-Goals:**
- Guarantee byte-for-byte reproducible images; version pinning is covered by `pin-docker-toolchain-versions`.
- Minimize final image size at the expense of the interactive developer toolset.
- Introduce an external registry cache or CI-specific cache backend.

## Decisions

### Use a shared runtime base

Create a base stage containing the common Debian packages, locale, and dev-user setup. Derive both the tool builder and final runtime assembly from that stage. Builder-only packages remain in a descendant builder stage.

This is preferred over maintaining two optimized APT commands because a single parent layer naturally deduplicates both execution and stored content.

### Scope build arguments at the latest possible point

Remove unused build arguments and declare each retained `ARG` immediately before the instruction that consumes it. Stable setup runs before versioned Pi and OpenSpec installation. Because a changed parent necessarily invalidates descendants, the most frequently changed tool is placed last unless isolated into its own stage.

### Isolate independently versioned tools

Install Pi and OpenSpec in separate stages and separate prefixes rather than one shared `/usr/local/lib/node_modules` tree. Runtime assembly copies each prefix independently and exposes stable symlinks on `PATH`. Pi-dependent plugin setup belongs to the Pi branch; OpenSpec assembly remains independent and late.

Separate prefixes are preferred over copying selected files out of npm's shared global tree because npm packages can contain package-relative dependencies and executable links.

### Treat cache mounts as disposable build acceleration

APT list/archive directories remain cache mounts and are not deleted by the same `RUN`; the Debian `docker-clean` hook is disabled for the mounted archive cache. npm receives a cache mount for downloaded package data. Cargo receives registry, git, and compilation-target caches with ownership matching the build user.

No cache-mount contents are copied to the runtime image. Correctness must not depend on a warm cache.

### Verify cache boundaries on a Docker host

Verification performs two plain-progress builds and then changes one version at a time. The second unchanged build must be cached, while an OpenSpec-only change must not execute APT, Rust, uv, Cargo, or Pi installation. This repository's agent container has no Docker daemon, so these checks require the host.

## Risks / Trade-offs

- [A common base may contain packages needed by only one descendant] → Keep only genuinely shared/runtime-required packages in the base and measure final image contents.
- [Separate npm prefixes may change module resolution or executable links] → Expose explicit symlinks and run version/smoke commands in the final image.
- [Cargo target caches can consume substantial disk] → Use distinct cache identifiers and document normal BuildKit pruning.
- [APT cache behavior varies across Debian image revisions] → Configure cache retention explicitly and verify with cold layer-cache builds.
- [Multiple stages increase Dockerfile complexity] → Name stages by responsibility and document the dependency graph near the stage declarations.

## Verification Results

Docker-host verification is recorded in `verification.md`. The measured cold build completed in 524.88 seconds, an identical rebuild in 3.49 seconds, an OpenSpec-only rebuild in 15.02 seconds, and a Pi-only rebuild in 229.81 seconds. The final image measured 3.53 GB, and BuildKit reported 19.47 GB of cache with 13.32 GB reclaimable.

The cache boundaries met the requirements: the identical build reused every deterministic step; an OpenSpec-only change preserved APT, Rust, uv/Python, Cargo, MCP, Pi, and pi-read layers; and a Pi-only change preserved the independent OpenSpec installation. Runtime smoke and version checks passed as user `dev`.

The logs also exposed follow-up opportunities, especially moving stable runtime assembly before the Pi overlay, reducing the 1.58 GB Rust runtime tree, splitting the 155.4-second combined Cargo installation, and caching or isolating the 22–26-second pi-read installation. Recursive whole-home ownership work is handled by the separate `optimize-runtime-home-ownership` change.
