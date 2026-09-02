## Why

Constructor currently implements owner-private filesystem locking, durable replacement, interruption recovery, and cleanup independently in build artifacts, runtime artifacts, and npm-environment publication. The duplication has already produced a build-cache recovery defect: interruption after durable cleanup-intent publication but before committed-manifest replacement leaves a journal that blocks every later transaction.

This change follows completion and archival of `materialize-build-artifacts-on-host`. It introduces one layered filesystem-transaction substrate, fixes that deferred-cleanup recovery defect through the shared state machine, and migrates all existing lock implementations without changing their domain-specific concurrency policies.

## What Changes

- Add a dedicated layered transaction module tree for owner-private durable I/O, validated advisory file locks, typed live-lock capabilities, versioned journals, and recoverable single-authority transitions with idempotent deferred cleanup.
- Distinguish interrupted transitions by comparing the current authoritative-state fingerprint with both the recorded previous and intended fingerprints: discard uncommitted intent when the previous state remains authoritative, roll cleanup forward when the intended state is authoritative, and fail without mutation on conflict.
- Refactor the archived build-artifact implementation to use the shared substrate for its checkout-wide nonblocking lock, committed-manifest transition, pending cleanup, and durable control files while retaining build-specific digest validation, marker TTL, snapshot recovery, and blob deletion policy.
- Refactor all existing runtime-artifact and npm-environment lock implementations to use the common lock and durable-I/O layers while preserving their identity-scoped blocking behavior, immutable publication, quarantine, evidence validation, and cache ownership boundaries.
- Provide explicit extension seams for later multi-target publication and compare-and-swap adapters; those stronger protocols remain owned by the changes that require them.
- Update relevant planned changes to consume or deliberately extend this substrate instead of introducing additional lock, journal, or durable-write implementations.

## Capabilities

### New Capabilities
- `durable-filesystem-transactions`: Defines secure owner-private locks, durable filesystem state transitions, deterministic interruption recovery, and safe extension boundaries for Constructor-owned state.

### Modified Capabilities

None. Existing externally observable build-cache, runtime-artifact, and npm-environment behavior remains unchanged; the known build-cache recovery defect is brought into conformance with its existing interruption-recovery contract.

## Impact

Affected code includes a new `docker/transactions/` package plus `docker/versioning/build_cache.py`, `docker/versioning/artifact_cache.py`, `docker/npm_environment/publication.py`, `docker/npm_environment/storage.py`, and overlapping durable helpers in versioning projection/rendering code where their semantics match. Tests will cover shared primitives, fault injection at every durability boundary, policy-preserving consumer migrations, and removal of duplicate implementations.

The change must be implemented only after `materialize-build-artifacts-on-host` is complete and archived. Planned `add-locked-image-owned-pi-extensions` work will extend the substrate for multi-target publication and user-settings CAS semantics; metadata-cache work may consume durable I/O without adopting journals or broad locks.
