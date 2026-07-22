## MODIFIED Requirements

### Requirement: Preserve the runtime interface after tool isolation
The runtime image SHALL expose Pi, OpenSpec, Rust/Cargo tools, uv, ty, rtk, and fd on the existing runtime `PATH` after their build stages or installation prefixes are isolated. `rtk` and `fd` SHALL be supplied by verified pinned prebuilt release artifacts, and `rtk` integration setup SHALL remain available.

#### Scenario: Running isolated tools in the final image
- **WHEN** the final runtime container is started as user `dev`
- **THEN** `pi`, `openspec`, `cargo`, `uv`, `ty`, `rtk`, and `fd` SHALL resolve from `PATH`
- **AND** each command SHALL execute without requiring build-stage cache mounts
- **AND** `rtk --version` and `fd --version` SHALL report the pinned release versions

#### Scenario: Configuring rtk integration
- **WHEN** the prebuilt `rtk` executable is assembled into the image
- **THEN** the existing `rtk init -g --agent pi` integration SHALL be applied
- **AND** telemetry SHALL remain disabled
- **AND** generated integration files SHALL be owned by `dev`

#### Scenario: Runtime network isolation
- **WHEN** the final runtime stage is assembled
- **THEN** it SHALL copy the verified `rtk` and `fd` executables from artifact stages
- **AND** SHALL NOT download or install either release from the network
