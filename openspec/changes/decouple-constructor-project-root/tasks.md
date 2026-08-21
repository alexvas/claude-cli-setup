# Implementation Contract

This task list is the binding implementation contract for `decouple-constructor-project-root`.

Rules:

- Phases form a directed acyclic graph (DAG). A phase MAY depend only on phases listed before it.
- A phase SHALL start only after every task in its declared dependencies is complete.
- Tasks within each phase SHALL execute in `RED → GREEN → INTROSPECT → VALIDATE` order.
- `RED` adds or changes executable checks that fail for the missing behavior and does not implement that behavior.
- `GREEN` makes the phase's RED checks pass with the smallest production change that satisfies the active specs.
- `INTROSPECT` checks boundaries, naming, and forbidden coupling after behavior is green; any defect found SHALL be fixed before validation.
- `VALIDATE` runs the phase-specific checks and records a passing result before dependent phases begin.
- A task is complete only when its stated observable result exists. Completing a later task does not implicitly complete an earlier task.

## Phase 1 — Constructor Project Selection

**Dependencies:** none.

**Deliverables:** one immutable normalized constructor-project value; global `--project-directory`; removal of `--inventory`; one resolved project threaded through dispatch without installation-root fallback.

### RED

- [ ] P1.R1 Add resolver tests for default CWD selection, relative selection, absolute selection, symlink normalization, missing paths, non-directory paths, and absence of parent or installation-root fallback.
- [ ] P1.R2 Add path-derivation tests for `docker-constructor.toml`, `docker-constructor.local.toml`, `Dockerfile`, `.env`, `.docker-local/`, and `.docker-generated/` beneath one normalized root.
- [ ] P1.R3 Add parser tests that accept global `--project-directory` and reject `--inventory` without an alias.
- [ ] P1.R4 Add a dispatcher-boundary test proving one resolved constructor-project value is reused for the complete invocation.

### GREEN

- [ ] P1.G1 Implement the immutable constructor-project path value and physical-directory resolver required by P1.R1 and P1.R2.
- [ ] P1.G2 Replace the global inventory request field and parser option with `--project-directory` as required by P1.R3.
- [ ] P1.G3 Resolve the constructor project once in the facade and pass it through the dispatcher boundary as required by P1.R4.

### INTROSPECT

- [ ] P1.I1 Inspect project-selection code for process-CWD rereads, parent discovery, custom inventory derivation, and `_REPO_ROOT` use for project-owned state; remove every occurrence found.

### VALIDATE

- [ ] P1.V1 Run the resolver, path-model, parser, and dispatcher tests introduced in P1.R1–P1.R4 and record that they all pass.

## Phase 2 — Fixed Project-Owned Inputs and Build Contract

**Dependencies:** Phase 1.

**Deliverables:** fixed project-local inventory and companion discovery for all commands; selected-project Docker build context; project-local dotenv and corporate trust input; no installation-checkout input fallback.

### RED

- [ ] P2.R1 Add command-dispatch tests proving `validate`, `show`, and `check-updates` use the CWD-selected or explicitly selected project's fixed inventory.
- [ ] P2.R2 Add build tests for the exact selected-project context and root `Dockerfile` argument vector.
- [ ] P2.R3 Add a build test proving a missing root `Dockerfile` fails with a path-specific CONFIG error before projection publication or Docker execution.
- [ ] P2.R4 Add non-build tests proving commands with a valid inventory do not require `Dockerfile`.
- [ ] P2.R5 Add local-companion tests proving `doctor` and every local-config consumer use only `<project-directory>/docker-constructor.local.toml`.
- [ ] P2.R6 Add cross-project tests proving launcher dotenv resolution ignores the installation checkout and uses only `<project-directory>/.env`.
- [ ] P2.R7 Add cross-project corporate-trust tests proving only `<project-directory>/.docker-local/corporate-ca-bundle.crt` is considered.

### GREEN

- [ ] P2.G1 Change `validate`, `show`, and `check-updates` dispatch to consume the fixed selected-project inventory required by P2.R1.
- [ ] P2.G2 Change build planning to use the selected project as context and its root `Dockerfile` as required by P2.R2–P2.R4.
- [ ] P2.G3 Change `doctor` and local-config consumers to use only the fixed selected-project inventory and companion required by P2.R5.
- [ ] P2.G4 Change launcher dotenv resolution to use the selected project's `.env` required by P2.R6.
- [ ] P2.G5 Change corporate-trust resolution to use the selected project's fixed `.docker-local` bundle required by P2.R7.

### INTROSPECT

- [ ] P2.I1 Inspect all command input paths for custom-inventory companion derivation, alternate basenames, ancestor discovery, or installation-root fallback; remove every active path found.

### VALIDATE

- [ ] P2.V1 Run the command-dispatch, build, local-companion, dotenv, and corporate-trust tests introduced in P2.R1–P2.R7 and record that they all pass.

## Phase 3 — Generated Outputs and Cache Boundaries

**Dependencies:** Phase 1 and Phase 2.

**Deliverables:** project-local build/runtime projection creation; default project-local runtime-projection lookup; preserved caller-directed verify `--runtime-projection`; default project-local evidence; unrestricted explicit evidence output; persistent caches remain distinct from projections and evidence.

### RED

- [ ] P3.R1 Add a build orchestration test proving the effective build projection is atomically published under the selected project's `.docker-generated/` tree.
- [ ] P3.R2 Add run and verify tests proving runtime projections are created under, and looked up by default from, the selected project's `.docker-generated/` tree.
- [ ] P3.R3 Add an evidence test proving omission of `--output-dir` writes to `<project-directory>/.docker-generated/evidence/`.
- [ ] P3.R4 Add an evidence test proving explicit `--output-dir DIR` writes to `DIR`, including when `DIR` is beneath `XDG_CACHE_HOME`.
- [ ] P3.R5 Add an isolation test proving explicit `--output-dir` does not change the constructor-project root or any other project-owned path.
- [ ] P3.R6 Add a foreign-project test proving default projections and evidence are neither read from nor written to the installation checkout or constructor-managed persistent cache.
- [ ] P3.R7 Add a verify test proving `--runtime-projection PATH` reads exactly a valid projection outside the selected project and does not alter any project-owned path.

### GREEN

- [ ] P3.G1 Route effective build projection publication through the selected project's generated-output path required by P3.R1.
- [ ] P3.G2 Route runtime projection creation and default verify lookup through the selected project's generated-output path required by P3.R2.
- [ ] P3.G3 Make the default evidence directory `<project-directory>/.docker-generated/evidence/` as required by P3.R3.
- [ ] P3.G4 Preserve explicit evidence `--output-dir` independently of its location as required by P3.R4 and P3.R5.
- [ ] P3.G5 Preserve verify `--runtime-projection PATH` as a caller-directed lookup independently of its location as required by P3.R7.

### INTROSPECT

- [ ] P3.I1 Inspect generated-output, verification-lookup, and cache APIs to confirm projection creation and default lookup are project-owned, explicit `--runtime-projection` is caller-directed, default evidence is project-owned, explicit evidence is caller-directed, and evidence is never classified as constructor-managed cache content; fix every boundary violation found.

### VALIDATE

- [ ] P3.V1 Run the projection, explicit verification lookup, evidence, cache-boundary, and foreign-project tests introduced in P3.R1–P3.R7 and record that they all pass.

## Phase 4 — Workspace Host Interface

**Dependencies:** Phase 1 and Phase 2.

**Deliverables:** workspace-oriented CLI, domain DTOs, dotenv key, TUI, and evidence/verification inputs; no active host-interface project aliases.

### RED

- [ ] P4.R1 Add CLI tests for `--workspace`/`-w`, repeatable `--extra-workspace`, and `--workspace-root`, including rejection of `--main-project`, `-m`, `--project`, and `--base-project-dir`.
- [ ] P4.R2 Add workspace-selection domain tests that preserve existing lexical absolute-path normalization without resolving workspace symlinks, plus primary/extra ordering, duplicate rejection, and TUI precedence.
- [ ] P4.R3 Add dotenv tests for `WORKSPACE_ROOT`, CLI precedence, home-directory fallback, and rejection of `BASE_PROJECT_DIR` as an active default.
- [ ] P4.R4 Add TUI tests for primary/extra selection, labels, return values, navigation, and scrolling behavior.
- [ ] P4.R5 Add verification/evidence DTO tests requiring workspace-oriented public and domain fields.

### GREEN

- [ ] P4.G1 Implement the workspace CLI and remove project-oriented aliases required by P4.R1.
- [ ] P4.G2 Rename launcher domain types, protocols, fields, diagnostics, and structured data required by P4.R2.
- [ ] P4.G3 Replace `BASE_PROJECT_DIR` with project-local `WORKSPACE_ROOT` behavior required by P4.R3.
- [ ] P4.G4 Migrate the curses TUI model, labels, states, inputs, and outputs required by P4.R4 without changing navigation behavior.
- [ ] P4.G5 Rename verification/evidence workspace inputs and DTO fields required by P4.R5.

### INTROSPECT

- [ ] P4.I1 Inspect public host interfaces and domain boundaries for retained main/additional-project terminology or compatibility translation; remove every active occurrence found.

### VALIDATE

- [ ] P4.V1 Run the CLI, workspace-domain, dotenv, TUI, and verification/evidence DTO tests introduced in P4.R1–P4.R5 and record that they all pass.

## Phase 5 — Container Workspace Contract

**Dependencies:** Phase 4.

**Deliverables:** atomic host/image `WORKSPACE_PATH_1..N` contract; workspace-only entrypoint repair and verification; updated image fixtures.

### RED

- [ ] P5.R1 Add run-vector tests for primary/extra 1:1 bind mounts, primary workdir, consecutive `WORKSPACE_PATH_1..N`, duplicate rejection, and stable ordering.
- [ ] P5.R2 Add entrypoint harness tests for workspace mounts, gaps, non-mounts, disabled repair, symlink safety, permission repair, Git safe-directory registration, and privilege dropping.
- [ ] P5.R3 Add runtime verification tests for consecutive workspace discovery, accessibility, ownership, working-directory equality, gaps, and absence of `PROJECT_PATH_*` fallback.
- [ ] P5.R4 Add an ownership regression test proving host workspace bind-mount repair remains available without whole-home image ownership rewrites.
- [ ] P5.R5 Add host-access and corporate-network run-vector tests using only the workspace container contract.
- [ ] P5.R6 Add an image-fixture compatibility test that fails when launcher, entrypoint, and runtime verification use different container contracts.

### GREEN

- [ ] P5.G1 Change run rendering to emit the workspace mounts, workdir, and environment contract required by P5.R1.
- [ ] P5.G2 Change `docker/entrypoint.sh` to inspect and repair only configured `WORKSPACE_PATH_*` mount points as required by P5.R2 and P5.R4.
- [ ] P5.G3 Change runtime discovery and verification to require consecutive `WORKSPACE_PATH_1..N` with no old-name fallback as required by P5.R3.
- [ ] P5.G4 Update host-access and corporate-network rendering integrations required by P5.R5.
- [ ] P5.G5 Rebuild or adjust image verification fixtures so host launcher, image entrypoint, and verification satisfy P5.R6 atomically.

### INTROSPECT

- [ ] P5.I1 Inspect the host/image boundary for mixed workspace/project contracts, whole-home ownership rewrites, or repair of non-workspace mounts; fix every occurrence found.

### VALIDATE

- [ ] P5.V1 Run the run-vector, entrypoint harness, runtime verification, ownership, host-access, corporate-network, and image-fixture tests introduced in P5.R1–P5.R6 and record that they all pass.

## Phase 6 — Repository Integrations and Documentation

**Dependencies:** Phase 2, Phase 3, Phase 4, and Phase 5.

**Deliverables:** migrated scripts, examples, comments, help, fixtures, and equivalent maintained README translations; executable checks reject obsolete active contracts.

### RED

- [ ] P6.R1 Add semantic migration checks that reject active `--inventory`, custom inventory, removed workspace aliases, `BASE_PROJECT_DIR`, and `PROJECT_PATH_*` while permitting historical archived OpenSpec artifacts.
- [ ] P6.R2 Add documentation contract checks for constructor-project/workspace terminology, fixed project layout, CWD/`--project-directory` usage, and the breaking migration mapping.
- [ ] P6.R3 Add translation-equivalence checks for the supported workflows in the Russian, English, and Chinese READMEs.

### GREEN

- [ ] P6.G1 Update runtime artifact collection and evidence shell scripts to use fixed project-local inventory discovery and the new project/workspace options.
- [ ] P6.G2 Update all repository-owned command examples to use `--project-directory`, `--workspace`, and `--extra-workspace` where applicable.
- [ ] P6.G3 Update code comments, module documentation, help text, error messages, maintained fixtures, and tests to remove obsolete active terminology.
- [ ] P6.G4 Update the Russian README with constructor-project/workspace terminology, fixed layout, generated-output behavior, and migration guidance.
- [ ] P6.G5 Update the English README to be behaviorally equivalent to the Russian README required by P6.G4.
- [ ] P6.G6 Update the Chinese README to be behaviorally equivalent to the Russian README required by P6.G4.

### INTROSPECT

- [ ] P6.I1 Review scripts, examples, diagnostics, fixtures, and all three translations against the active specs; resolve every semantic or translation mismatch found.

### VALIDATE

- [ ] P6.V1 Run the semantic migration and documentation checks introduced in P6.R1–P6.R3 and record that they all pass.

## Phase 7 — End-to-End Acceptance

**Dependencies:** Phase 1, Phase 2, Phase 3, Phase 4, Phase 5, and Phase 6.

**Deliverables:** every facade command works from a foreign project and from default CWD; all project-owned reads/writes are isolated correctly; complete repository and OpenSpec validation pass.

### RED

- [ ] P7.R1 Add acceptance coverage invoking every facade command from outside the source checkout with `--project-directory` and asserting applicable reads, writes, Docker vectors, local state, projections, and default evidence use the selected project.
- [ ] P7.R2 Add acceptance coverage for explicit evidence `--output-dir`, including a destination beneath `XDG_CACHE_HOME`, while asserting all unrelated project-owned paths remain under the selected project.
- [ ] P7.R3 Add acceptance coverage for the default-CWD project flow: validate, build dry-run, run dry-run, doctor planning, and verify path selection.

### GREEN

- [ ] P7.G1 Add only the acceptance fixtures and orchestration corrections required to make P7.R1–P7.R3 pass without weakening their assertions.

### INTROSPECT

- [ ] P7.I1 Search active code, tests, scripts, documentation, and non-archived specs for removed public flags, `BASE_PROJECT_DIR`, authoritative `PROJECT_PATH_*`, installation-checkout project state, or default evidence cache placement; fix every violation found.

### VALIDATE

- [ ] P7.V1 Run the complete unit and acceptance test suites and record that they pass.
- [ ] P7.V2 Run all static, compile, shell-harness, and documentation-contract checks and record that they pass.
- [ ] P7.V3 Run `openspec validate decouple-constructor-project-root --strict` and record that it passes.
