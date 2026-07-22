# docker-build-caching

## Purpose

Define BuildKit cache reuse and invalidation boundaries for the Docker build, including shared base setup, dependency caches, and independently versioned tools.

## Requirements

### Requirement: Preserve stable layers across tool version changes
The Docker build SHALL scope version build arguments and order layers so that changing one independently versioned tool does not invalidate unrelated operating-system or toolchain setup. `rtk` and `fd` SHALL be fetched as independently pinned prebuilt artifacts with verified SHA-256 digests in separate build stages.

#### Scenario: Upgrading OpenSpec only
- **WHEN** an image has been built and only `OPENSPEC_VERSION` is changed
- **THEN** the subsequent build SHALL reuse cached Debian package, dev-user, Rust, uv, Cargo-tool, and Pi installation results
- **AND** SHALL rebuild the OpenSpec installation and required final assembly only

#### Scenario: Repeating an unchanged build
- **WHEN** the same Dockerfile, context, build arguments, base-image digest, and builder cache are used for a second build
- **THEN** all deterministic build layers SHALL be reused from cache

#### Scenario: Changing the rtk release
- **WHEN** only the pinned `rtk` release or digest changes
- **THEN** the `fd` artifact stage SHALL remain cacheable
- **AND** the runtime SHALL receive the newly verified `rtk` executable

#### Scenario: Changing the fd release
- **WHEN** only the pinned `fd` release or digest changes
- **THEN** the `rtk` artifact stage SHALL remain cacheable
- **AND** the runtime SHALL receive the newly verified `fd` executable

#### Scenario: Artifact integrity failure
- **WHEN** a downloaded `rtk` or `fd` artifact does not match its configured SHA-256 digest
- **THEN** the corresponding build stage SHALL fail
- **AND** the invalid artifact SHALL NOT be copied into the runtime image

### Requirement: Build prebuilt Rust tools independently
The build SHALL provide independent `rtk` and `fd` artifact stages and SHALL copy only their required executables into the runtime image. The initial release pins SHALL be exposed as `RTK_VERSION=v0.43.0` and `FD_VERSION=v10.4.2` build arguments, each paired with an expected SHA-256 digest.

#### Scenario: Building the runtime
- **WHEN** the runtime image is assembled
- **THEN** it SHALL copy `rtk` from the `rtk` artifact stage
- **AND** SHALL copy `fd` from the `fd` artifact stage
- **AND** the runtime stage SHALL perform no network download for either tool

### Requirement: Isolate independently versioned Node tools
The Docker build SHALL install Pi and OpenSpec into independent build stages or prefixes that can be copied into the runtime image separately.

#### Scenario: Changing the Pi version
- **WHEN** only `PI_VERSION` changes
- **THEN** the OpenSpec installation stage SHALL remain cacheable
- **AND** the final image SHALL expose the newly requested Pi and the previously requested OpenSpec

#### Scenario: Changing the OpenSpec version
- **WHEN** only `OPENSPEC_VERSION` changes
- **THEN** the Pi installation stage and Pi-dependent plugin setup SHALL remain cacheable
- **AND** the final image SHALL expose the previously requested Pi and the newly requested OpenSpec

### Requirement: Retain dependency downloads outside image layers
The Docker build SHALL use BuildKit cache mounts for package-manager data whose reuse accelerates an otherwise uncached installation, and correctness SHALL NOT depend on cache contents.

#### Scenario: Rebuilding an invalidated APT layer with a warm cache
- **WHEN** an APT installation layer must execute again and its BuildKit cache mounts are available
- **THEN** retained package metadata and archives SHALL be reusable
- **AND** the cache contents SHALL NOT be included in the resulting image layer

#### Scenario: Building with empty dependency caches
- **WHEN** all BuildKit dependency caches are absent
- **THEN** the build SHALL fetch the required dependencies and complete successfully

### Requirement: Verify cache invalidation boundaries
The project SHALL define a host-side verification procedure that uses plain BuildKit progress output to distinguish executed steps from cached steps.

#### Scenario: Verifying an OpenSpec-only upgrade
- **WHEN** the cache verification procedure rebuilds with only `OPENSPEC_VERSION` changed
- **THEN** its output SHALL show the OpenSpec-specific installation executing
- **AND** SHALL show stable prerequisite and Pi-specific steps as cached
