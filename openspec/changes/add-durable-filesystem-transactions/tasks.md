# Implementation Contract

This checklist is the binding implementation contract for `add-durable-filesystem-transactions`. A task is complete only when its stated production change or test evidence exists and its stated verification passes. A phase MAY depend only on lower-numbered phases listed in its `Depends on` line. Independent phases MAY be implemented in parallel. Within each phase, work proceeds in `RED → GREEN → INTROSPECT → VALIDATE` order; a later stage SHALL NOT be marked complete while an earlier stage in that phase remains incomplete.

The change SHALL begin only after `materialize-build-artifacts-on-host` is complete and archived. Its archived on-disk `pending-build-cleanup.json` format is a compatibility input, not a format that may be silently discarded or reinterpreted by generic infrastructure.

```text
Phase 1 ──┬──> Phase 3 ──> Phase 4 ───────────────┐
          ├───────────────> Phase 5 ───────────────┤
Phase 2 ──┼──> Phase 3     Phase 6 ───────────────┼──> Phase 8
          ├───────────────> Phase 5                │
          └───────────────> Phase 6                │
Phase 1 ──────────────────> Phase 7 ───────────────┘
```

## Phase 1. Durable Filesystem Primitives

**Depends on:** none
**Deliverables:** byte-oriented owner-private validated reads; durable same-directory atomic replacement; durable unlink; deterministic JSON codec; complete descriptor and temporary-entry cleanup.

- [ ] 1.1 **RED:** Add tests proving validated reads reject symlink, non-regular, and foreign-owned leaf entries without following or repairing them; verify the focused tests fail because the shared package does not exist.
- [ ] 1.2 **RED:** Add fault-injection tests proving durable replacement performs complete partial-write loops, file fsync before replace, same-directory atomic replace, and parent-directory fsync before success; verify every write/fsync/replace failure preserves a complete authoritative destination and removes only transaction-owned temporary state.
- [ ] 1.3 **RED:** Add fault-injection tests proving durable unlink flushes the parent directory, treats only the declared absent-target case idempotently, and closes every descriptor when open/unlink/fsync/close fails.
- [ ] 1.4 **RED:** Add deterministic JSON-codec tests proving canonical bytes are stable across mapping order, non-finite values and unsupported types are rejected before publication, and schema interpretation remains outside the codec.
- [ ] 1.5 **GREEN:** Create the `docker/transactions` package and implement the byte-oriented validated-read primitive required by task 1.1.
- [ ] 1.6 **GREEN:** Implement same-directory durable atomic byte replacement with private temporary state and complete failure cleanup required by task 1.2.
- [ ] 1.7 **GREEN:** Implement durable unlink and directory synchronization with unconditional descriptor closure required by task 1.3.
- [ ] 1.8 **GREEN:** Implement the deterministic JSON encode/decode boundary required by task 1.4 without adding domain schemas.
- [ ] 1.9 **INTROSPECT:** Review the Phase 1 API for descriptor leaks, leaf-following, ancestor repair, cross-filesystem rename, partial writes, false durability claims, implicit JSON authority, and cleanup that can replace the primary failure; resolve every finding and keep specialized no-clobber/tree operations out of the generic API.
- [ ] 1.10 **VALIDATE:** Run all Phase 1 tests under every injected write, fsync, replace, unlink, open, and close failure; record that no partial authoritative bytes, unrelated mutation, leaked descriptor, or transaction-owned temporary entry remains.

## Phase 2. Owner-Private Advisory Locks

**Depends on:** none
**Deliverables:** validated owner-private advisory lock; explicit blocking and fail-fast policies; namespace-bound live capability; safe acquisition/release and deterministic contention behavior.

- [ ] 2.1 **RED:** Add lock-entry tests covering symlink, non-regular, foreign-owned, multiply linked, and wrong-mode owner-owned lock files. Prove symlink, non-regular, foreign-owned, and multiply linked entries are rejected without chmod, replacement, or target mutation. Prove a safe owner-owned single-link regular lock with the wrong mode is accepted, is repaired to exactly `0600` only after exclusive lock acquisition, and leaves every ancestor and unrelated entry unchanged.
- [ ] 2.2 **RED:** Add process-level tests proving same-namespace exclusion, different-namespace concurrency, explicit `BLOCK` waiting, explicit `FAIL_FAST` rejection, and deterministic bootstrap behavior on a pristine root.
- [ ] 2.3 **RED:** Add capability tests proving protected operations reject released, cross-namespace, wrong-root, and otherwise non-live lock capabilities before mutation.
- [ ] 2.4 **RED:** Add lifecycle tests proving lock descriptors are released after success, ordinary exceptions, cancellation, validation failure, and contention failure.
- [ ] 2.5 **GREEN:** Implement secure lock-file preparation and descriptor validation required by task 2.1: accept a safe owner-owned single-link regular lock with the wrong mode and repair it to exactly `0600` only after exclusive ownership is established; reject rather than repair symlink, non-regular, foreign-owned, and multiply linked entries, without modifying ancestors or unrelated entries.
- [ ] 2.6 **GREEN:** Implement mandatory `BLOCK` and `FAIL_FAST` acquisition policies and namespace-scoped process coordination required by task 2.2.
- [ ] 2.7 **GREEN:** Implement namespace-bound live lock capabilities and protected-operation assertions required by task 2.3.
- [ ] 2.8 **GREEN:** Implement unconditional release and primary-error-preserving lifecycle handling required by task 2.4.
- [ ] 2.9 **INTROSPECT:** Review acquisition and capability use for pathname/descriptor TOCTOU windows, lock-order inversion, accidental default contention policy, descriptor inheritance, lock replacement, ancestor mutation, and capability reuse after release; resolve every finding without moving domain path authority into the shared layer.
- [ ] 2.10 **VALIDATE:** Run all Phase 2 security and deterministic multiprocessing tests; record that exactly one same-namespace holder enters, unrelated namespaces remain concurrent, safe wrong-mode owner-owned entries are repaired to exactly `0600` only while exclusively held, unsafe entries remain untouched, ancestors and unrelated entries are unchanged, and every outcome releases owned descriptors.

## Phase 3. Recoverable Single-Authority Transition

**Depends on:** Phase 1, Phase 2
**Deliverables:** closed versioned journal envelope; lock-bound single-authority transition; previous/intended authoritative-state recovery oracle; bounded domain-validated idempotent cleanup; conflict-without-mutation behavior.

- [ ] 3.1 **RED:** Add journal-envelope tests for protocol version, transaction identity, domain and payload version, canonical previous/intended fingerprints, bounded cleanup payload, deterministic bytes, unknown fields/version, malformed values, unsafe journal entry, and durable publication/removal.
- [ ] 3.2 **RED:** Add pre-commit interruption tests proving recovery removes only transaction intent when current authority matches the recorded previous fingerprint and performs no cleanup.
- [ ] 3.3 **RED:** Add post-commit interruption tests proving recovery runs bounded idempotent cleanup when current authority matches the recorded intended fingerprint and durably removes the journal only after cleanup completes.
- [ ] 3.4 **RED:** Add partial-cleanup tests proving recovery retries the complete bounded cleanup set and treats already absent domain-approved targets idempotently.
- [ ] 3.5 **RED:** Add conflict tests proving an authority matching neither previous nor intended preserves the journal, authority, and every cleanup target and fails without mutation.
- [ ] 3.6 **RED:** Add adversarial adapter tests proving malformed payloads, unchecked paths, noncanonical identities, cross-domain capabilities, and cleanup operations not validated by the domain cannot acquire deletion authority.
- [ ] 3.7 **GREEN:** Implement the closed versioned journal envelope and durable journal store required by task 3.1 without embedding a consumer schema.
- [ ] 3.8 **GREEN:** Implement the exclusive-lock-capability-bound transition coordinator and previous-state recovery branch required by task 3.2.
- [ ] 3.9 **GREEN:** Implement the intended-state roll-forward and idempotent deferred-cleanup branch required by tasks 3.3–3.4.
- [ ] 3.10 **GREEN:** Implement conflict-without-mutation and domain-adapter validation boundaries required by tasks 3.5–3.6.
- [ ] 3.11 **INTROSPECT:** Review whether protocol phase duplicates or contradicts filesystem truth, fingerprints bind canonical authoritative state, generic code can interpret paths or identities, cleanup can run before durable commit, and recovery can discard diagnostic evidence on conflict; simplify the state machine and resolve every finding.
- [ ] 3.12 **VALIDATE:** Run exhaustive fault injection at journal write/fsync, authority replace/fsync, each cleanup operation, and journal unlink/fsync; record that every state resolves to previous-complete, intended-complete with safely recoverable cleanup, intended-complete after cleanup, or conflict-without-mutation.

## Phase 4. Archived Build-Cache Migration and Legacy Recovery

**Depends on:** Phase 3; completed and archived `materialize-build-artifacts-on-host`
**Deliverables:** shared checkout fail-fast lock; shared manifest transition; build-domain legacy-journal migration adapter; corrected pre-manifest interruption recovery; preserved manifest, marker, TTL, snapshot, blob-validation, and cache-boundary behavior.

- [ ] 4.1 **RED:** Retain a reproducer for interruption after durable cleanup-intent publication but before committed-manifest replacement; require its fixture to preserve byte-for-byte the exact legacy `pending-build-cleanup.json` schema and canonical serialization produced by the archived implementation, and verify that implementation leaves the prior live set intact but blocks the next transaction.
- [ ] 4.2 **RED:** Add a legacy pre-commit migration test proving that, when the manifest references every journaled blob, recovery removes only the exact legacy journal, preserves every journaled blob and marker, and durably records journal removal.
- [ ] 4.3 **RED:** Add a legacy post-commit migration test proving that, when the manifest references none of the journaled blobs, recovery idempotently removes the validated journaled blobs and markers and durably removes the journal only after cleanup completes.
- [ ] 4.4 **RED:** Add malformed and ambiguous legacy-state tests covering invalid JSON/schema, unknown fields, duplicate or noncanonical digest identities, unsafe journal entry, and partial manifest overlap; verify recovery preserves the journal and every cleanup target and fails without mutation.
- [ ] 4.5 **RED:** Add build policy-parity tests for checkout-wide `FAIL_FAST` locking, competing-build rejection before cache/snapshot mutation, abandoned-snapshot ordering, committed-marker immunity, exact fixed TTL, manifest durability before deletion, shared-XDG non-interaction, and release after startup/commit/cleanup failure.
- [ ] 4.6 **GREEN:** Implement a narrowly scoped build-domain adapter that recognizes only the exact archived `pending-build-cleanup.json` format, validates every canonical digest identity, classifies all/every, none, and partial manifest overlap, and derives cleanup paths only through existing build-cache authority.
- [ ] 4.7 **GREEN:** Connect the build-domain legacy adapter to startup recovery so full overlap discards only pre-commit intent, no overlap rolls post-commit cleanup forward, and malformed or partial overlap fails without mutation; do not place legacy schema handling, digest interpretation, or path/deletion authority in the generic transaction package.
- [ ] 4.8 **GREEN:** Adapt build committed-manifest bytes/fingerprints and canonical digest cleanup to the shared single-authority transition and migrate checkout locking and durable control-file operations while preserving build-owned marker, TTL, snapshot, blob-validation, and XDG-separation logic.
- [ ] 4.9 **GREEN:** Remove the superseded local build lock, atomic JSON, no-follow control-read, cleanup-journal, and durable-unlink implementations only after tasks 4.1–4.8 prove existing on-disk legacy journals are handled compatibly by the build-domain adapter.
- [ ] 4.10 **INTROSPECT:** Review migrated build transitions for legacy/new journal ambiguity, cleanup before commit, manifest/journal TOCTOU, canonical digest bypass, stale-marker deletion of live blobs, lock-order inversion, hidden TTL configuration, and accidental authority over shared XDG state; resolve every finding without broadening generic infrastructure.
- [ ] 4.11 **VALIDATE:** Run build-cache transaction, materialization, and acceptance suites with real process interruption before manifest replacement, after replacement, during each cleanup step, and during journal removal, beginning from both exact legacy files and journals written by the new protocol; record corrected blocked recovery, prior-set preservation before commit, idempotent post-commit cleanup, durable journal removal, and ambiguous-state failure without mutation.

## Phase 5. Runtime-Artifact Lock Migration

**Depends on:** Phase 1, Phase 2
**Deliverables:** runtime-artifact identity locks migrated to the shared blocking lock; unchanged fast path, post-lock recheck, streaming verification, immutable publication, quarantine, cleanup diagnostics, and shared-XDG ownership.

- [ ] 5.1 **RED:** Add parity tests proving runtime-artifact lock scope is one digest identity, same-identity contenders block and recheck, different identities proceed concurrently, and a valid cache hit retains its pre-lock fast path.
- [ ] 5.2 **RED:** Add failure-parity tests for unsafe lock entries, transport failure, digest mismatch, publication/revalidation failure, cancellation, temporary cleanup failure, and release failure; verify primary diagnostics and cache ownership remain unchanged.
- [ ] 5.3 **GREEN:** Replace the runtime artifact cache's local identity lock with the shared `BLOCK` lock adapter while preserving namespace derivation and the fast-path/post-lock-recheck pipeline.
- [ ] 5.4 **GREEN:** Adopt Phase 1 durable helpers only for runtime publication operations whose replace, permission, and cleanup semantics match exactly; retain specialized quarantine and streaming behavior.
- [ ] 5.5 **GREEN:** Remove superseded runtime-artifact lock and matching durable helper code only after tasks 5.1–5.4 pass.
- [ ] 5.6 **INTROSPECT:** Review the migration for accidental checkout-wide serialization, changed lock waiting, weakened SRI/revalidation, build-cache retention leakage, cleanup-error masking, and forced reuse of semantically different helpers; resolve every finding.
- [ ] 5.7 **VALIDATE:** Run runtime materializer, launcher, cache-security, and corrupt-cache recovery suites; record same-identity serialization, different-identity concurrency, unchanged diagnostics, and strict non-interaction with build manifests, markers, and GC.

## Phase 6. npm-Environment Lock Migration

**Depends on:** Phase 1, Phase 2
**Deliverables:** npm publication and storage identity locks migrated to the shared blocking lock; unchanged immutable-tree publication, evidence, collision, quarantine, cancellation, and cleanup semantics.

- [ ] 6.1 **RED:** Add publication parity tests proving one input-identity namespace serializes lookup, assembly validation, and publication while different input identities remain concurrent.
- [ ] 6.2 **RED:** Add storage lock-entry tests covering safe preparation, symlink, non-regular, foreign-owned, hard-linked, wrong-mode, and bootstrap-race cases without target or ancestor mutation.
- [ ] 6.3 **RED:** Add lifecycle parity tests covering post-lock lookup, immutable output collision, corrupt-output quarantine, cancellation, workspace removal, lock release, and preservation of primary errors when cleanup also fails.
- [ ] 6.4 **GREEN:** Migrate `docker/npm_environment/storage.py` lock preparation and namespace derivation to the shared `BLOCK` lock adapter.
- [ ] 6.5 **GREEN:** Migrate `docker/npm_environment/publication.py` coordination and lock lifecycle to the shared capability while retaining npm-domain assembly evidence, tree sealing, output identity, collision, and quarantine logic.
- [ ] 6.6 **GREEN:** Adopt Phase 1 durable helpers only where npm output/index publication semantics match exactly, then remove superseded npm lock and matching durable implementations after tasks 6.1–6.5 pass.
- [ ] 6.7 **INTROSPECT:** Review the migration for cross-identity serialization, split lock namespaces between storage/publication, evidence or tree-authority leakage, changed blocking behavior, quarantine deletion authority, cancellation masking, and incompatible durable-helper reuse; resolve every finding.
- [ ] 6.8 **VALIDATE:** Run npm preflight, execution, publication, storage, evidence, validation, and smoke suites; record unchanged output/evidence identities, same-identity coordination, different-identity concurrency, and absence of newly introduced npm, Docker, or network effects.

## Phase 7. Remaining Durable-Helper Consolidation

**Depends on:** Phase 1
**Deliverables:** exact-match projection/rendering helpers consolidated; specialized no-clobber and destination semantics retained; complete inventory of intentional durable-I/O exceptions.

- [ ] 7.1 **RED:** Add parity tests for effective-projection and rendering writes covering destination-exists behavior, hard-link no-clobber publication, symlink rejection, modes, cleanup, and failure diagnostics before changing helper ownership.
- [ ] 7.2 **GREEN:** Migrate only projection/rendering operations whose atomic-replace and durability semantics exactly match Phase 1 primitives.
- [ ] 7.3 **GREEN:** Retain and clearly isolate hard-link no-clobber, tree, or destination-specific operations that cannot preserve their contract through the shared helpers; remove only proven exact duplicate implementations.
- [ ] 7.4 **INTROSPECT:** Search production Python for replace-plus-fsync, durable unlink, validated no-follow reads, and related temporary-file helpers; classify each as migrated or intentionally specialized and resolve every unexplained duplicate.
- [ ] 7.5 **VALIDATE:** Run effective projection, rendering, launcher, path-security, and failure-cleanup suites; record byte/mode/diagnostic parity and publish the complete intentional-exception inventory in the design or code documentation.

## Phase 8. Integration and Extension Boundary

**Depends on:** Phase 4, Phase 5, Phase 6, Phase 7
**Deliverables:** repository-wide migrated transaction substrate; tested extension seams for future multi-target and CAS adapters; no unexplained duplicate lock/durable implementations; complete regression and acceptance evidence.

- [ ] 8.1 **RED:** Add extension-contract test doubles proving a future multi-target publisher can add complete-old/complete-new recovery without representing the base single-authority transition as multi-file atomicity.
- [ ] 8.2 **RED:** Add extension-contract test doubles proving a future user-state adapter can add immediate fingerprint/CAS revalidation and reject third-state edits without giving generic code user-state reconciliation authority.
- [ ] 8.3 **GREEN:** Expose the minimal typed journal, transition, lock-capability, and durable-I/O extension interfaces required by tasks 8.1–8.2 without implementing sync-lock multi-target publication or settings reconciliation.
- [ ] 8.4 **GREEN:** Remove or document every remaining direct production `flock`, ad hoc lock preparation, and exact duplicate replace-plus-fsync helper; retain only explicit platform/domain adapters identified by prior phase validation.
- [ ] 8.5 **INTROSPECT:** Review the complete dependency direction for cycles, generic-to-domain imports, hidden path/deletion authority, widened lock scopes, changed contention policy, unsupported portability claims, compatibility gaps, and abstractions used by only one consumer without a security boundary benefit; resolve every finding.
- [ ] 8.6 **VALIDATE:** Run formatting, type checks, complete unit/integration/acceptance suites, strict OpenSpec validation, and `git diff --check`; record that public CLI behavior, cache paths, dry-run effects, retention, concurrency policies, on-disk legacy recovery, and consumer security boundaries remain compatible except for the intentional build recovery defect correction.
