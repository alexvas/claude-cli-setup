## Context

After `materialize-build-artifacts-on-host` is completed and archived, the repository will contain four overlapping lock paths: checkout-wide build locking, runtime-artifact identity locking, npm-environment identity coordination, and npm storage lock preparation. Atomic replacement, owner/no-follow reads, directory fsync, and cleanup handling are also repeated across cache, projection, and rendering modules.

The archived build implementation intentionally becomes the reference consumer. Its initial local cleanup journal has a known recovery defect: it writes the superseded set before manifest replacement, but recovery rejects that set whenever the old manifest still references it. A crash in that window therefore blocks all later transactions. This defect is accepted temporarily in order to finish and archive the originating change; this change owns its correction during migration.

Existing consumers have different authority and contention semantics. Build serialization is checkout-wide and nonblocking. Runtime artifact and npm assembly coordination are identity-scoped and blocking. Immutable content-addressed publication does not need the same journal protocol as mutable authoritative manifest replacement.

## Goals / Non-Goals

**Goals:**
- Establish one security-reviewed implementation of owner-private file locks and durable filesystem operations.
- Provide a narrow recoverable single-authority transition for atomic publication followed by idempotent destructive cleanup.
- Migrate every existing Python lock implementation while preserving scope, waiting policy, diagnostics, and domain ownership.
- Correct the archived build-cache pre-manifest interruption defect and test every transition boundary.
- Give planned multi-target and externally mutable-state work explicit extension seams.

**Non-Goals:**
- Provide general ACID transactions, distributed locks, leases, lock expiry, Windows locking, or network-filesystem guarantees beyond supported `flock` semantics.
- Move digest validation, TTL policy, tree evidence, quarantine, snapshot lifecycle, or domain path derivation into generic infrastructure.
- Implement multi-target lockfile publication or settings CAS in this change.
- Alter public CLI behavior, cache locations, retention duration, or dry-run side effects.

## Decisions

### Build a layered package instead of one transaction class

Create `docker/transactions/` with narrowly directed dependencies:

```text
errors
  ▲
  ├──────── durable_io
  ├──────── locking
  └──────── journal
                ▲
                │
             transition
                ▲
                │ domain adapters
       ┌────────┼───────────────┐
   build cache  artifact cache  npm environment
```

`durable_io` owns private temporary files, full writes, fsync, atomic replacement, durable unlink, and validated no-follow reads. `locking` owns lock-file preparation, validation, `flock`, contention policy, release, and namespace-bound live capabilities. `journal` owns a versioned closed envelope and codecs but not domain identities. `transition` owns the previous/intended/conflict decision and execution order.

Alternative considered: a single callback-heavy transaction context manager. Rejected because it would hide authority boundaries and make it easy for generic recovery to delete unvalidated domain paths.

### Make lock capability explicit and namespace-bound

Acquisition returns a non-forgeable-in-normal-use capability carrying the normalized namespace and live descriptor state. Protected shared operations require that capability and reject released or mismatched instances. Consumers choose `BLOCK` or `FAIL_FAST`; defaults are avoided because contention is product behavior.

The common implementation validates no-follow type, effective owner, single link, and mode under the acquired descriptor. Existing path-bootstrap rules remain domain adapters where roots differ. No lock acquisition repairs checkout ancestors or unrelated entries.

Alternative considered: expose only a context manager yielding `None`. Rejected because nested domain helpers could then be called without evidence that the correct lock remains live.

### Separate generic durability from domain serialization

The durable layer operates on bytes. Canonical JSON encoding is a thin deterministic codec over it. Domain modules remain responsible for closed schema validation and conversion from strings to safe identities before constructing any path.

Temporary files are siblings of the destination to preserve same-filesystem replacement. Success requires file flush, replacement, and parent-directory flush. Durable unlink flushes the parent. Every descriptor is closed through `finally`, including synchronization failures.

Alternative considered: centralize all JSON schemas. Rejected because manifests, markers, metadata envelopes, and npm evidence have different authorities and evolution rules.

### Journal fingerprints and bounded operations, not executable paths

A single-authority journal records:
- schema and protocol version;
- transaction identifier;
- canonical previous-state fingerprint;
- canonical intended-state fingerprint;
- domain name and domain payload version;
- a canonical bounded cleanup payload validated by the domain adapter;
- protocol phase only when it adds recovery information rather than duplicating filesystem truth.

It does not store arbitrary commands or unchecked absolute deletion paths. The domain adapter decodes identities, validates canonical form and containment, and produces idempotent cleanup operations.

Alternative considered: journal arbitrary path lists for maximal reuse. Rejected because a corrupt journal would become generic deletion authority.

### Treat authoritative state as the commit oracle

The transition order is:

```text
validate old/new/cleanup under lock
              │
              ▼
durably write intent(previous, intended, cleanup)
              │
              ▼
durably replace authoritative state       ← commit point
              │
              ▼
run bounded idempotent cleanup
              │
              ▼
durably remove intent
```

Recovery reads and validates both journal and authority:

```text
current fingerprint == previous
    → pre-commit interruption
    → remove journal only

current fingerprint == intended
    → committed interruption
    → run/retry cleanup, then remove journal

otherwise
    → conflict
    → preserve journal and all targets; fail
```

This directly fixes the archived build defect. A mere overlap test between the cleanup set and current live set is forbidden because overlap is expected before commit.

Alternative considered: phase alone determines recovery. Rejected because a crash can occur between authoritative replacement and phase update; filesystem authority is the reliable oracle.

### Migrate consumers without homogenizing policy

- Build cache uses a checkout namespace with `FAIL_FAST`, then adapts committed manifest bytes/fingerprints and canonical digest cleanup. Build markers, retention and snapshots remain local.
- Runtime artifact materialization uses digest identity namespaces with `BLOCK`; its fast-path/recheck/publication pipeline remains unchanged and does not adopt transition journals.
- npm environment publication/storage uses input-identity namespaces with `BLOCK`; immutable-tree publication, evidence, quarantine and collision handling remain local.
- Projection/rendering code adopts durable helpers only where exact atomicity, ownership, and overwrite semantics match. No forced migration is allowed where hard-link no-clobber publication or other semantics differ.

Migration tests assert policy and failure behavior rather than merely replacing imports.

### Let future changes own stronger adapters

`add-locked-image-owned-pi-extensions` will consume the common lock/durable layers and extend journal/transition interfaces for two distinct protocols:
- all-or-nothing multi-target checked-in lockfile publication, able to complete the candidate generation or restore the prior generation;
- settings plus sidecar reconciliation with fingerprints/CAS so newer user edits are never overwritten.

`revalidate-update-metadata` consumes durable I/O for replaceable cache envelopes but not journals or broad locks, because metadata cache is disposable rather than authoritative.

Alternative considered: implement speculative multi-target and CAS engines now. Rejected because their authoritative conflict and rollback semantics should be driven by their owning requirements and tests.

## Risks / Trade-offs

- **[An abstraction weakens a consumer's security checks]** → Keep bootstrap, identity parsing, containment and deletion authority in domain adapters; require policy-parity tests before removing local code.
- **[A generic journal becomes arbitrary deletion authority]** → Store canonical domain payloads, never executable paths, and require adapter validation before any cleanup.
- **[Fingerprint instability makes valid recovery conflict]** → Fingerprint canonical authoritative bytes or a domain-defined canonical state, with deterministic serialization tests.
- **[A lock migration changes waiting behavior]** → Make contention policy mandatory and test concurrent same/different namespaces for every consumer.
- **[Refactoring several mature paths creates a large blast radius]** → Land shared primitives and fault tests first, migrate one consumer at a time, and delete duplication only after each parity suite passes.
- **[POSIX-specific primitives appear portable]** → Keep platform support explicit and fail clearly where required `flock`, no-follow, or directory-fsync semantics are unavailable.
- **[The known build defect survives too long]** → Record it explicitly here and make its reproducer the first build-migration RED test.

## Migration Plan

1. Complete and archive `materialize-build-artifacts-on-host` independently, retaining its current local transaction implementation and documented recovery defect.
2. Add shared durable-I/O and lock primitives with direct security, concurrency, and fault-injection tests.
3. Add the journal envelope and single-authority transition with pre-commit, post-commit, partial-cleanup, conflict, corrupt-journal, and durability-boundary tests.
4. Migrate archived build-cache code first and remove its local lock/durable/journal implementation; prove the known defect is corrected.
5. Migrate runtime artifact and npm environment locks independently, preserving identity granularity and blocking behavior.
6. Consolidate exactly matching projection/rendering durability helpers without changing no-clobber semantics.
7. Run complete cache, build, npm environment, launcher, versioning and acceptance suites; verify no duplicate production `flock` implementations remain outside the shared package or documented platform adapter.

Rollback is source-level: each consumer migration remains separable until its duplicate implementation is removed. Persistent on-disk build state is migrated compatibly or through an explicitly tested journal-version adapter; no silent deletion of an unknown journal format is allowed.
