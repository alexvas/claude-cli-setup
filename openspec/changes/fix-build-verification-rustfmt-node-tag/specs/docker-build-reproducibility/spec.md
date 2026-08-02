## MODIFIED Requirements

### Requirement: Verify installed tool versions in built image
The system SHALL verify each configured build-time tool against expectations derived from the effective build projection used to build the image. Node verification SHALL require the exact semantic version encoded in a full semantic-version Node image tag. Rust toolchain verification SHALL compare `rustc` and `cargo` to the configured Rust version. When `rustfmt` is configured as a Rust component, verification SHALL prove that rustfmt is installed and resolves through the configured rustup toolchain; it SHALL NOT require rustfmt's independently versioned banner to equal the Rust toolchain version. When `clippy` is configured, verification SHALL continue to verify its expected toolchain-derived version.

#### Scenario: All expected versions match
- **WHEN** a Docker image is built from the effective projection
- **AND** the image reports exact expected versions for Node, Rust, uv, Python, ty, rtk, fd, Pi, OpenSpec, and oh-my-zsh
- **AND** configured Rust components resolve through the configured rustup toolchain
- **THEN** the build verification reports success

#### Scenario: Exact Node image tag matches installed Node
- **WHEN** the effective build projection uses an image tag containing exact Node semantic version `24.18.0`
- **AND** `node --version` reports `v24.18.0`
- **THEN** Node verification reports success

#### Scenario: Floating Node image tag is not exact-verifiable
- **WHEN** the effective build projection uses a Node image tag without an exact semantic version
- **THEN** build verification reports that the Node expectation is not exact-verifiable
- **AND** does not silently accept a major-version-only comparison

#### Scenario: Rustfmt uses an independent component version
- **WHEN** the effective projection configures Rust `1.97.1` with the `rustfmt` component
- **AND** rustfmt resolves through the Rust `1.97.1` rustup toolchain
- **AND** rustfmt reports independent version text such as `rustfmt 1.9.0-stable`
- **THEN** rustfmt verification reports success

#### Scenario: Rustfmt is missing or resolves outside the configured toolchain
- **WHEN** the effective projection configures the `rustfmt` component
- **AND** rustfmt is absent, not installed for the configured toolchain, or resolves outside that toolchain
- **THEN** build verification reports failure identifying the rustfmt provenance mismatch

#### Scenario: Conditional Rust components
- **WHEN** `rustfmt` or `clippy` is absent from the effective projection's components list
- **THEN** build verification does not run the corresponding component check

#### Scenario: Version mismatch
- **WHEN** any configured exact version or Rust component provenance differs from the effective projection
- **THEN** the build verification reports failure with expected and observed values
