## ADDED Requirements

### Requirement: Verify tools against the effective inventory
The runtime image SHALL expose a root-owned read-only effective version inventory, and runtime verification SHALL compare installed tools and extensions with those effective values.

#### Scenario: Verifying configured runtime tools
- **WHEN** the runtime smoke check runs as `dev`
- **THEN** it SHALL verify Node, Rust/Cargo, rustfmt/clippy, uv, Python, ty, Pi, OpenSpec, rtk, and fd against the effective inventory
- **AND** SHALL report actionable version mismatches

#### Scenario: Verifying configured Pi extensions
- **WHEN** the protected Pi extension setup script installs extensions into the mounted Pi home
- **THEN** it SHALL obtain package identity from each entry's npm source metadata and its version from the same effective inventory entry
- **AND** runtime extension verification SHALL compare installed package metadata with those values
- **AND** neither the runtime entry nor the setup script SHALL duplicate the npm package identity

### Requirement: Preserve direct stable Python selection
The effective inventory and runtime SHALL preserve the direct uv-managed Python contract: the default version SHALL be exactly `3.14.6`; supported overrides SHALL be stable numeric `X.Y.Z` values at or above `3.14.6`; and no standalone pip interface SHALL be exposed.

#### Scenario: Verifying direct Python executables
- **WHEN** runtime verification checks `python` and `python3`
- **THEN** both SHALL resolve directly to the effective uv-managed CPython interpreter
- **AND** SHALL NOT resolve through `uv run`, project-aware wrappers, or shell aliases

#### Scenario: Rejecting an unsupported Python selector
- **WHEN** the effective configuration contains a prerelease, non-numeric selector, or version older than `3.14.6`
- **THEN** validation SHALL fail before the Docker build starts
