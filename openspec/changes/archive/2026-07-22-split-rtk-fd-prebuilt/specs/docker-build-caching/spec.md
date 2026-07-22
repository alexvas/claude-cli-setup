## MODIFIED Requirements

### Requirement: Preserve stable layers across tool version changes
The Docker build SHALL scope version build arguments and order layers so that changing one independently versioned tool does not invalidate unrelated operating-system or toolchain setup. `rtk` and `fd` SHALL be fetched as independently pinned prebuilt artifacts with verified SHA-256 digests in separate build stages.

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

#### Scenario: Repeating an unchanged build
- **WHEN** the same Dockerfile, context, build arguments, artifact URLs, digests, base-image digest, and builder cache are used for a second build
- **THEN** all deterministic build layers SHALL be reused from cache

## ADDED Requirements

### Requirement: Build prebuilt Rust tools independently
The build SHALL provide independent `rtk` and `fd` artifact stages and SHALL copy only their required executables into the runtime image. The initial release pins SHALL be exposed as `RTK_VERSION=v0.43.0` and `FD_VERSION=v10.4.2` build arguments, each paired with an expected SHA-256 digest.

#### Scenario: Building the runtime
- **WHEN** the runtime image is assembled
- **THEN** it SHALL copy `rtk` from the `rtk` artifact stage
- **AND** SHALL copy `fd` from the `fd` artifact stage
- **AND** the runtime stage SHALL perform no network download for either tool
