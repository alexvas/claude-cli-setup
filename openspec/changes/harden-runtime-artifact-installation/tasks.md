## 1. Type the Runtime Artifact Contract

- [ ] 1.1 Add failing model, projection serialization, and closed-schema tests for a required runtime `install_type`; cover `npm-tarball` propagation and unknown-type rejection.
- [ ] 1.2 Add the closed installation-type model to reviewed runtime entries, host effective selections, container projection DTOs, TOML rendering/parsing, and compatibility fixtures.
- [ ] 1.3 Assert the declared installation type at the protected installer boundary before package-home mutation; keep current reviewed runtime entries explicitly `npm-tarball`.

## 2. Make npm Tarball Installation Transactional

- [ ] 2.1 Add failing installer tests for valid npm `package/` layout, missing/invalid metadata, unsafe or non-package members, unsupported archive types, and no target mutation on failure.
- [ ] 2.2 Add failing filesystem-boundary tests for staging cleanup, stale-file removal on replacement, replacement failure rollback, and exact post-install ownership/metadata validation.
- [ ] 2.3 Implement same-filesystem package-specific staging, strict npm tarball validation, metadata validation in staging, atomic target replacement, rollback, and cleanup without reopening the mounted artifact source.
- [ ] 2.4 Run focused installer, projection, and compatibility tests with fake archive/filesystem boundaries.

## 3. Harden Acceptance Evidence

- [ ] 3.1 Add tests or shell-level checks proving scenario 02 records its supplied offline-wrapper path and exact wrapped collector command.
- [ ] 3.2 Add a unique per-launch identifier to constructor evidence collection and inspect only the matching Docker container under concurrent same-image launches.
- [ ] 3.3 Record the launch identifier, inspected container ID, and offline-policy provenance in evidence output; preserve non-destructive cache and isolated-Pi-home behavior.
- [ ] 3.4 Run shell checks and collect/review real-Docker evidence for cache miss, offline cache hit, and concurrent-container identification when Docker is available.

## 4. Validate and Document

- [ ] 4.1 Update maintained developer/Docker documentation only if acceptance evidence collection is a supported workflow; document the host-network impact and restoration behavior of the sample offline wrapper.
- [ ] 4.2 Run the full test suite, Python compile/static checks, shell checks, `git diff --check`, and `openspec validate harden-runtime-artifact-installation --strict`.
