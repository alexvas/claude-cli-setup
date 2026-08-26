# Implementation Contract

Every checkbox below is required for completion. A phase is complete only when all of its RED → GREEN → INTROSPECT → VALIDATE tasks pass and every listed deliverable exists. GREEN work SHALL be limited to satisfying that phase's RED tests and SHALL NOT implement behavior owned by a later phase. Newly discovered scope SHALL be added to this contract before implementation.

A phase MAY depend only on phases with lower numbers that appear in its `Depends on` line. Work in independent branches of the DAG MAY proceed in parallel, but the checkout-wide build lock SHALL serialize side-effecting build acceptance runs.

Phase dependency DAG:

```text
Phase 1 ──> Phase 2 ──> Phase 3 ──> Phase 4 ──┬──> Phase 5 ──┐
                                              └──> Phase 6 ──┴──> Phase 7
```

## 1. Digest Identity and Checkout Cache Boundary

**Depends on:** none

**Deliverables:** canonical algorithm/digest identity shared by hex SHA-256 and SRI callers; fixed checkout-local build-cache paths; host-owner-private cache/snapshot paths; explicit prohibition on ancestor permission repair; updated ignore rules.

- [ ] 1.1 **RED:** Add focused digest-identity tests for SHA-256 hex/SRI equivalence, canonical cache paths, deduplication, malformed input, and unsupported algorithms; verify they fail against the runtime-only identity model.
- [ ] 1.2 **RED:** Add focused path tests for fixed checkout-local persistent/generated roots, containment, symlink/type rejection, and prohibition of shared-XDG or configurable roots; verify failure occurs before cache mutation.
- [ ] 1.3 **RED:** Add focused permission tests proving published verified blobs are exactly `0444`, ordinary host-owner/group/other mutation attempts fail, the invoking host owner can read cache/snapshot state beneath a `0700` checkout parent, a differing UID cannot traverse those host paths, and path preparation leaves checkout, parent, home, and unrelated cache modes unchanged.
- [ ] 1.4 **GREEN:** Implement canonical digest identity and adapters required by task 1.1; verify existing runtime SRI cache contracts still pass.
- [ ] 1.5 **GREEN:** Implement checkout-local path preparation, host-owner traversal validation, strict no-repair handling for inaccessible ancestors, and ignore entries required by tasks 1.2–1.3.
- [ ] 1.6 **INTROSPECT:** Review the phase diff for duplicated digest parsing, path derivation outside the owning module, ambient umask dependence, and accidental exposure of mutable control state; remove each issue found without adding later-phase behavior.
- [ ] 1.7 **VALIDATE:** Run digest, cache-path, permission, runtime-cache security, and ignore-boundary tests; record host-owner success beneath a `0700` parent, differing-UID host denial, and unchanged ancestor modes.

## 2. Serialized Transaction and Retention State

**Depends on:** Phase 1

**Deliverables:** checkout-wide nonblocking build lock; abandoned-transaction detection; atomic committed-build manifest; atomic uncommitted markers; fixed 2,592,000-second GC policy; commit-before-delete ordering.

- [ ] 2.1 **RED:** Add lock tests for single ownership, competing-build rejection before mutation, owner interruption, and release on all normal outcomes; verify no second transaction enters the critical section.
- [ ] 2.2 **RED:** Add abandoned-snapshot tests proving only snapshots without the live checkout lock are removed and their verified blobs remain uncommitted.
- [ ] 2.3 **RED:** Add manifest tests for atomic replacement, durability-before-GC, failed-build preservation, immediate removal of every superseded committed build blob, and strict non-interaction with the shared XDG runtime-artifact cache.
- [ ] 2.4 **RED:** Add marker/GC tests for `verified_at`, exact 2,592,000-second expiry boundary, committed-blob immunity, immediate corrupt/partial cleanup, and immediate post-commit removal of superseded unreferenced blobs.
- [ ] 2.5 **GREEN:** Implement the checkout-wide lock and abandoned-snapshot recovery required by tasks 2.1–2.2.
- [ ] 2.6 **GREEN:** Implement atomic committed manifests, uncommitted markers, fixed-policy GC, and commit-before-delete sequencing required by tasks 2.3–2.4.
- [ ] 2.7 **INTROSPECT:** Review transaction state transitions for TOCTOU windows, lock-order inversion, clock misuse, deletion before durable commit, and hidden configurability of the fixed TTL; simplify to one explicit state machine.
- [ ] 2.8 **VALIDATE:** Run deterministic lock, crash-recovery, manifest, retention, and fake-clock tests; record that failed/interrupted transactions preserve the prior committed live set.

## 3. Host Materialization and Corporate Network Policy

**Depends on:** Phase 2

**Deliverables:** exact `linux-amd64` selection for rustup, uv, rtk, and fd; streaming SHA-256 host materialization; verified hit reuse; atomic miss publication; host proxy/CA application and redacted diagnostics.

- [ ] 3.1 **RED:** Add selection tests requiring exactly the effective `linux-amd64` rustup, uv, rtk, and fd URL/digest pairs and explicit rejection of unsupported platforms.
- [ ] 3.2 **RED:** Add materializer tests for a verified cache hit, streamed cache miss, digest mismatch, transport interruption, atomic publication, and immediate temporary-file cleanup.
- [ ] 3.3 **RED:** Add orchestration tests proving materialization or integrity failure prevents Docker invocation and leaves no committed reference.
- [ ] 3.4 **RED:** Add corporate-network tests for enabled credential-free proxy, enabled replacement CA, disabled-policy neutrality, invalid-policy early failure, and secret/URL redaction.
- [ ] 3.5 **GREEN:** Implement effective build-artifact selection and streaming materialization required by tasks 3.1–3.3.
- [ ] 3.6 **GREEN:** Inject resolved host corporate network policy into the materialization transport as required by task 3.4.
- [ ] 3.7 **INTROSPECT:** Review the phase diff for full-buffer downloads, duplicate HTTP policy, unredacted diagnostics, network after integrity failure, and coupling to CLI/rendering modules; remove each issue found.
- [ ] 3.8 **VALIDATE:** Run provider-independent transport, materialization, orchestration, corporate-network, and failure-cleanup tests; record that Docker is never invoked on a materialization failure.

## 4. Immutable Named Build Context

**Depends on:** Phase 3

**Deliverables:** selected-only owner-private transaction snapshot with canonical manifest and stable filenames; hard-link/copy fallback; host-owner named-context import; in-build read-only copies for remapped `dev`; fail-fast BuildKit/path checks; removed artifact URL arguments.

- [ ] 4.1 **RED:** Add snapshot-content tests for deterministic manifest bytes, stable logical filenames, selected-only exposure, hard-link creation, copy fallback, and post-copy digest verification.
- [ ] 4.2 **RED:** Add snapshot-lifecycle tests for owner-private mutable population followed by `0444` file finalization and removal of every directory write bit, failed ordinary host-owner mutation and permission assertions, host-owner import beneath a `0700` parent, no host traversal for differing UID, readable non-writable in-build copies for remapped `dev`, cache-name unlink survival, and unconditional cleanup.
- [ ] 4.3 **RED:** Add BuildKit prerequisite tests proving missing named-context support fails before download, snapshot publication, or Docker execution.
- [ ] 4.4 **RED:** Add typed-plan tests requiring real builds to hold `Materialized(platform-native-path)`, dry-runs to hold `{name: constructor-artifacts, state: prospective, path: null}`, and executable rendering to reject every unresolved prospective context before producing argv.
- [ ] 4.5 **RED:** Add presentation tests requiring dry-run text `--build-context constructor-artifacts=<prospective:not-materialized>` beneath `Planned build (not executable)`, byte-identical POSIX/Windows output, retained digest inputs, absent artifact URL inputs, and zero filesystem/cache/network/Docker side effects.
- [ ] 4.6 **GREEN:** Implement owner-private snapshot creation, verification, all-write-bit removal at finalization, host-client import boundary, explicit in-build copy permissions, and cleanup required by tasks 4.1–4.2.
- [ ] 4.7 **GREEN:** Implement the named-context prerequisite check, closed `Materialized`/`Prospective` context model, real executable rendering, cross-platform dry-run serialization/presentation, and unresolved-plan rejection required by tasks 4.3–4.5.
- [ ] 4.8 **INTROSPECT:** Review the phase diff for exposure of the whole cache, mutable snapshots, unstable manifest ordering, primary-context leakage, permission changes through hard links, OS-specific prospective paths, and command/display divergence; correct each issue found.
- [ ] 4.9 **VALIDATE:** Run snapshot, private-ancestor, host-owner import, remapped in-build UID, typed-plan, build-vector, capability-failure, and command-display tests; record byte-identical POSIX/Windows dry-runs with `path: null`, no lock/filesystem/cache/network/Docker interaction, no executable argv for prospective plans, and platform-native paths only for materialized plans.

## 5. Dockerfile Pinned-Artifact Conversion

**Depends on:** Phase 4

**Deliverables:** rustup, uv, rtk, and fd stages consuming named-context files; no corresponding in-Docker network downloads; second SHA-256 verification boundary; preserved independent BuildKit invalidation.

- [ ] 5.1 **RED:** Add Dockerfile contract tests requiring rustup and uv to use stable named-context files, retain in-stage SHA-256 checks, and contain no corresponding curl or URL input.
- [ ] 5.2 **RED:** Add Dockerfile contract tests requiring independent rtk and fd stages to use stable named-context files, retain in-stage SHA-256 checks, and contain no corresponding network download.
- [ ] 5.3 **RED:** Add focused BuildKit cache tests proving a changed rtk input does not invalidate fd, rustup, uv, Pi, or OpenSpec stages and a changed fd input has the symmetric boundary.
- [ ] 5.4 **GREEN:** Convert rustup and uv stages to named-context inputs and satisfy task 5.1 without changing unrelated stages.
- [ ] 5.5 **GREEN:** Convert rtk and fd stages to named-context inputs and satisfy task 5.2 without changing unrelated stages.
- [ ] 5.6 **GREEN:** Adjust stage/context structure only as required to satisfy the independent invalidation tests in task 5.3.
- [ ] 5.7 **INTROSPECT:** Review Dockerfile stages for retained artifact URLs, duplicated verification, accidental payload persistence in the final image, cross-stage invalidation, and unnecessary network access; remove each issue found.
- [ ] 5.8 **VALIDATE:** Run focused `linux-amd64` builds with valid and tampered snapshots plus plain-progress cache-boundary rebuilds; record successful installs, integrity rejection, and expected cached stages.

## 6. Official Locked Pi Installation

**Depends on:** Phase 4

**Deliverables:** reviewed Pi release repository and tag-prefix schema; exact deterministic GitHub release URL contract; strict SHA256SUMS verification; named-context delivery; `npm ci --ignore-scripts`; Pi-specific BuildKit npm cache; preserved `/opt/pi` command and SDK interfaces.

- [ ] 6.1 **RED:** Add inventory tests requiring Pi npm package `@earendil-works/pi-coding-agent`, `release_repository = "earendil-works/pi"`, and `release_tag_prefix = "v"`, with closed-schema rejection of missing, malformed, or unknown source metadata.
- [ ] 6.2 **RED:** Add URL-contract tests deriving the exact `https://github.com/earendil-works/pi/releases/download/v<version>/` base and exact `SHA256SUMS`, `pi-coding-agent-install-package.json`, and `pi-coding-agent-install-package-lock.json` asset URLs without npm inference or alternate naming.
- [ ] 6.3 **RED:** Add release-content tests for strict SHA256SUMS parsing, both required checksum entries, redirects, missing assets, mismatches, and transport failures.
- [ ] 6.4 **RED:** Add selection tests proving Pi binary release archives are never chosen and only the two checksum-verified installation files enter the build snapshot under their exact names.
- [ ] 6.5 **RED:** Add Pi stage tests requiring `npm ci --ignore-scripts`, the Pi-specific BuildKit npm cache mount, no global version-only install, and lockfile integrity failure propagation.
- [ ] 6.6 **RED:** Add final-layout tests for `/opt/pi/bin/pi`, selected package version, SDK/module resolution, ownership, help/update behavior, extension compatibility, and runtime verification.
- [ ] 6.7 **GREEN:** Implement reviewed Pi release-source loading and exact URL derivation required by tasks 6.1–6.2.
- [ ] 6.8 **GREEN:** Implement host acquisition, checksum verification, and exact-name snapshot exposure required by tasks 6.3–6.4.
- [ ] 6.9 **GREEN:** Replace global Pi installation with lockfile-frozen `npm ci` and explicit `/opt/pi` assembly required by tasks 6.5–6.6.
- [ ] 6.10 **INTROSPECT:** Review the phase diff for implicit repository/asset inference, binary-archive use, mutable dependency resolution, lifecycle-script execution, lockfile bypass, npm cache correctness dependence, and changes to established Pi paths; remove each issue found.
- [ ] 6.11 **VALIDATE:** Run inventory, exact-URL, Pi metadata, empty/warm npm-cache, integrity-failure, command, SDK, extension, ownership, and runtime verification tests; record identical external Pi interfaces with the locked graph.

## 7. Commit Integration and End-to-End Lifecycle

**Depends on:** Phase 5, Phase 6

**Deliverables:** complete build transaction from lock through materialization, snapshots, Docker execution, atomic commit, GC, and cleanup; self-contained existing images; acceptance evidence for cache hits, failures, retries, replacement, and unsupported scope.

- [ ] 7.1 **RED:** Add orchestration acceptance tests proving successful Docker completion commits the selected checkout-local build set and only then removes every superseded build blob without reading or mutating shared XDG runtime artifacts.
- [ ] 7.2 **RED:** Add failure acceptance tests for Docker nonzero exit, cancellation, signal interruption, snapshot failure, commit failure, and cleanup failure, each preserving the prior committed set and reusable verified uncommitted blobs.
- [ ] 7.3 **RED:** Add lifecycle acceptance tests proving an unchanged rebuild performs zero host artifact downloads, a changed artifact downloads once, a failed-build download is reused within 30 days, and an expired uncommitted blob is reacquired.
- [ ] 7.4 **RED:** Add image-independence tests proving existing images and containers remain operational after source-blob deletion without image labels or historical generation manifests.
- [ ] 7.5 **GREEN:** Connect successful build completion to atomic live-set commit, post-commit GC, and transaction cleanup required by tasks 7.1–7.2.
- [ ] 7.6 **GREEN:** Complete cache-hit, retry, expiry, and image-independence orchestration required by tasks 7.3–7.4 without adding historical retention.
- [ ] 7.7 **INTROSPECT:** Review the full change for phase-boundary violations, duplicate state ownership, hidden rollback retention, platform-generalization beyond `linux-amd64`, image-label generation tracking, and cleanup that can invalidate a successful image; resolve all findings.
- [ ] 7.8 **VALIDATE:** Run the complete inventory, digest, cache-security, transaction, materialization, corporate-network, snapshot, build-vector, Dockerfile, Pi, runtime, and acceptance suites; record a passing `linux-amd64` build and explicit rejection of unsupported platforms.
