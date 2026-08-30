## MODIFIED Requirements

### Requirement: Use a central version inventory
The project SHALL maintain `docker-constructor.toml` as the single reviewed dependency source with explicit, closed build and runtime sections. `[build.stages.base.node]` SHALL reuse the required exact `node_version` and `npm_version` fields owned by the prerequisite `materialize-build-artifacts-on-host` alongside its reviewed image tag and digest; this change SHALL NOT introduce a second tool-version source, and these fields SHALL remain the sole reviewed expectations for resolver runtime versions, and npm version SHALL NOT be inferred from the image tag. Managed Pi extensions SHALL be represented as exact reviewed root packages whose complete closure is authoritative only in one checked-in `package-lock.json` v3. Ordinary `validate` and `build` SHALL require that existing lockfile to match the roots exactly and contain a complete valid closure. The managed lock owner preflight under `sync-lock` SHALL validate schema, roots, reviewed toolchain pins, and lockfile location without applying root matching or closure checks to the existing lock; it SHALL require those full checks from the generated candidate before publication. The resolver SHALL reject managed-extension runtime overrides and artifact catalogs. Runtime artifact URLs and individually mounted extension blobs SHALL not be part of the managed-extension model.

#### Scenario: Describing managed npm extensions
- **WHEN** the reviewed inventory declares managed Pi extensions
- **THEN** it SHALL declare only exact root package identities and versions
- **AND** ordinary validation and build planning SHALL require a matching checked-in lockfile root set and complete closure
- **AND** transitive packages SHALL not become independently selectable sources

#### Scenario: Declaring reviewed resolver runtime versions
- **WHEN** `[build.stages.base.node]` is validated
- **THEN** it SHALL contain exact non-empty `node_version` and `npm_version` values in addition to the reviewed image tag and digest
- **AND** those two fields SHALL be the only reviewed expected versions used to verify the resolver runtime
- **AND** validation SHALL NOT infer npm version from the image tag

#### Scenario: Rejecting an incomplete or open Node inventory
- **WHEN** `node_version` or `npm_version` is missing or malformed, or `[build.stages.base.node]` contains an unknown field
- **THEN** validation SHALL fail before resolver, network, assembly, or Docker build execution
- **AND** SHALL identify the missing, malformed, or unknown field

#### Scenario: Changing managed extension versions
- **WHEN** a managed extension version changes
- **THEN** the user SHALL update reviewed roots, run `sync-lock`, review the synchronized lockfile set, and rebuild the image
- **AND** `run` SHALL not select an alternative version

#### Scenario: Building with default selections
- **WHEN** the canonical build command runs
- **THEN** it SHALL use the reviewed managed roots and checked-in lockfile to produce the image-owned closure
- **AND** it SHALL not require runtime extension artifact materialization for image correctness

#### Scenario: Validating the reviewed inventory locally
- **WHEN** `docker-constructor.py validate` runs
- **THEN** it SHALL validate exact managed-root matching and the complete existing checked-in lockfile closure without Docker or network access
- **AND** SHALL reject root-lock drift and unknown or phase-inappropriate managed extension fields

#### Scenario: Using owner-specific synchronization validation to repair root drift
- **WHEN** `sync-lock` runs after reviewed TOML roots change while the checked-in lockfile still contains prior roots
- **THEN** the managed lock owner preflight SHALL accept only a closed valid inventory, exact roots, reviewed Node/npm pins, and safe lockfile location without requiring the existing lock to match those roots
- **AND** the generated candidate SHALL match the current roots exactly and pass complete closure validation before atomic publication
- **AND** ordinary `validate` and `build` SHALL continue to reject the same drift until that candidate is published

#### Scenario: Discovering the authoritative inventory
- **WHEN** a facade command runs without an explicit inventory path
- **THEN** it SHALL discover `docker-constructor.toml` and its checked-in managed extension lockfile from the repository root

#### Scenario: Using an explicit custom inventory
- **WHEN** a caller supplies an explicit inventory path
- **THEN** it SHALL require the corresponding checked-in lockfile and the same closed root schema

#### Scenario: Describing uv-managed Python
- **WHEN** the build section declares CPython
- **THEN** its existing dedicated uv-python source and update behavior SHALL remain unchanged

#### Scenario: Describing a Python package tool
- **WHEN** the build section declares `ty`
- **THEN** its existing PyPI source and update behavior SHALL remain unchanged

#### Scenario: Describing runtime npm extensions
- **WHEN** the inventory declares managed Pi extensions
- **THEN** it SHALL use exact roots and the checked-in lockfile rather than a runtime artifact catalog

#### Scenario: Building with a supported override
- **WHEN** a supported build override is requested
- **THEN** it SHALL remain limited to the host-side build projection
- **AND** SHALL not create a managed-extension runtime override

#### Scenario: Generating effective build configuration
- **WHEN** effective Docker construction inputs are rendered
- **THEN** the build projection SHALL remain host-only
- **AND** managed extension roots and lock inputs SHALL be consumed before Docker build

#### Scenario: Preparing runtime dependency configuration
- **WHEN** a runtime container launches
- **THEN** it SHALL not select, materialize, project, or mount managed extension artifacts
- **AND** it SHALL use the image-owned locked closure

#### Scenario: Sharing identical artifact content
- **WHEN** managed extension roots share transitive package content
- **THEN** the checked-in lockfile SHALL represent that closure once
- **AND** runtime SHALL not create artifact mounts

### Requirement: Preserve authoritative focused pins
The central inventory SHALL preserve authoritative reviewed prebuilt artifact pins and their established build-time installation workflows. Managed Pi extensions SHALL be defined as exact reviewed roots in the inventory, their complete closure SHALL be defined only by the checked-in `package-lock.json`, and installation SHALL be performed only by the host-side assembler before Docker build. The former managed-extension runtime installer workflow SHALL NOT be preserved.

#### Scenario: Resolving focused dependency values
- **WHEN** effective construction inputs are generated
- **THEN** the effective build configuration SHALL include each selected prebuilt artifact's reviewed version, platform URLs, and SHA-256 digests
- **AND** reviewed managed extension roots and the checked-in lockfile SHALL be supplied to the host-side assembler before Docker build to produce the image-owned `/opt/pi-extensions` closure
- **AND** pinned managed extension versions SHALL NOT enter an effective runtime configuration or runtime installer workflow

### Requirement: Document the component update workflow concretely
Every maintained README translation SHALL explain how to inspect, review, apply, validate, and rebuild version-managed development-environment components. For managed Pi extensions, documentation SHALL describe only the reviewed-root and lockfile workflow and SHALL NOT instruct users to run a runtime installer, update a mounted extension, select a runtime override, or manage runtime npm artifacts.

#### Scenario: Updating Pi after a release
- **WHEN** a user follows the focused Pi update example
- **THEN** documentation SHALL identify `build.stages.pi-tools.pi` as the inventory path
- **AND** SHALL show a focused update check with a non-mutating suggestion
- **AND** SHALL state that the suggested version is reviewed and applied manually to `docker-constructor.toml`
- **AND** SHALL finish with inventory validation, diff review, image rebuild, and runtime verification

#### Scenario: Understanding update-check options
- **WHEN** a user reads the update reference
- **THEN** `--only` and `--suggest` SHALL be grouped as interactive review controls
- **AND** `--json`, `--strict`, and `--fail-on-outdated` SHALL be grouped as automation or policy controls
- **AND** prerelease and cache controls SHALL be described separately from the ordinary stable update path

#### Scenario: Updating a mounted Pi extension
- **WHEN** a user changes a managed Pi extension
- **THEN** documentation SHALL require updating its exact reviewed root, running `sync-lock`, reviewing and validating the synchronized lockfile set, and rebuilding the image
- **AND** SHALL identify `/opt/pi-extensions` as image-owned output
- **AND** SHALL NOT require or describe a protected installer, mounted Pi-home extension, runtime selection, runtime override, or runtime artifact cache

### Requirement: Separate reviewed launch policy from local runtime state
The closed `runtime` section of `docker-constructor.toml` SHALL own reviewed host-access launch policy, while machine-specific host addresses SHALL reside only in the closed local TOML companion. Managed Pi extensions SHALL have no effective runtime dependency DTO or projection; their exact roots and lockfile SHALL be consumed only by host assembly and image construction, and runtime SHALL use only the image-owned `/opt/pi-extensions` closure.

#### Scenario: Validating host-access policy with runtime scope
- **WHEN** the reviewed inventory contains `[runtime.host-access]`
- **THEN** runtime-scope validation SHALL validate its closed typed policy schema
- **AND** build-only validation and build projection resolution SHALL remain independent of that policy

#### Scenario: Generating the effective runtime dependency projection
- **WHEN** launch inputs are resolved for an image containing managed Pi extensions
- **THEN** Constructor SHALL NOT create a managed-extension runtime DTO, dependency projection, artifact selection, blob materialization, mount plan, installer input, or runtime override
- **AND** SHALL use the image-owned `/opt/pi-extensions` closure without projecting managed-extension metadata into runtime

#### Scenario: Protecting reviewed source from local diagnostics
- **WHEN** `doctor` discovers or refreshes a machine-specific Docker gateway address
- **THEN** it SHALL NOT modify `docker-constructor.toml`
- **AND** ordinary inventory serialization and update discovery SHALL NOT incorporate the local companion

### Requirement: Keep cache directory paths machine-local
The reviewed `docker-constructor.toml` SHALL NOT accept `cache.dir`; a custom dedicated constructor cache root SHALL be read only from an absolute `[cache].dir` in the resolved local TOML companion. When it is absent, cache consumers SHALL use `${XDG_CACHE_HOME}/docker-constructor` when `XDG_CACHE_HOME` is non-empty and absolute, creating a missing XDG directory with `0700` or requiring an existing writable directory; they SHALL use `~/.cache/docker-constructor` only when XDG is empty or non-absolute, and SHALL reject an explicit absolute non-directory or unwritable XDG path without fallback. HTTP update discovery SHALL use the `versioning` child. Managed-extension assembly SHALL use only the assembler-owned opaque download cache and published-environment namespace. Constructor SHALL NOT create `runtime-artifacts/blobs`, a managed npm runtime cache, or per-launch extension cache state. Reviewed `cache.ttl` SHALL remain supported in `docker-constructor.toml` as portable HTTP cache policy.

#### Scenario: Migrating a reviewed cache directory
- **WHEN** validation encounters `cache.dir` in `docker-constructor.toml`
- **THEN** it SHALL reject the retired field with an instruction to move the value to the corresponding local companion
- **AND** SHALL NOT silently copy, merge, or prefer the reviewed path

#### Scenario: Resolving cache settings from separate sources
- **WHEN** reviewed `cache.ttl` and local `[cache].dir` are both configured
- **THEN** HTTP update discovery and managed-extension assembly SHALL use the reviewed policy and resolved local cache root according to their separate ownership contracts
- **AND** neither cache setting SHALL create a managed-extension runtime DTO, projection, or cache input

#### Scenario: Separating cache formats under a local root
- **WHEN** a local `[cache].dir` is configured
- **THEN** update-discovery HTTP cache data SHALL use its `versioning` child
- **AND** managed-extension npm downloads and published environments SHALL remain in the assembler-owned namespace
- **AND** no consumer SHALL create or use `runtime-artifacts/blobs` for managed Pi extensions

#### Scenario: Rejecting the removed HTTP-only command-line cache directory
- **WHEN** a user supplies unsupported `check-deps --cache-dir`
- **THEN** command-line parsing SHALL reject the supplied option as unsupported
- **AND** SHALL NOT interpret it, select a cache path, or migrate cache data
