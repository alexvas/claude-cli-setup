# Implementation Contract

Implementation is blocked until `decouple-constructor-project-root` is implemented, synchronized to main specs, and archived. Every phase follows RED → GREEN → INTROSPECT → VALIDATE; GREEN work SHALL remain limited to its RED contract and preserve all earlier phase invariants.

Phase dependency DAG:

```text
Dependency Gate → Parent Chain → Inventory Merge → Asset Manifest → Context Lifecycle
                                                        └──────────────┬──────────────┘
                                                                       v
Asset Migration → Consumer Integration → Documentation and Closure
```

## 1. Dependency and Semantic Baseline

- [ ] 1.1 **GATE:** Confirm `decouple-constructor-project-root` is implemented, its delta specs are synchronized, and the change is archived; do not continue while it remains active or incomplete.
- [ ] 1.2 Reconcile this change's modified delta requirements against the archived predecessor's main specifications without weakening parent, leaf-local, or fixed-project-root semantics.
- [ ] 1.3 Inventory every repository-owned Dockerfile `COPY` input and classify it as host implementation, reviewed `docker-assets/`, or leaf-only `.docker-assets-local/`.
- [ ] 1.4 **VALIDATE:** Run `openspec validate compose-parent-constructor-projects` and record a clean dependency baseline.

## 2. Parent-Project Chain Resolution

- [ ] 2.1 **RED:** Add schema tests for optional top-level `parent-project`, absolute and per-declaring-project relative resolution, literal rejection of tilde/environment expansion, fixed inventory naming, and unchanged standalone schema-1 behavior.
- [ ] 2.2 **RED:** Add chain tests for physical normalization, symlinked directory components, missing/non-directory projects, non-regular inventory leaves, self/canonical cycles, the 32-layer boundary, and overflow.
- [ ] 2.3 **RED:** Add POSIX tests proving different hard-linked inventory paths are rejected from `(st_dev, st_ino)` obtained from the descriptor used to read TOML.
- [ ] 2.4 **GREEN:** Implement immutable project-layer and chain-resolution models with physical paths, source descriptors/identities, declared-reference diagnostics, and the 32-layer limit.
- [ ] 2.5 **GREEN:** Extend schema-1 raw loading to accept only the defined `parent-project` metadata and resolve every edge relative to its declaring project.
- [ ] 2.6 **INTROSPECT:** Audit path resolution for CWD/install-root fallback, descriptor/path races, symlink-leaf acceptance, duplicate identities, and effects before complete chain validation.
- [ ] 2.7 **VALIDATE:** Run focused project-root, inventory, cycle, hard-link, and no-side-effect suites.

## 3. Disjoint Raw Inventory Composition

- [ ] 3.1 **RED:** Add merge tests proving tables are structural, arrays are atomic, metadata is exempt, distinct leaves merge base-to-child, and repeated leaves fail globally even with equal values.
- [ ] 3.2 **RED:** Add prefix-validation tests requiring the terminal base and every accumulated prefix to validate, with the first invalid layer and source owners in diagnostics.
- [ ] 3.3 **RED:** Add deterministic serialization and round-trip tests proving merged raw values survive, comments/format do not affect output, `parent-project` is absent, and the ordinary inventory loader accepts the result.
- [ ] 3.4 **RED:** Add override-boundary tests proving different CLI overrides leave merged reviewed TOML unchanged while changing only existing effective projections and build arguments.
- [ ] 3.5 **GREEN:** Implement leaf-path flattening, global provenance, disjoint merge, prefix validation, and deterministic validated-raw TOML serialization.
- [ ] 3.6 **GREEN:** Route inventory consumers through the resolved merged raw configuration before existing effective override processing.
- [ ] 3.7 **INTROSPECT:** Review dynamic tables, empty tables, dotted TOML forms, arrays, schema metadata, error ownership, and default-value leakage from typed models.
- [ ] 3.8 **VALIDATE:** Run focused inventory schema, effective configuration, overrides, display, update discovery, and serialization suites.

## 4. Reviewed and Local Asset Manifests

- [ ] 4.1 **RED:** Add manifest tests for optional `docker-assets/`, empty directories, regular files, exact case-sensitive paths, and leaf-only or absent `.docker-assets-local/`.
- [ ] 4.2 **RED:** Add rejection tests for symlink asset roots and entries, sockets, FIFOs, devices, unreadable entries, file/directory conflicts, duplicate cross-layer paths, and differing shared-directory modes.
- [ ] 4.3 **RED:** Add POSIX inode tests rejecting cross-layer hard-link aliases while accepting same-layer hard links as independent logical paths.
- [ ] 4.4 **RED:** Add Docker-control tests for nearest-child selection, missing controls, non-regular nearest candidates, same-owner `.dockerignore`, no independent fallback, and no ignore-file rewriting.
- [ ] 4.5 **GREEN:** Implement no-follow reviewed/local manifest scanning, exact logical ownership, type/mode collision checks, POSIX physical alias checks, and stable diagnostics before ignore application.
- [ ] 4.6 **GREEN:** Implement nearest-child Dockerfile and paired `.dockerignore` selection as controls outside the asset union.
- [ ] 4.7 **INTROSPECT:** Audit manifest boundaries to prove arbitrary project-root files, parent local state, source inventories, `.env`, and generated outputs cannot enter composition.
- [ ] 4.8 **VALIDATE:** Run focused asset type, mode, identity, Docker-control, and leaf-local isolation suites on POSIX.

## 5. Locked Private Context Lifecycle

- [ ] 5.1 **RED:** Add context allowlist tests for selected controls, merged inventory, composed `docker-assets/`, and leaf-only `.docker-assets-local/`, including the always-present empty local directory.
- [ ] 5.2 **RED:** Add metadata tests for file and unique-directory `0o777` preservation, structural asset-root mode, equal shared-directory modes, empty directories, independent hard-link copies, and omission of ownership/xattrs/special bits.
- [ ] 5.3 **RED:** Add descriptor-snapshot tests that replace or mutate files during copying and require failure before Docker execution.
- [ ] 5.4 **RED:** Add concurrency and cleanup tests for one exclusive executed build per leaf, independent leaves, unique private contexts, normal/failure/interruption cleanup, stale cleanup, and refusal of unsafe names, symlinks, or escapes; block one build inside Docker and prove a waiting build with different overrides cannot overwrite its published effective projection or any other fixed generated output before lock release.
- [ ] 5.5 **RED:** Add `build --dry-run` regressions requiring full chain/control/local-policy/manifest validation and a complete Docker vector with an in-memory planned context path, while asserting no context or generated path creation, lock acquisition, stale cleanup, projection publication, Docker execution, or filesystem mutation.
- [ ] 5.6 **GREEN:** Implement private context creation beneath leaf `.docker-generated/build-contexts/` with owner-private containers and descriptor-based regular-file snapshots for executed builds only.
- [ ] 5.7 **GREEN:** Acquire the per-leaf executed-build lock before effective projection publication or any other fixed `.docker-generated/` build write, hold it through stale cleanup, materialization, Docker completion, and own-context deletion, and implement bounded no-follow cleanup inside that critical section.
- [ ] 5.8 **GREEN:** Route dry-run planning through read-only composition validation and planned-path Docker-vector rendering without entering context, lock, cleanup, or publication services.
- [ ] 5.9 **INTROSPECT:** Audit dry-run no-effect boundaries, pre-lock fixed-output publication, projection overwrite windows, lock release, concurrent processes, handled interruption, stale sensitive local assets, permission restoration, partial contexts, and cleanup confinement.
- [ ] 5.10 **VALIDATE:** Run focused dry-run, materialization, mutation-race, permissions, concurrency, cleanup, and Docker-vector suites.

## 6. Repository Asset-Path Migration

- [ ] 6.1 **RED:** Add semantic scans requiring every Dockerfile-consumed reviewed input under `docker-assets/`, corporate trust under `.docker-assets-local/`, and no build fallback to `docker/` or `.docker-local/`.
- [ ] 6.2 **GREEN:** Move only Dockerfile-consumed files from the host implementation tree into the reviewed `docker-assets/` layout and update every Dockerfile `COPY` path.
- [ ] 6.3 **GREEN:** Rename `.docker-local/` to `.docker-assets-local/`, update corporate bundle resolution and validation, and remove the old tracked-empty-directory mechanism.
- [ ] 6.4 **GREEN:** Update repository scripts, verification inputs, ignore rules, fixtures, and examples atomically to the new fixed paths without compatibility aliases.
- [ ] 6.5 **INTROSPECT:** Verify host Python implementation remains under `docker/`, every image input is present in `docker-assets/`, and no local certificate or generated context can be committed accidentally.
- [ ] 6.6 **VALIDATE:** Run focused Dockerfile source-contract, corporate-network, build-vector, verification, and migration semantic-scan suites.

## 7. Command and Consumer Integration

- [ ] 7.1 **RED:** Add `validate` acceptance tests covering chain, every prefix, Docker controls, and manifests without generated output, network, artifact materialization, or Docker.
- [ ] 7.2 **RED:** Add command-boundary tests proving show/update/run/doctor resolve merged settings but do not require Docker controls or scan assets, and use only leaf local companion state.
- [ ] 7.3 **RED:** Add build acceptance tests proving executed Docker receives only the private composed context, fixed generated outputs remain leaf-owned and serialized through Docker completion, a waiting override build cannot replace the executing build's projection, parent directories remain unmodified, and dry-run emits the complete planned vector while leaving leaf and parent filesystems byte-for-byte unchanged.
- [ ] 7.4 **RED:** Add runtime/update/evidence tests for inherited runtime policy, inherited override policy, merged update sources, unchanged show data shape, owner-rich conflict diagnostics, leaf-local default evidence, and exact external `--output-dir` redirection without changing the parent chain or any other leaf-owned path.
- [ ] 7.5 **GREEN:** Wire validation, build, read-only, runtime, doctor, verification, projection, and evidence consumers to the resolved chain at their specified validation depth.
- [ ] 7.6 **GREEN:** Render canonical builds from the locked private context while retaining existing effective arguments, projection publication, output streaming, and exit classification.
- [ ] 7.7 **INTROSPECT:** Trace every facade command from foreign CWD through parent resolution, leaf-local state, generated outputs, build context, and failure ordering; remove residual source-checkout assumptions.
- [ ] 7.8 **VALIDATE:** Run focused facade, orchestration, display, update, doctor, runtime, acceptance, and no-side-effect suites.

## 8. Documentation and Regression Closure

- [ ] 8.1 Update maintained README translations with parent-chain syntax, relative-path base, depth/cycle/conflict behavior, asset namespaces, nearest Dockerfile selection, leaf-local state, migration, and override boundaries.
- [ ] 8.2 Update examples to show standalone, relative multi-level, absolute centralized, conflict, and corporate-trust leaf layouts without unsupported interpolation or fallback.
- [ ] 8.3 Add documentation semantic scans for fixed names and removal of obsolete `docker/` build-input and `.docker-local/` guidance.
- [ ] 8.4 **INTROSPECT:** Reconcile implementation, main semantic sources, proposal, design, delta specs, tasks, docs, and diagnostics; remove unrelated changes and verify the predecessor dependency is historically satisfied.
- [ ] 8.5 **VALIDATE:** Run the complete project typecheck, lint, unit, integration, acceptance, build, and documentation suites with no skipped or weakened regressions.
- [ ] 8.6 **VALIDATE:** Run `openspec validate compose-parent-constructor-projects` and confirm every modified or added scenario has automated evidence.
