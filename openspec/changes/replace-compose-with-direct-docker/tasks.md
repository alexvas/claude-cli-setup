## 1. Stage 1 — Reviewed Inventory Root and Typed Phase Containers

### RED

- [x] 1.1 Add failing tests requiring one `docker-constructor.toml` root with `schema`, explicit `build` and `runtime` tables, optional host-side `cache`, and path-aware missing-section errors.
- [x] 1.2 Add failing model tests for frozen `BuildInventory`, `RuntimeInventory`, and root `Inventory` containers with immutable nested collections.

### GREEN

- [x] 1.3 Introduce typed build/runtime source containers and make the root inventory expose them without importing CLI, Docker, networking, launcher, or installer modules.
- [x] 1.4 Add canonical root-envelope parsing behind a temporary internal legacy-layout adapter so existing fixtures remain green until Stage 2; do not expose legacy layout as a public schema.

### INTROSPECT

- [x] 1.5 Review root-model ownership and ensure phase containers retain complete typed source, update, artifact, and override metadata rather than generic dictionaries.
- [x] 1.6 Confirm `cache` remains host-side and gateway, UID/GID, ownership, launcher defaults, and project paths are absent from both dependency containers.

### VALIDATE

- [x] 1.7 Run focused root-envelope/model tests and existing inventory tests without Docker or network access.
- [x] 1.8 Run type/import checks, `git diff --check`, and strict OpenSpec validation.

## 2. Stage 2 — Canonical Build Section and Build Dependency Migration

### RED

- [x] 2.1 Add failing closed-schema tests for `build.stages`, full canonical build paths, unknown or misspelled fields, misplaced Pi extensions, and actionable errors.
- [x] 2.2 Add failing migration-contract tests proving every existing build dependency appears exactly once under `build`, with unchanged selected versions, revisions, URLs, digests, artifacts, and policies.

### GREEN

- [x] 2.3 Parse and validate build dependencies directly from canonical `build.stages.*` paths and update source/provider compatibility and known-key registrations accordingly.
- [x] 2.4 Migrate `docker-constructor.toml`, shared test builders, active TOML fixtures, and Docker-independent verification inputs from `[stages.*]` to `[build.stages.*]`; remove the temporary legacy-layout adapter.

### INTROSPECT

- [x] 2.5 Review Docker-stage naming versus installation-phase ownership, confirming `build.stages.runtime.oh-my-zsh` remains build-owned despite its stage name.
- [x] 2.6 Compare pre/post-migration dependency values and reject accidental version changes, duplicated defaults, operational settings, or runtime-extension entries in `build`.

### VALIDATE

- [x] 2.7 Run focused build-schema, inventory, fixture, provider/source, and semantic-source tests without Docker or network access.
- [x] 2.8 Run type/import checks, `git diff --check`, and strict OpenSpec validation.

## 3. Stage 3 — Canonical Runtime Section and Cross-Phase Ownership

### RED

- [x] 3.1 Add failing closed-schema tests for `runtime.pi-extensions`, complete typed extension entries, unknown fields, invalid source/provider combinations, and unsupported override policy.
- [x] 3.2 Add failing semantic tests for build entries misplaced in runtime, runtime entries misplaced in build, and duplicate dependency identities across phases with both paths in the error.

### GREEN

- [x] 3.3 Complete typed runtime-section parsing and immutable extension mappings while retaining all reviewed host-side metadata required by later update, override, artifact, and validation workflows.
- [x] 3.4 Implement explicit phase-placement and cross-phase identity validation, then migrate all existing Pi extensions into exactly one runtime section without changing selected package versions.

### INTROSPECT

- [x] 3.5 Review identity rules per source type so duplicate detection uses package/repository identity rather than display keys or coincidentally equal versions.
- [x] 3.6 Confirm the reviewed runtime source remains broader than the later mounted DTO while containing no operational host settings or session project paths.

### VALIDATE

- [x] 3.7 Run focused runtime-schema, compatibility, duplicate-identity, immutability, and complete inventory tests without Docker or network access.
- [x] 3.8 Run the daemon-independent green loop, type/import checks, `git diff --check`, and strict OpenSpec validation.

## 4. Stage 4 — Effective Build Projection

### RED

- [x] 4.1 Add failing resolver tests for default build selections, supported overrides, platform artifacts, URL/version consistency, and deterministic projection ordering.
- [x] 4.2 Add failing filesystem tests for atomic `.docker-generated/docker-constructor.build.effective.toml` replacement, validation before replacement, interrupted writes, and unsafe output paths.

### GREEN

- [x] 4.3 Implement a pure typed build resolver that accepts the reviewed build model plus overrides and returns the effective build projection without invoking Docker.
- [x] 4.4 Implement validated atomic serialization of the effective build projection at the canonical host-only path.

### INTROSPECT

- [x] 4.5 Verify defaults and override constraints remain inventory-owned rather than becoming Python or Dockerfile constants.
- [x] 4.6 Review projection contents and remove runtime entries, host operational state, and fields not required for construction or host-side verification.

### VALIDATE

- [x] 4.7 Run build resolver, serialization, override, and fake-filesystem tests without Docker.
- [x] 4.8 Run type/import checks and `git diff --check`.

## 5. Stage 5 — Effective Runtime Projection

### RED

- [x] 5.1 Add failing resolver tests for default and overridden Pi-extension versions, matching artifact identity/integrity, and preservation of the reviewed source.
- [x] 5.2 Add failing closed-DTO tests proving the runtime projection rejects build entries, update providers, update/override policy, and unrelated source metadata.
- [x] 5.3 Add failing lifecycle tests for atomic private files under `.docker-generated/runtime/`, concurrent override isolation, and cleanup after success or failure.

### GREEN

- [x] 5.4 Implement a pure typed runtime resolver that applies validated runtime overrides and explicitly selects only installer-required DTO fields.
- [x] 5.5 Implement private per-launch runtime projection creation, validation, stable identity reporting, and cleanup through injected filesystem boundaries.

### INTROSPECT

- [x] 5.6 Review the source-to-DTO mapping field by field and eliminate implicit whole-section copying or generic dictionary passthrough.
- [x] 5.7 Confirm concurrent launches cannot rewrite each other's mounted input and runtime resolution never mutates `docker-constructor.toml`.

### VALIDATE

- [x] 5.8 Run runtime resolver, schema, concurrency, and fake-filesystem tests without Docker or network access.

## 6. Stage 6 — Pure Direct-Docker Command Rendering

### RED

- [x] 6.1 Add failing tests for deterministic `docker build` vectors: context, runtime target, canonical image tag, platform, build arguments, cache, pull, and progress controls.
- [x] 6.2 Add failing tests for deterministic `docker run` vectors: read-only runtime projection, Pi home, projects, working directory, `PROJECT_PATH_*`, host mapping, name, removal, TTY, and command passthrough.
- [x] 6.3 Add failing edge-case tests for spaces, empty optional projects, argument ordering, shell-escaped display, and rejection of reviewed-source or effective-build mounts.

### GREEN

- [x] 6.4 Implement pure build and run renderers that return argument lists and never execute Docker.
- [x] 6.5 Implement a separate shell-escaped display renderer without feeding rendered strings back into subprocess execution.

### INTROSPECT

- [x] 6.6 Remove Compose terminology, environment interpolation, hidden dependency defaults, and subprocess coupling from the command model.
- [x] 6.7 Confirm build arguments and runtime package inputs originate only from their validated phase projections.

### VALIDATE

- [x] 6.8 Run renderer tests, type/import checks, and `git diff --check` without Docker.

## 7. Stage 7 — Reusable Gateway Networking and Doctor APIs

### RED

- [x] 7.1 Add failing tests for rootful/rootless detection, candidate ordering, successful and failed probes, and structured diagnosis results.
- [x] 7.2 Add failing tests for rootless override planning/application, explicit consent, existing operational gateway persistence, and process/filesystem/service failures.
- [x] 7.3 Use injected process, filesystem, HTTP-probe, and service-control fakes so tests require neither Docker nor systemd.

### GREEN

- [x] 7.4 Extract gateway diagnosis and rootless override behavior from `docker/build_wrapper.py` into a dedicated internal networking module.
- [x] 7.5 Expose structured diagnosis, persistence, override planning, and explicit application APIs without CLI parsing or exit-code policy.

### INTROSPECT

- [x] 7.6 Verify the module does not import the facade, mutate global process state implicitly, or execute Docker/systemd outside injected boundaries.
- [x] 7.7 Compare extracted behavior with rootful/rootless contracts and eliminate duplicated gateway logic.

### VALIDATE

- [x] 7.8 Run networking and doctor API tests, dependency checks, and `git diff --check` without Docker or user systemd.

## 8. Stage 8 — Read-Only Facade Commands

### RED

- [x] 8.1 Add failing facade tests for global options, help, one explicit inventory path, output modes, verbosity, color, input errors, and exit-code mapping.
- [x] 8.2 Add failing scoped tests for `validate`, `show`, and `check-updates` with `build|runtime|all`, effective display, provider/path filters, suggestions, prerelease, cache, policy exits, and JSON.
- [x] 8.3 Add failing tests proving `schema` is absent and read-only commands cannot invoke Docker or mutate the reviewed inventory.

### GREEN

- [x] 8.4 Add `docker/docker-constructor.py` as the thin sole public facade and wire `validate`, `show`, and `check-updates` to focused internal APIs.
- [x] 8.5 Preserve provider behavior and scoped update discovery while rendering build/runtime source or effective projections as explicitly requested.

### INTROSPECT

- [x] 8.6 Ensure the facade owns only argument validation, presentation, prompts, and exit-code mapping; inventory traversal and providers remain internal.
- [x] 8.7 Verify help and errors consistently name `docker/docker-constructor.py` and only the agreed command surface.

### VALIDATE

- [x] 8.8 Run facade, inventory, effective-display, and provider tests with fake boundaries and no Docker.

## 9. Stage 9 — Build and Doctor Orchestration

### RED

- [x] 9.1 Add failing `build` tests for build overrides, projection generation, gateway API reuse, platform/cache controls, confirmation, dry-run, and direct execution with fake processes.
- [x] 9.2 Add failing `doctor` tests for read-only diagnosis, unavailable gateways, explicit rootless repair consent, denied consent, persistence failures, and service failures.

### GREEN

- [x] 9.3 Implement the internal build transaction over validated source, effective build projection, gateway diagnosis, pure rendering, and injected Docker execution.
- [x] 9.4 Wire facade `build` and `doctor` commands to the internal APIs while preserving canonical image naming and explicit repair intent.

### INTROSPECT

- [x] 9.5 Confirm transaction/domain logic does not migrate into facade handlers and ordinary import or validation paths cannot execute Docker.
- [x] 9.6 Review failure ordering so invalid inventory or projection state cannot trigger gateway mutation or Docker execution.

### VALIDATE

- [x] 9.7 Run build/doctor orchestration, prompt, dry-run, and subprocess-failure tests with fakes.
- [x] 9.8 Run type/import checks and `git diff --check` without Docker.

## 10. Stage 10 — Protected Runtime Extension Installer

### RED

- [x] 10.1 Add failing installer tests for closed DTO validation, exact artifact resolution, checksum/integrity rejection, interrupted installation, and actionable failures.
- [x] 10.2 Add failing tests for idempotent installation, mismatched installed packages, post-install identity/version validation, Pi-home ownership, and dry-run behavior.

### GREEN

- [x] 10.3 Implement the internal runtime installer over the mounted projection with integrity verification before mutation and injected download/package boundaries.
- [x] 10.4 Integrate extension setup with entrypoint ownership repair, safe-directory setup, and privilege drop without broadening the runtime DTO.

### INTROSPECT

- [x] 10.5 Review trust boundaries so package execution cannot precede integrity verification and failures cannot leave a falsely validated installation.
- [x] 10.6 Confirm installer code does not read the reviewed inventory, build projection, update providers, or override policy.

### VALIDATE

- [x] 10.7 Run installer, entrypoint, ownership, and failure-recovery tests with fake filesystem/network/package boundaries.
- [x] 10.8 Run shell/static checks and `git diff --check` without Docker or network access.

## 11. Stage 11 — Direct Project Launcher and Run Command

### RED

- [x] 11.1 Add failing launcher tests for project selection, no-main-project errors, optional projects, `pi-N` allocation, Pi home, 1:1 mounts, working directory, and `PROJECT_PATH_*`.
- [x] 11.2 Add failing run-transaction tests for runtime overrides, private projection creation, read-only mount, gateway mapping, TTY modes, dry-run, Docker failure, and projection cleanup.
- [x] 11.3 Model Docker inspection and execution behind injected process fakes so all launcher tests remain daemon-independent.

### GREEN

- [x] 11.4 Move project selection behind an internal launcher API and replace generated Compose fragments and `COMPOSE_FILE` assembly with the pure run renderer.
- [x] 11.5 Wire facade `run` to runtime resolution, private projection lifecycle, direct execution, and cleanup while preserving image and entrypoint behavior.

### INTROSPECT

- [x] 11.6 Verify paths remain individual arguments rather than shell/YAML strings and dry-run creates no lingering configuration files.
- [x] 11.7 Review concurrency, signal/exception cleanup, optional-project boundaries, and absence of reviewed/build configuration in rendered mounts.

### VALIDATE

- [x] 11.8 Run launcher, TUI, runtime lifecycle, and dry-run tests with fakes and no Docker.

## 12. Stage 12 — Internal Verification and Evidence Collection APIs

### RED

- [x] 12.1 Add failing verification tests comparing container observations with host-side effective build expectations without providing build metadata to the container.
- [x] 12.2 Add failing runtime verification tests for projection identity, read-only mount, extension results, projects, working directory, ownership, Pi home, gateway mapping, and forbidden configuration paths.
- [x] 12.3 Add daemon-independent collector tests for commands, exit codes, timestamps, bounded output, image inspection, checksums, redaction, failures, and a human-readable index.

### GREEN

- [x] 12.4 Consolidate verification rules behind structured internal APIs and wire facade `verify` to check selection and presentation only.
- [x] 12.5 Implement `verify --collect-evidence` over injected process/filesystem boundaries, including canonical build and representative runtime observations.

### INTROSPECT

- [x] 12.6 Ensure verification executables are no longer competing public entry points and the collector does not duplicate facade or launcher domain logic.
- [x] 12.7 Review bundle determinism, size bounds, secret/environment redaction, host metadata, and diagnostic completeness.

### VALIDATE

- [x] 12.8 Run verification and collector tests against fake subprocesses and inspect generated fixtures without Docker.

## 13. Stage 13 — Repository Migration and Obsolete Surface Removal

### RED

- [x] 13.1 Add failing semantic-source and documentation tests rejecting supported references to old CLIs, wrappers, Compose, generated fragments, obsolete inf-splitter settings, separate phase source inventories, and forbidden runtime configuration paths.
- [x] 13.2 Add failing command-contract tests requiring the facade in repository-owned callers and direct API imports—not CLI subprocesses—in internal tests.

### GREEN

- [ ] 13.3 Migrate rootless helpers, examples, verification helpers, acceptance harnesses, active OpenSpec artifacts, and maintained Russian, English, and Chinese documentation; update every maintained README to remove the legacy two-additional-project limit and document consecutive `PROJECT_PATH_2..N` numbering.
- [ ] 13.4 Remove `docker/build_wrapper.py`, user-facing `docker/versions.py`, `launch-pi.py`, Compose files/fragments/classification, obsolete verification adapters, and their superseded tests.
- [ ] 13.5 Remove `docker/gen-models-json.py`, generator-only tests, stale inf-splitter settings, runtime copies of reviewed/build metadata, and Docker Compose prerequisites.

### INTROSPECT

- [ ] 13.6 Search supported source and documentation for stale contracts while excluding historical archived OpenSpec artifacts from migration requirements.
- [ ] 13.7 Review deletions for lost behavior or excess disclosure: image tag, caching, gateway, projects, ownership, extensions, effective expectations, and runtime isolation.

### VALIDATE

- [ ] 13.8 Run documentation, semantic-source, command-contract, full unit, compile/import, strict OpenSpec, and `git diff --check` validations without Docker.

## 14. Stage 14 — Portable Docker-Host Acceptance Evidence

> Only this stage requires Docker. The collector runs on a Docker-capable host and writes a portable, self-describing bundle that can be copied into the development container for agent review.

### RED

- [ ] 14.1 Finalize daemon-independent acceptance fixtures covering failed build/run commands, mismatched image expectations, bad runtime mounts, exposed source/build paths, project errors, and unsuccessful extension checks.
- [ ] 14.2 Confirm each simulated failure leaves enough structured and raw evidence for diagnosis without rerunning Docker.

### GREEN

- [ ] 14.3 On a Docker-capable host, invoke `docker/docker-constructor.py verify --collect-evidence <path>` for one canonical build and representative main-plus-additional-project launch.

### INTROSPECT

- [ ] 14.4 Compare collected command arguments and container state with daemon-independent fixtures; convert each mismatch into a regression test before implementation changes.
- [ ] 14.5 Inspect the bundle for runtime projection identity, read-only mount, absence of reviewed/build configuration, integrity-checked extensions, expected image contents, and redaction.

### VALIDATE

- [ ] 14.6 Preserve and checksum the host-generated evidence bundle, then copy it into the development container.
- [ ] 14.7 In the development container, rerun the complete daemon-independent validation suite and strict OpenSpec validation.
- [ ] 14.8 Have the agent review the copied index, structured evidence, and bounded raw outputs against every change requirement and record acceptance findings.
