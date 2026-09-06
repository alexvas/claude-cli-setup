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
The Docker build SHALL install Pi and OpenSpec into independent build stages or prefixes that can be copied into the runtime image separately. Pi extension installation SHALL NOT run during Docker image assembly; extension setup SHALL be performed by the protected runtime setup script after the mounted Pi home is available.

#### Scenario: Changing the Pi version
- **WHEN** only `PI_VERSION` changes
- **THEN** the OpenSpec installation stage SHALL remain cacheable
- **AND** the final image SHALL expose the newly requested Pi and the previously requested OpenSpec

#### Scenario: Changing the OpenSpec version
- **WHEN** only `OPENSPEC_VERSION` changes
- **THEN** the Pi installation stage and Pi-dependent plugin setup SHALL remain cacheable
- **AND** the final image SHALL expose the previously requested Pi and the newly requested OpenSpec

#### Scenario: Changing an extension version
- **WHEN** only a pinned Pi extension version changes
- **THEN** unrelated Docker image stages SHALL remain cacheable
- **AND** the new extension version SHALL be installed by the runtime setup script when invoked

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

### Requirement: Cache locked Pi dependency downloads with the shared assembler
Pi assembly SHALL use the opaque download cache and standalone pinned container supplied by `locked-npm-environment-assembly`. Cache contents SHALL remain outside final image layers, SHALL NOT determine dependency versions independently of the official lockfile, and SHALL be disposable without affecting correctness. BuildKit SHALL perform no Pi npm download or installation.

#### Scenario: Rebuilding Pi with a warm npm cache
- **WHEN** standalone Pi assembly executes with cached tarballs matching the official lockfile
- **THEN** npm SHALL reuse those downloads where valid
- **AND** SHALL install exactly the locked dependency graph

#### Scenario: Building Pi with an empty npm cache
- **WHEN** the shared assembler npm cache is absent or pruned
- **THEN** npm SHALL fetch every required locked dependency before Docker build, verify locked SRI when present, and apply pinned npm's native registry integrity behavior to accepted integrity-less exact HTTPS registry nodes
- **AND** assembler evidence SHALL identify every integrity-less node and canonically hash the published output tree
- **AND** the build SHALL not require Constructor to interpret npm cache internals

### Requirement: Preserve independent artifact-stage invalidation with named inputs
Each logical prebuilt artifact SHALL retain an independent Docker stage and stable named-context filename. Changing one selected artifact or digest SHALL invalidate its consuming stage and dependent assembly while leaving unrelated artifact stages cacheable.

#### Scenario: Changing only the rtk artifact
- **WHEN** only the reviewed rtk bytes or digest change in the named context
- **THEN** the rtk stage and dependent final assembly SHALL rebuild
- **AND** the fd, rustup, uv, Pi, and OpenSpec stages SHALL remain eligible for BuildKit cache reuse
