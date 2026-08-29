## Why

Managed npm roots can have arbitrary dependency closures and npm-specific placement semantics that the direct tarball extractor cannot safely reproduce. A shared locked assembler is needed so Pi itself and image-owned Pi extensions can consume exact reviewed lockfiles through one host-evidenced, script-free materialization boundary.

## What Changes

- Add a reusable standalone npm environment assembler executed from the inventory-pinned Node image digest before Docker build.
- Accept exact root intent plus standard `package-lock.json` v3, validate a strict registry-only subset, and reject unreviewed local, git, link, workspace, traversal, bundled, or integrity-less nodes.
- Run `npm ci --ignore-scripts --no-bin-links --no-audit --no-fund` in private host-owned staging; permit lock metadata indicating install scripts but never execute them.
- Let npm download and verify locked SRI bytes while Constructor independently validates the resulting closure, paths, identities, permissions, symlinks, omissions, and canonical tree manifest.
- Publish validated environments atomically under deterministic identities derived from inputs, pinned assembler identity, platform, script digest, and policy version; fully revalidate cache hits.
- Provide one opaque assembler-owned npm download cache reusable by independent Pi and extension assemblies without making cache contents authoritative.
- Apply existing credential-free corporate proxy, CA, cancellation, locking, cleanup, redaction, and evidence requirements to assembler execution.
- Expose a consumer-neutral assembly result/evidence contract; Pi layout, extension roots, settings integration, CLI guards, named-context placement, and lock-refresh UX remain owned by dependent changes.

## Capabilities

### New Capabilities

- `locked-npm-environment-assembly`: Validates lock inputs, runs the pinned standalone assembler, verifies and atomically publishes npm environment trees, and records host evidence.

### Modified Capabilities

- `user-cache-storage`: Adds a shared opaque npm download cache and content-addressed assembled-environment storage with explicit ownership and lifecycle boundaries.
- `corporate-network-configuration`: Applies resolved credential-free host proxy and trust policy to standalone assembler containers without persisting local network configuration.

## Impact

Affects Docker execution boundaries, Node image identity, lockfile parsing, npm invocation, host staging/cache security, filesystem-tree verification, corporate networking, cancellation and cleanup, evidence DTOs, and tests. The new capability is a prerequisite for the revised Pi build-materialization and managed-extension reconciliation changes, but does not itself adopt either consumer.
