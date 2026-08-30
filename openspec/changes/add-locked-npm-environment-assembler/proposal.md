## Why

Managed npm roots can have arbitrary dependency closures and npm-specific placement semantics that the direct tarball extractor cannot safely reproduce. A shared locked assembler is needed so Pi itself and image-owned Pi extensions can consume exact reviewed lockfiles through one host-evidenced, script-free materialization boundary.

## What Changes

- Add a reusable standalone npm environment assembler executed from the inventory-pinned Node image digest before Docker build.
- Accept exact root intent plus standard `package-lock.json` v3, validate a strict registry-only subset, preserve validated functional `bin` and `engines.node` metadata separately for every reviewed root by package identity and lock path in the closed model while accepting role-specific shape-validated `license`, `funding`, and `deprecated`, transitive `bin`, and syntax-valid manifest/transitive engines as ignored npm metadata, and reject unreviewed local, git, link, workspace, traversal, bundled, integrity-less, unsafe executable-path, or incompatible Node-engine inputs.
- Expose a side-effect-free input preflight that returns a digest-bound immutable validated input with keyed metadata for all reviewed roots; require Docker-backed assembly to consume that exact validated input and matching lock bytes before running effects.
- Run `npm ci --ignore-scripts --no-bin-links --no-audit --no-fund` in private host-owned staging; permit lock metadata indicating install scripts but never execute them.
- Let npm download and verify locked SRI bytes while Constructor independently validates the resulting closure, paths, identities, permissions, symlinks, omissions, and canonical tree manifest.
- Publish validated environments atomically under deterministic identities derived from inputs, pinned assembler identity, platform, script digest, and policy version; fully revalidate cache hits.
- Provide one opaque assembler-owned npm download cache reusable by independent Pi and extension assemblies without making cache contents authoritative.
- Apply existing credential-free corporate proxy, CA, cancellation, locking, cleanup, redaction, and evidence requirements to assembler execution.
- Expose a consumer-neutral assembly result/evidence contract, including validated executable and Node-engine metadata for every reviewed root but no generated executable links; verify every reviewed root's `engines.node` against the caller-supplied reviewed exact Node version, without enabling npm `engine-strict`, enforcing transitive engine compatibility, or adding a custom transitive-engine diagnostic before Docker execution; Pi layout, launcher construction, extension roots, settings integration, CLI guards, named-context placement, and lock-refresh UX remain owned by dependent changes.
- Maintain a byte-exact repository fixture copied from a pinned published Pi install lock, with its Pi version read from the fixture itself and exact source URL and SHA-256 recorded as provenance, to prove the strict parser remains compatible with a real npm-produced closure without replacing synthetic negative and security tests.

## Capabilities

### New Capabilities

- `locked-npm-environment-assembly`: Validates lock inputs, runs the pinned standalone assembler, verifies and atomically publishes npm environment trees, and records host evidence.

### Modified Capabilities

- `user-cache-storage`: Adds a shared opaque npm download cache and content-addressed assembled-environment storage with explicit ownership and lifecycle boundaries.
- `corporate-network-configuration`: Applies resolved credential-free host proxy and trust policy to standalone assembler containers without persisting local network configuration.

## Impact

Affects Docker execution boundaries, Node image identity, lockfile parsing, npm invocation, host staging/cache security, filesystem-tree verification, corporate networking, cancellation and cleanup, evidence DTOs, and tests. The new capability is a prerequisite for the revised Pi build-materialization and managed-extension reconciliation changes, but does not itself adopt either consumer.
