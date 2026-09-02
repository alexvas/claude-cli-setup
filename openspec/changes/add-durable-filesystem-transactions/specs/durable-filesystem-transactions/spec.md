## Purpose

Define reusable security and recovery guarantees for Constructor processes that coordinate and durably mutate owner-private filesystem state.

## ADDED Requirements

### Requirement: Coordinate owner-private state through validated file locks
A side-effecting Constructor operation that adopts the shared transaction substrate SHALL acquire an advisory lock at its domain-selected scope before entering its critical section. Lock preparation and acquisition SHALL reject symlinks, non-regular files, foreign-owned files, and multiply linked files without mutating their targets. Each consumer SHALL explicitly select blocking or nonblocking contention behavior, and only a live lock capability for the same namespace SHALL authorize protected mutation.

#### Scenario: Rejecting an unsafe lock entry
- **WHEN** a lock path resolves to a symlink, non-regular entry, foreign-owned file, or multiply linked file
- **THEN** acquisition SHALL fail without chmodding, replacing, or otherwise mutating that entry or its target

#### Scenario: Preserving consumer contention policy
- **WHEN** two operations contend for the same lock namespace
- **THEN** the shared mechanism SHALL apply the consuming domain's declared blocking or nonblocking policy
- **AND** SHALL permit at most one holder to enter the protected critical section

#### Scenario: Rejecting a stale or unrelated capability
- **WHEN** protected mutation receives a released lock capability or one issued for another namespace
- **THEN** it SHALL fail before changing protected state

### Requirement: Publish and remove control state durably
Shared durable writes SHALL create complete private sibling state, flush its contents, atomically replace the destination, and flush the parent directory before reporting success. Shared durable removal SHALL unlink the owned entry and flush the parent directory before reporting success. Reads SHALL reject unsafe type or ownership without following a leaf symlink.

#### Scenario: Completing an atomic replacement
- **WHEN** a durable control-state replacement reports success
- **THEN** later processes SHALL observe the complete replacement rather than partial bytes
- **AND** the replacement and containing-directory entry SHALL have crossed their required durability boundaries

#### Scenario: Failing during replacement
- **WHEN** writing, flushing, replacement, or directory synchronization fails
- **THEN** the operation SHALL report failure
- **AND** SHALL remove any still-owned temporary entry without modifying an unrelated path

#### Scenario: Reading unsafe control state
- **WHEN** a control-state path is a symlink, non-regular entry, or foreign-owned entry
- **THEN** the read SHALL fail without following or repairing it

### Requirement: Recover single-authority transitions with deferred cleanup
A shared single-authority transition SHALL durably identify its previous state, intended state, and bounded idempotent cleanup before replacing authoritative state. Recovery under the same exclusive lock SHALL compare current authoritative state with both recorded states: previous state means publication did not commit and cleanup MUST NOT run; intended state means publication committed and cleanup SHALL resume; any other state means conflict and SHALL cause failure without cleanup or authoritative mutation.

#### Scenario: Interruption before authoritative replacement
- **WHEN** interruption occurs after durable transition intent but before authoritative state is replaced
- **THEN** recovery SHALL recognize the previous state as authoritative
- **AND** SHALL discard only transaction-owned intent state without performing post-commit cleanup

#### Scenario: Interruption after authoritative replacement
- **WHEN** interruption occurs after authoritative state is durably replaced but before cleanup completes
- **THEN** recovery SHALL recognize the intended state as authoritative
- **AND** SHALL retry the remaining idempotent cleanup before durably removing transaction state

#### Scenario: Conflicting authoritative state
- **WHEN** current authoritative state matches neither the recorded previous nor intended state
- **THEN** recovery SHALL fail without deleting cleanup targets, replacing authoritative state, or discarding evidence needed for diagnosis

#### Scenario: Interruption during cleanup
- **WHEN** interruption occurs after only part of post-commit cleanup completes
- **THEN** later recovery SHALL safely retry the complete bounded cleanup set
- **AND** already absent cleanup targets SHALL be treated idempotently

### Requirement: Preserve domain ownership and concurrency boundaries
Adoption of the shared substrate SHALL NOT broaden a consumer's lock scope, cache ownership, deletion authority, or filesystem traversal permissions. Domain adapters SHALL validate and derive every authoritative identity and cleanup target before passing bounded operations to the shared transition mechanism.

#### Scenario: Migrating identity-scoped caches
- **WHEN** runtime-artifact or npm-environment publication adopts shared locking
- **THEN** different identities SHALL remain independently concurrent
- **AND** contention for the same identity SHALL retain its existing blocking policy

#### Scenario: Migrating checkout build transactions
- **WHEN** checkout build state adopts the shared transition mechanism
- **THEN** its checkout-wide lock SHALL remain nonblocking
- **AND** build-specific manifest validation, marker retention, snapshot recovery, and blob-deletion authority SHALL remain confined to the checkout build domain

#### Scenario: Rejecting an unvalidated cleanup target
- **WHEN** a journal or domain adapter presents a malformed, noncanonical, escaping, or otherwise unowned cleanup identity
- **THEN** recovery SHALL fail without deleting any target

### Requirement: Expose bounded extension seams
The shared substrate SHALL permit later domain-owned adapters to add multi-target publication or compare-and-swap conflict rules without weakening single-authority recovery, lock validation, or durable-I/O guarantees. The base mechanism SHALL NOT claim atomic multi-file replacement or automatic reconciliation of externally mutable user state.

#### Scenario: Requesting stronger transaction semantics
- **WHEN** a consumer requires all-or-nothing replacement of multiple authoritative files or reconciliation with concurrent user edits
- **THEN** it SHALL supply an explicit stronger adapter and recovery contract
- **AND** SHALL NOT represent the base single-authority transition as providing those guarantees
