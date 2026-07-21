## ADDED Requirements

### Requirement: Reuse shared operating-system setup across image stages
The multi-stage Docker image SHALL derive builder and runtime assembly from a shared base stage for their common operating-system packages and user setup, while builder-only packages SHALL remain outside the final runtime lineage when they are not runtime requirements.

#### Scenario: Building builder and runtime descendants
- **WHEN** Docker builds the tool builder and runtime image
- **THEN** common Debian package and dev-user setup SHALL originate from the same cached base layers
- **AND** common package installation SHALL NOT execute independently in both descendants

### Requirement: Preserve the runtime interface after tool isolation
The runtime image SHALL expose Pi, OpenSpec, Rust/Cargo tools, uv, ty, rtk, and fd on the existing runtime `PATH` after their build stages or installation prefixes are isolated.

#### Scenario: Running isolated tools in the final image
- **WHEN** the final runtime container is started as user `dev`
- **THEN** `pi`, `openspec`, `cargo`, `uv`, `ty`, `rtk`, and `fd` SHALL resolve from `PATH`
- **AND** each command SHALL execute without requiring its build-stage cache mounts
