# Binding Implementation Contract

Every checkbox and phase deliverable is required. Within each phase work SHALL proceed RED → GREEN → INTROSPECT → VALIDATE. Later phases may depend only on earlier phases listed below; changing an earlier delivered contract reopens its affected introspection and validation.

```text
Phase 1 ──> Phase 2 ──┬──> Phase 3 ──┐
                      └──> Phase 4 ──┼──> Phase 5 ──> Phase 6
                                     ┘
```

## 1. Locked Input and Identity Contract

**Depends on:** none.

**Deliverables:** closed lockfile-v3 DTO including validated executable declarations and `engines.node` metadata for every reviewed root, keyed by package identity and lock path; exact roots/closure/range validation; published Pi compatibility fixture with immutable provenance; supported optional omission model; assembler and assembler-input identities; assembled output identity is produced after output validation in Phase 5.

- [x] 1.1 RED — Add failing table-driven tests for valid lockfile-v3 roots, scoped packages, nested placement, present-SRI validation, accepted integrity-less exact HTTPS registry nodes with explicit omission records, safe `bin` maps and valid `engines.node` ranges for multiple reviewed roots preserved separately in the closed DTO by package identity/path, explicitly accepted-and-ignored `license`, `funding`, and `deprecated` across manifest/reviewed-root/transitive roles, shape-valid transitive `bin`, and syntax-valid manifest/transitive `engines.node` ranges including `||` accepted but absent from semantic DTOs; verify no side-effect-free preflight returns the complete digest-bound validated assembly input contract.
- [x] 1.2 RED — Add failing tests for root drift, unsatisfied ranges, missing nodes, unsafe paths/URLs, malformed SRI, missing SRI when exact version or valid HTTPS registry `resolved` is absent, file/git/link/workspace/bundled nodes, root `bin` values that are empty, absolute, contain `..`, empty components or backslashes, or are otherwise ambiguous or escaping, malformed/unknown root `engines` metadata, reviewed Node versions that fail any one of multiple reviewed-root `engines.node` ranges, with the incompatible root identity/path identified, malformed role-specific `bin`/`engines`/`license`/`funding`/`deprecated`, unsupported manifest/transitive engine keys or syntactically invalid ranges, acceptance of valid transitive ranges unsatisfied by the reviewed Node version without a Constructor compatibility diagnostic, and every unknown root or transitive field.
- [x] 1.3 RED — Add failing tests for platform-applicable and platform-omitted optional nodes with explicit omission evidence.
- [x] 1.4 RED — Replace legacy `EnvironmentIdentity`/`compute_environment_identity` tests with failing `AssemblerInputIdentity`/`compute_assembler_input_identity` API tests covering canonical reviewed roots, the exact lockfile-byte digest, and the assembler identity (image digest, Node/npm versions, script/policy digests, and platform); prove the type and API describe inputs only and contain no output-tree or evidence claims.
- [x] 1.5 GREEN — Implement the side-effect-free preflight and immutable digest-bound validated assembly input with canonical roots, platform, reviewed tool versions, closure, omissions, integrity-less registry-node records, and keyed root metadata; implement immutable lock/root/optional DTO parsing, preserve validated executable declarations and `engines.node` separately for every reviewed root by package identity/path, explicitly accept-and-ignore role-valid `license`, `funding`, and `deprecated`, transitive `bin`, and syntax-valid manifest/transitive `engines.node`, reject only reviewed-root engine incompatibility against the caller-supplied reviewed Node version before effects, keep npm `engine-strict` disabled, add no custom transitive-engine compatibility diagnostic, make no suppression or deduplication claim about native pinned-npm `EBADENGINE` output, and verify tasks 1.1–1.3 pass.
- [x] 1.6 GREEN — Rename the legacy environment-identity implementation/export to `AssemblerInputIdentity`/`compute_assembler_input_identity`, preserve its input-derived semantics, remove misleading environment-identity terminology, and verify task 1.4 passes.
- [x] 1.7 INTROSPECT — Enumerate manifest, reviewed-root, and transitive accepted fields separately; distinguish functional `bin` and `engines.node` for every reviewed root from accepted-and-ignored role-valid `license`/`funding`/`deprecated`, transitive `bin`, and syntax-valid manifest/transitive `engines.node`; prove ignored transitive values are absent from DTOs, evidence, and semantic identity inputs and cannot change dependency/placement validation, compatibility decisions, assembler behavior, npm flags, executable links, tree evidence, or assembled output; prove Constructor emits no custom compatibility diagnostic and does not claim to suppress or deduplicate native pinned-npm `EBADENGINE` output, while exact lock-byte changes remain represented only by the required lockfile digest; prove unsupported fields cannot influence output silently.
- [x] 1.8 INTROSPECT — Compare npm range/placement semantics used by validation with fixtures generated by the pinned npm version; add a byte-exact checked-in `tests/data/` copy of a pinned published Pi install lock without sanitization; read and assert its Pi version from its own root package metadata and record the exact immutable source URL corresponding to that embedded version plus SHA-256 provenance; derive `RootSpec` values from exact top-level locked-node versions rather than root-manifest ranges; verify the fixture actually exercises integrity-less exact HTTPS registry nodes with explicit omission records and accepted-and-ignored `funding` and `deprecated` plus transitive `bin`/`license`/`engines.node` and syntax-valid discarded manifest `engines.node`, including real `||` ranges, accepts syntax-valid transitive ranges without treating them as authoritative compatibility constraints; verify complete `linux-x64` closure acceptance, exact roots, only evidence-backed `platform-inapplicable` omissions, and deterministic repeated model/input-identity derivation; retain all synthetic negative/security fixtures and close every discrepancy without reading `/opt/pi`.
- [x] 1.9 VALIDATE — Run lock, range, URL, present/missing/malformed SRI, integrity-less registry evidence, path, root-executable, root-engine, published-Pi compatibility, optional and identity tests plus type checks and verify Phase 1 is green.

## 2. Secure Cache, Staging, and Tree Evidence

**Depends on:** Phase 1.

**Deliverables:** private assembler cache namespace; opaque npm cache; safe staging; canonical hashed tree manifest and digest primitives; complete no-follow filesystem/tree verification primitives. Assembled output identity, canonical assembler-evidence digest, publication, and authoritative cache-hit selection remain Phase 5 contracts.

- [x] 2.1 RED — Add failing path/permission tests for owner-private cache, identity locks, staging containment, foreign ownership, symlinks and unchanged ancestors.
- [x] 2.2 RED — Add failing canonical tree tests for files, directories, contained symlinks, ordering, hashes, special files, escapes and extras.
- [x] 2.3 RED — Add failing no-follow tree-verifier tests covering valid manifest/filesystem agreement and every file, directory, symlink, ordering, type, hash, permission, ownership, extra, missing, and escape corruption class without assuming a published output identity or assembler-evidence digest.
- [x] 2.4 GREEN — Implement assembler cache/staging preparation and opaque npm-cache namespacing required by task 2.1.
- [x] 2.5 GREEN — Implement deterministic tree-manifest generation, canonical tree digest, and verification primitives required by task 2.2.
- [x] 2.6 GREEN — Implement complete no-follow manifest/filesystem revalidation primitives required by task 2.3; do not select cache entries or derive/verify output identity or assembler-evidence digest in Phase 2.
- [x] 2.7 INTROSPECT — Audit all filesystem operations for traversal, TOCTOU, ambient umask, symlink following and accidental npm-cache authority.
- [x] 2.8 VALIDATE — Run cache security, tree evidence, corruption and permission tests under normal and `0700` parent paths.

## 3. Standalone Pinned Assembler Execution

**Depends on:** Phases 1 and 2.

**Deliverables:** deterministic Docker run vector; numeric host identity; fixed npm policy; narrow mounts; structured cancellation and redacted failures.

- [x] 3.1 RED — Add failing tests proving Docker-backed assembly accepts only a preflight-produced validated input, rejects changed lock bytes, roots, platform or reviewed tool versions before effects, and then renders a run vector with pinned image digest, numeric UID/GID, private HOME, read-only inputs, opaque cache, writable staging and no consumer mounts.
- [x] 3.2 RED — Add failing tests requiring pre-Docker satisfaction of every reviewed root's `engines.node` by the caller-supplied reviewed exact Node version, including multiple roots and one incompatible root with identity/path diagnostics while valid incompatible transitive ranges remain non-fatal, no custom compatibility diagnostic is added, and `engine-strict` remains disabled; require asserted actual Node/npm versions before npm execution, and exactly `npm ci --ignore-scripts --no-bin-links --no-audit --no-fund`, proving no reviewed root's `bin` metadata causes the assembler or npm to create executable links.
- [x] 3.3 RED — Add failing tests proving install scripts never run, nonzero npm exits remain structured, and stdout/stderr redact sensitive command inputs.
- [x] 3.4 RED — Add failing cancellation/interruption tests proving container cleanup and staging cleanup for every BaseException path.
- [x] 3.5 GREEN — Implement validated-input binding rechecks, the consumer-neutral assembler script and deterministic Docker execution boundary required by tasks 3.1–3.3 with enforcement of every reviewed root's engine constraint, no custom transitive-engine compatibility diagnostic, no guarantee about native npm warning count, no `engine-strict`, and no consumer launchers or executable links.
- [x] 3.6 GREEN — Implement cancellation, process/container cleanup and structured failure chaining required by task 3.4.
- [x] 3.7 INTROSPECT — Compare displayed and executable vectors, environment, mounts and script bytes; remove every ambient or consumer-specific input.
- [x] 3.8 GREEN — Create a repository-owned dedicated host smoke-test script that accepts only the reviewed immutable image reference and an explicit report-file path, uses production run-vector rendering with exact reviewed Node/npm versions, a valid lockfile fixture, and the fixed npm policy, and fails unless assembly exits `0` with the expected installed closure, no lifecycle-script effect, and no executable link. Have it write a canonical report recording the reviewed image digest, tool versions, script/policy and fixture digests, executed checks, result, and run timestamp or identifier; add tests for argument validation, failure propagation, and report serialization without requiring nested Docker.
- [x] 3.9 VALIDATE — Run execution, script-blocking, redaction, signal, and fake-Docker tests in the agent container; then invoke the task 3.8 smoke-test script on the Docker host and retain its successful report as validation evidence before marking this task complete.
- [x] 3.10 GREEN — Validate the Docker image reference before namespace/staging creation: accept only `sha256:<64 lowercase hex>`, `<registry>/<repository>@sha256:<64 lowercase hex>`, or `<registry>/<repository>:<tag>@sha256:<64 lowercase hex>`, treating the digest as authoritative and any tag as descriptive; reject tag-only references, malformed repositories, malformed/uppercase/non-hex digests, userinfo, and mutable references; prove invalid references fail before cache, staging, executor, or Docker activity.
- [x] 3.11 GREEN — Remove `peerDependencies` from the synthesized assembler manifest (root peers stay excluded by closure validation); copy only installed root-edge dependency classes and add a root-peer fixture proving npm cannot install or require an unvalidated package.
- [x] 3.12 GREEN — Stop swallowing cleanup failures: return structured container/staging cleanup failures and attach them to the primary assembly exception without replacing it, report the staging path and mutable-residue risk, and keep prior committed environments untouched.
- [x] 3.13 GREEN — Cover cleanup combinations: assembly failure with successful cleanup, plus container-cleanup failure, plus staging-cleanup failure, both failures, and KeyboardInterrupt during execution and cleanup, verifying the original failure stays identifiable and every cleanup failure is observable.

## 4. Corporate Network Boundary

**Depends on:** Phases 1 and 2.

**Deliverables:** assembler credential-free proxy/CA projection; fixed trust mount; non-persistence of local network configuration in evidence and diagnostics.

- [ ] 4.1 RED — Add failing tests for enabled/disabled credential-free corporate CA and proxy projection into assembler execution.
- [ ] 4.2 RED — Add failing tests proving assembler execution receives only the resolved credential-free proxy and CA policy.
- [ ] 4.3 RED — Add failing redaction tests over vectors, logs, exceptions, manifests, evidence and output trees for configured proxy endpoints and trust paths.
- [ ] 4.4 GREEN — Integrate resolved credential-free trust/proxy policy with assembler Docker execution and verify tasks 4.1–4.2 pass.
- [ ] 4.5 GREEN — Implement non-persistence and redaction of local network configuration and verify task 4.3 passes.
- [ ] 4.6 INTROSPECT — Trace every local network-policy input to the process boundary and prove it is absent from published outputs and evidence.
- [ ] 4.7 VALIDATE — Run corporate-network, disabled-policy, resolved-policy, and non-persistence acceptance tests.

## 5. Validation, Locking, and Atomic Publication

**Depends on:** Phases 2, 3, and 4.

**Deliverables:** exact post-install closure validator; canonical tree/evidence digests; assembled output identity serialization; non-authoritative input index; concurrent coordination; atomic immutable output-identity publication; consumer-neutral result DTO.

- [ ] 5.1 RED — Add failing output tests for exact paths/names/versions, dependency closure, omissions, extras, ownership, permissions, symlinks and special files.
- [ ] 5.2 RED — Add failing concurrency/storage/cache-hit tests proving identical inputs with different assembled bytes retain one input identity but receive distinct output identities, cannot overwrite or alias each other, may both be referenced by a non-authoritative input index, and undergo post-lock selection plus full recomputation of output identity, canonical tree digest, canonical assembler-evidence digest, and Phase 2 no-follow tree verification; cover corrupted and substituted tree/evidence candidates.
- [ ] 5.3 RED — Add failing publication tests for durability-before-rename, immutable modes, collision handling, interruption and prior-generation preservation.
- [ ] 5.4 RED — Add failing result/evidence serialization tests covering assembler input identity, assembled output identity, canonical tree/evidence digests, every input, package, integrity omission, flag and path without Pi/runtime fields; reject substituted tree/evidence pairs.
- [ ] 5.5 GREEN — Implement independent post-install validation and verify task 5.1 passes.
- [ ] 5.6 GREEN — Implement canonical assembler-evidence digest and assembled output identity derivation, input-identity coordination locking, non-authoritative lookup selection, complete output-identity cache-hit verification using Phase 2 primitives, atomic output-identity publication and failure cleanup, and verify tasks 5.2–5.3 pass.
- [ ] 5.7 GREEN — Implement immutable consumer-neutral result/evidence DTOs and verify task 5.4 passes.
- [ ] 5.8 INTROSPECT — Review the full state machine for races, partial publication, lock inversion, deletion of committed data and consumer leakage.
- [ ] 5.9 VALIDATE — Run output, concurrency, crash, publication, cache-hit and serialization tests together and verify deterministic evidence bytes, output identities, non-aliasing, and full cache-hit binding.

## 6. Integration and Repository Validation

**Depends on:** Phase 5.

**Deliverables:** two neutral synthetic consumers; shared-download proof; complete documentation; full green loop.

- [ ] 6.1 RED — Add failing acceptance tests where two independent locks share one tarball download but publish distinct trees and evidence.
- [ ] 6.2 RED — Add failing acceptance tests for cold/warm cache, corruption recovery, network outage with valid environment, and incomplete cache failure.
- [ ] 6.3 RED — Add failing documentation contracts for supported lock subset, fixed flags, trust model, evidence and consumer boundaries.
- [ ] 6.4 GREEN — Complete integration wiring needed for tasks 6.1–6.2 without adding Pi or extension-specific behavior.
- [ ] 6.5 GREEN — Document assembler contracts, cache recovery and dependent-consumer API and verify task 6.3 passes.
- [ ] 6.6 INTROSPECT — Map every new spec scenario to a focused or acceptance test and verify dependent changes can consume only the public result boundary.
- [ ] 6.7 VALIDATE — Run all focused assembler, cache, network, filesystem, concurrency and acceptance suites.
- [ ] 6.8 VALIDATE — Run project typecheck, lint, complete tests, build/contracts and configured green loop; require a fully passing report.
