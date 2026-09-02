# Implementation Contract

Every checkbox below is required for completion. A phase is complete only when all of its RED → GREEN → INTROSPECT → VALIDATE tasks pass and every listed deliverable exists. GREEN work SHALL be limited to satisfying that phase's RED tests and SHALL NOT implement behavior owned by a later phase. Newly discovered scope SHALL be added to this contract before implementation.

A phase MAY depend only on phases with lower numbers that appear in its `Depends on` line. Work in independent branches of the DAG MAY proceed in parallel, but the checkout-wide build lock SHALL serialize side-effecting build acceptance runs.

External prerequisite: change `add-locked-npm-environment-assembler` SHALL be completed before Phase 6 begins.

Phase dependency DAG:

```text
Phase 1 ──> Phase 2 ──> Phase 3 ──> Phase 4 ──┬──> Phase 5 ──┐
                                              └──> Phase 6 ──┴──> Phase 7
```

## 1. Digest Identity and Checkout Cache Boundary

**Depends on:** none

**Deliverables:** canonical algorithm/digest identity shared by hex SHA-256 and SRI callers; fixed checkout-local build-cache paths; host-owner-private cache/snapshot paths; explicit prohibition on ancestor permission repair; updated ignore rules.

- [x] 1.1 **RED:** Add focused digest-identity tests for SHA-256 hex/SRI equivalence, canonical cache paths, deduplication, malformed input, and unsupported algorithms; verify they fail against the runtime-only identity model.
- [x] 1.2 **RED:** Add focused path tests for fixed checkout-local persistent/generated roots, containment, symlink/type rejection, and prohibition of shared-XDG or configurable roots; verify failure occurs before cache mutation.
- [x] 1.3 **RED:** Add focused permission tests proving published verified blobs are exactly `0444`, ordinary host-owner/group/other mutation attempts fail, the invoking host owner can read cache/snapshot state beneath a `0700` checkout parent, a differing UID cannot traverse those host paths, and path preparation leaves checkout, parent, home, and unrelated cache modes unchanged.
- [x] 1.4 **GREEN:** Implement canonical digest identity and adapters required by task 1.1; verify existing runtime SRI cache contracts still pass.
- [x] 1.5 **GREEN:** Implement checkout-local path preparation, host-owner traversal validation, strict no-repair handling for inaccessible ancestors, and ignore entries required by tasks 1.2–1.3.
- [x] 1.6 **INTROSPECT:** Review the phase diff for duplicated digest parsing, path derivation outside the owning module, ambient umask dependence, and accidental exposure of mutable control state; remove each issue found without adding later-phase behavior.
- [x] 1.7 **VALIDATE:** Run digest, cache-path, permission, runtime-cache security, and ignore-boundary tests; record host-owner success beneath a `0700` parent, differing-UID host denial, and unchanged ancestor modes.

## 2. Serialized Transaction and Retention State

**Depends on:** Phase 1

**Deliverables:** checkout-wide nonblocking build lock; abandoned-transaction detection; atomic committed-build manifest; atomic uncommitted markers; fixed 2,592,000-second GC policy; commit-before-delete ordering.

- [x] 2.1 **RED:** Add lock tests for single ownership, competing-build rejection before mutation, owner interruption, and release on all normal outcomes; verify no second transaction enters the critical section.
- [x] 2.2 **RED:** Add abandoned-snapshot tests proving only snapshots without the live checkout lock are removed and their verified blobs remain uncommitted.
- [x] 2.3 **RED:** Add manifest tests for atomic replacement, durability-before-GC, failed-build preservation, immediate removal of every superseded committed build blob, and strict non-interaction with the shared XDG runtime-artifact cache.
- [x] 2.4 **RED:** Add marker/GC tests for `verified_at`, exact 2,592,000-second expiry boundary, committed-blob immunity, immediate corrupt/partial cleanup, and immediate post-commit removal of superseded unreferenced blobs.
- [x] 2.5 **GREEN:** Implement the checkout-wide lock and abandoned-snapshot recovery required by tasks 2.1–2.2.
- [x] 2.6 **GREEN:** Implement atomic committed manifests, uncommitted markers, fixed-policy GC, and commit-before-delete sequencing required by tasks 2.3–2.4.
- [x] 2.7 **INTROSPECT:** Review transaction state transitions for TOCTOU windows, lock-order inversion, clock misuse, deletion before durable commit, and hidden configurability of the fixed TTL; simplify to one explicit state machine.
- [x] 2.8 **VALIDATE:** Run deterministic lock, crash-recovery, manifest, retention, and fake-clock tests; record that failed/interrupted transactions preserve the prior committed live set.

## 3. Host Materialization and Corporate Network Policy

**Depends on:** Phase 2

**Deliverables:** exact `linux-amd64` selection for rustup, uv, rtk, and fd; streaming SHA-256 host materialization; verified hit reuse; atomic miss publication; host proxy/CA application and redacted diagnostics.

- [x] 3.1 **RED:** Add selection tests requiring exactly the effective `linux-amd64` rustup, uv, rtk, and fd URL/digest pairs and explicit rejection of unsupported platforms.
- [x] 3.2 **RED:** Add materializer tests for a verified cache hit, streamed cache miss, digest mismatch, transport interruption, atomic publication, and immediate temporary-file cleanup.
- [x] 3.3 **RED:** Add orchestration tests proving materialization or integrity failure prevents Docker invocation and leaves no committed reference.
- [x] 3.4 **RED:** Add corporate-network tests for enabled credential-free proxy, enabled replacement CA, disabled-policy neutrality, invalid-policy early failure, and secret/URL redaction.
- [x] 3.5 **GREEN:** Implement effective build-artifact selection and streaming materialization required by tasks 3.1–3.3.
- [x] 3.6 **GREEN:** Inject resolved host corporate network policy into the materialization transport as required by task 3.4.
- [x] 3.7 **INTROSPECT:** Review the phase diff for full-buffer downloads, duplicate HTTP policy, unredacted diagnostics, network after integrity failure, and coupling to CLI/rendering modules; remove each issue found.
- [x] 3.8 **VALIDATE:** Run provider-independent transport, materialization, orchestration, corporate-network, and failure-cleanup tests; record that Docker is never invoked on a materialization failure.

## 4. Immutable Named Build Context and Minimal Dockerfile Conversion

**Depends on:** Phase 3

**Deliverables:** selected-prebuilt-artifact-only owner-private transaction snapshot with canonical manifest and stable filenames; hard-link/copy fallback; host-owner named-context import; in-build read-only copies for remapped `dev`; fail-fast BuildKit/path checks; rustup, uv, rtk, and fd stages minimally converted to consume named-context files with retained SHA-256 verification and no artifact URL arguments or corresponding in-Docker downloads; Rustup's already reviewed `4acc9acc…` bytes sourced from the immutable official `archive/1.29.0/` URL and matching archived checksum URL instead of mutable `dist/` aliases.

- [x] 4.1 **RED:** Add snapshot-content tests for deterministic manifest bytes, stable logical filenames, selected-prebuilt-artifact-only exposure, hard-link creation, copy fallback, and post-copy digest verification.
- [x] 4.2 **RED:** Add snapshot-lifecycle tests for owner-private mutable population followed by `0444` selected-prebuilt-artifact finalization and removal of every directory write bit; failed ordinary host-owner mutation and permission assertions; host-owner import beneath a `0700` parent; no host traversal for differing UID; readable non-writable in-build copies for remapped `dev`; cache-name unlink survival; and unconditional cleanup.
- [x] 4.3 **RED:** Add BuildKit prerequisite tests proving missing named-context support fails before download, snapshot publication, or Docker execution.
- [x] 4.4 **RED:** Add typed-plan tests requiring Phase 4 real builds to hold `Materialized(platform-native-path, NoDerivedEnvironment)`, dry-runs to hold `{name: constructor-artifacts, state: prospective, path: null, attestation: {state: prospective}}`, and executable rendering to reject every unresolved prospective context or invalid closed attestation before producing argv.
- [x] 4.5 **RED:** Add presentation tests requiring dry-run text `--build-context constructor-artifacts=<prospective:not-materialized>` beneath `Planned build (not executable)`, byte-identical POSIX/Windows output, retained digest inputs, absent artifact URL inputs, and zero filesystem/cache/network/Docker side effects.
- [x] 4.6 **RED:** Add Dockerfile contract tests requiring rustup and uv to use stable named-context files, retain in-stage SHA-256 checks, and contain no corresponding curl or URL input; add a focused inventory contract proving Rustup's reviewed SHA-256 `4acc9acc76d5079515b46346a485974457b5a79893cfb01112423c89aeb5aa10` is paired with the immutable official `archive/1.29.0/` artifact and checksum URLs rather than mutable `dist/` aliases.
- [x] 4.7 **RED:** Add Dockerfile contract tests requiring independent rtk and fd stages to use stable named-context files, retain in-stage SHA-256 checks, and contain no corresponding network download.
- [x] 4.8 **GREEN:** Implement selected-prebuilt-artifact snapshot creation, verification, `0444` finalization, host-client import boundary, explicit in-build copy permissions, and cleanup required by tasks 4.1–4.2.
- [x] 4.9 **GREEN:** Implement the named-context prerequisite check, closed `Materialized`/`Prospective` context model, real executable rendering, cross-platform dry-run serialization/presentation, and unresolved-plan rejection required by tasks 4.3–4.5.
- [x] 4.10 **GREEN:** Minimally convert the rustup, uv, rtk, and fd stages to named-context inputs, removing their URL inputs and corresponding downloads while retaining independent stages and in-stage SHA-256 verification; correct Rustup's reviewed inventory provenance from mutable `dist/` aliases to the immutable official `archive/1.29.0/` artifact and checksum URLs without changing the selected bytes or digest, as required by tasks 4.6–4.7.
- [x] 4.11 **INTROSPECT:** Review the phase diff for exposure of the whole cache, mutable snapshots, unstable manifest ordering, primary-context leakage, permission changes through hard links, OS-specific prospective paths, command/display divergence, retained artifact URLs, or unnecessary artifact network access; correct each issue found without taking on Phase 5 cache-boundary tuning.
- [x] 4.12 **VALIDATE:** Run snapshot, private-ancestor, host-owner import, remapped in-build UID, typed-plan, build-vector, capability-failure, command-display, and Dockerfile contract tests; record byte-identical POSIX/Windows dry-runs with `path: null`, no lock/filesystem/cache/network/Docker interaction, no executable argv for prospective plans, platform-native paths only for materialized plans, and named-context Dockerfile consumption with retained digest checks and absent artifact URL inputs.

## 5. Dockerfile Independent Invalidation and Build Acceptance

**Depends on:** Phase 4

**Deliverables:** preserved independent BuildKit invalidation for the converted rustup, uv, rtk, and fd stages; focused valid/tampered-snapshot and cache-boundary build evidence.

- [ ] 5.1 **RED:** Add focused BuildKit cache tests proving a changed rtk input does not invalidate fd, rustup, uv, Pi, or OpenSpec stages and a changed fd input has the symmetric boundary.
- [ ] 5.2 **GREEN:** Adjust stage/context structure only as required to satisfy the independent invalidation tests in task 5.1.
- [ ] 5.3 **INTROSPECT:** Review Dockerfile stages for duplicated verification, accidental payload persistence in the final image, cross-stage invalidation, and unnecessary coupling introduced by the minimal Phase 4 conversion; remove each issue found.
- [ ] 5.4 **VALIDATE:** Run focused `linux-amd64` builds with valid and tampered snapshots plus plain-progress cache-boundary rebuilds; record successful installs, integrity rejection, and expected cached stages.

## 6. Official Locked Pi Installation

**Depends on:** Phase 4

**Deliverables:** reviewed Pi release repository and tag-prefix schema; exact GitHub assets and SHA256SUMS verification; adoption of the completed `add-locked-npm-environment-assembler` prerequisite; standalone host Pi assembly and evidence; consumer evidence for the safe explicit `/opt/pi/bin/pi` launcher’s exact contents, non-writable executable mode, target, and containment; post-materialization `DerivedEnvironment(assembledOutputIdentity, canonicalTreeDigest, assemblerEvidenceDigest, consumerLauncherEvidenceDigest)` transaction/build-plan attestation, alongside the Phase 4 `NoDerivedEnvironment` and dry-run `prospective` closed variants; validated Pi tree/evidence/launcher admission to the named context with evidence-preserved executable bits and no-follow-contained symlinks; BuildKit-boundary verification against those attestation values with no BuildKit npm/network; preserved command and SDK interfaces.

- [ ] 6.1 **RED:** Add inventory tests requiring exact `[build.stages.base.node].node_version` and `.npm_version` alongside the reviewed image tag/digest, plus Pi npm package `@earendil-works/pi-coding-agent`, `release_repository = "earendil-works/pi"`, and `release_tag_prefix = "v"`; verify closed-schema rejection of missing, malformed, or unknown metadata and that tool versions are never inferred from the image tag. Bootstrap the reviewed values once by inspecting the current digest-pinned image and prove the inspected digest matches inventory.
- [ ] 6.2 **RED:** Add URL-contract tests deriving the exact `https://github.com/earendil-works/pi/releases/download/v<version>/` base and exact `SHA256SUMS`, `pi-coding-agent-install-package.json`, and `pi-coding-agent-install-package-lock.json` asset URLs without npm inference or alternate naming.
- [ ] 6.3 **RED:** Add release-content tests for strict SHA256SUMS parsing, both required checksum entries, redirects, missing assets, mismatches, and transport failures.
- [ ] 6.4 **RED:** Add tests for the explicit side-effect-free assembler preflight returning a digest-bound validated input with every reviewed root's `bin` and `engines.node` keyed by package identity/path; prove every root engine is checked against reviewed `node_version` with multi-root coverage, one incompatible root is identified, and malformed or incompatible input produces no Docker, npm, network, cache, staging, lock, publication, output path, or output evidence; syntax-valid transitive engine ranges are discarded and accepted even when unsatisfied, `engine-strict` is never enabled, and Pi adds no custom transitive-engine diagnostic or guarantee about native pinned-npm warning count. Add selection and snapshot-admission tests proving Pi binary release archives are never chosen; the two checksum-verified installation files are acquired under their exact names as host-only assembler inputs and are absent from the BuildKit context; only the validated assembled Pi tree, assembler evidence, and consumer launcher evidence enter that context; `bin.pi` is consumed only from the keyed DTO entry for the exact selected `@earendil-works/pi-coding-agent` root identity/resolved path, never from another reviewed root and never reparsed from raw package input; the consumer-created launcher’s safe relative target, exact contents, non-writable executable mode, and containment through complete symlink resolution are verified before admission; dangling or escaping targets are rejected; and the assembled output identity, canonical tree digest, canonical assembler-evidence digest, and deterministic consumer-launcher-evidence digest bind only to a post-materialization `DerivedEnvironment` transaction/build-plan attestation, while Phase 4 uses `NoDerivedEnvironment` and dry-run uses `prospective` without side effects.
- [ ] 6.5 **RED:** Add orchestration tests requiring side-effect-free preflight before Docker-backed shared assembly; prove assembly receives the exact preflight-produced validated input and lock bytes, rejects changed digest, roots, platform or tool versions before effects, and only then uses host evidence and the shared opaque cache; prove assembler execution uses `--no-bin-links` and creates no launcher, BuildKit-boundary matching of assembled output identity, canonical tree digest, assembler-evidence digest, and consumer launcher-evidence digest to post-materialization attestation values before evidence verification and copy, rejection of substituted launcher/evidence pairs, no Dockerfile npm/network, present-SRI mismatch propagation, acceptance and evidence of integrity-less exact HTTPS registry nodes, and rejection of missing integrity when exact version or valid registry URL is absent.
- [ ] 6.6 **RED:** Add final-layout tests for safe `bin.pi` derivation from the validated assembler DTO entry keyed to the selected Pi root rather than any other reviewed root; consumer-evidenced launcher contents, mode, target, and containment; post-materialization `DerivedEnvironment` attestation of expected assembled output identity, canonical tree digest, assembler-evidence digest, and launcher-evidence digest, distinct from Phase 4 `NoDerivedEnvironment` and side-effect-free `prospective` dry-run states; preservation of assembler-evidenced executable bits including an executable `/opt/pi/bin/pi`; contained symlink import; verification of launcher evidence before BuildKit copy and again in the final image; rejection of dangling, escaping, output-identity-mismatched, tree-digest-mismatched, assembler-evidence-mismatched, consumer-launcher-evidence-mismatched, or substituted tree/launcher/evidence entries; selected package version, SDK/module resolution, immutable ownership, help/update behavior, extension compatibility, and runtime verification.
- [ ] 6.7 **GREEN:** Implement reviewed shared Node/npm version loading, invocation of the explicit side-effect-free assembler preflight, reviewed-root engine enforcement, ignored transitive-engine handling without `engine-strict`, keyed Pi-root metadata selection, Pi release-source loading, and exact URL derivation required by tasks 6.1–6.2 and 6.4.
- [ ] 6.8 **GREEN:** Implement host-only acquisition and checksum verification of exact-name release-source assembler inputs, without BuildKit snapshot exposure, as required by tasks 6.3–6.4.
- [ ] 6.9 **GREEN:** Pass the exact preflight-produced digest-bound input and lock bytes to shared Docker-backed assembly with binding rechecks and no executable-link creation, validate/publish the Pi tree, consume safe `bin.pi` only from the preflight DTO entry keyed to the selected Pi root identity/path, have the consumer derive `/opt/pi/bin/pi` while rejecting dangling or escaping resolved targets, generate consumer evidence for its exact contents, non-writable executable mode, target, and containment, bind the expected assembled output identity, canonical tree digest, canonical assembler-evidence digest, and deterministic consumer-launcher-evidence digest to a post-materialization `DerivedEnvironment` transaction/build-plan attestation, retain the Phase 4 `NoDerivedEnvironment` and side-effect-free `prospective` dry-run variants before Pi materialization, admit the tree and both evidence sets to the immutable snapshot with preserved executable bits and no-follow-contained symlinks, match all four attested values and both evidence sets to those BuildKit inputs before verification and copy, verify the installed launcher again in the final image, and replace Dockerfile installation with named-context copy as required by tasks 6.5–6.6.
- [ ] 6.10 **INTROSPECT:** Review for implicit asset inference, binary archives, mutable resolution, lifecycle scripts, lock bypass, BuildKit npm/network, consumer duplication of assembler logic, cache authority, and changed Pi paths; remove each issue found.
- [ ] 6.11 **VALIDATE:** Run inventory, exact-URL, Pi metadata, cold/warm shared-cache, assembled-output/tree/assembler-evidence/consumer-evidence failure, materialized-attestation binding and substituted tree/evidence-pair rejection, prospective dry-run representation, side-effect-free projection resolution, launcher containment, no-build-network, command, SDK, extension, ownership, and runtime verification tests; record identical external Pi interfaces.

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
