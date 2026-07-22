## MODIFIED Requirements

### Requirement: Preserve the runtime interface after tool isolation
The runtime image SHALL expose Pi, OpenSpec, Rust/Cargo tools, uv, ty, rtk, and fd on the existing runtime `PATH` after their build stages or installation prefixes are isolated. The Rust toolchain SHALL use rustup's minimal profile and SHALL explicitly include the stable-toolchain `rustfmt` and `clippy` components.

#### Scenario: Running isolated tools in the final image
- **WHEN** the final runtime container is started as user `dev`
- **THEN** `pi`, `openspec`, `cargo`, `rustc`, `rustfmt`, `uv`, `ty`, `rtk`, and `fd` SHALL resolve from `PATH`
- **AND** each required command SHALL execute without requiring build-stage cache mounts
- **AND** `cargo clippy --version` SHALL succeed

#### Scenario: Verifying the minimal Rust profile
- **WHEN** the runtime verification script checks the Rust installation
- **THEN** the active stable toolchain SHALL be available through rustup
- **AND** `rustfmt` SHALL be installed as an explicit component
- **AND** `clippy` SHALL be installed as an explicit component
- **AND** the verification SHALL fail with an actionable error if either component is unavailable
