## ADDED Requirements

### Requirement: Document the component update workflow concretely
Every maintained README translation SHALL explain how to inspect, review, apply, validate, and rebuild version-managed development-environment components.

#### Scenario: Updating Pi after a release
- **WHEN** a user follows the focused Pi update example
- **THEN** documentation SHALL identify `stages.pi-tools.pi` as the inventory path
- **AND** SHALL show a focused update check with a non-mutating suggestion
- **AND** SHALL state that the suggested version is reviewed and applied manually to `versions.toml`
- **AND** SHALL finish with inventory validation, diff review, image rebuild, and runtime verification

#### Scenario: Understanding update-check options
- **WHEN** a user reads the update reference
- **THEN** `--only` and `--suggest` SHALL be grouped as interactive review controls
- **AND** `--json`, `--strict`, and `--fail-on-outdated` SHALL be grouped as automation or policy controls
- **AND** prerelease and cache controls SHALL be described separately from the ordinary stable update path

#### Scenario: Updating a mounted Pi extension
- **WHEN** a selected update belongs to `runtime.pi-extensions`
- **THEN** documentation SHALL explain that rebuilding updates the effective image inventory
- **AND** SHALL require rerunning the protected extension installer against the mounted Pi home

### Requirement: Document version-managed component categories
Every maintained README translation SHALL identify component categories, representative members, installation ownership, and update source without duplicating concrete selected versions.

#### Scenario: Reviewing included environment components
- **WHEN** a user reviews what the development image manages
- **THEN** documentation SHALL distinguish the base image, toolchain, Node CLIs, prebuilt binaries, shell runtime, Pi extensions, and Debian packages
- **AND** SHALL distinguish image-owned paths from host-mounted Pi state
- **AND** SHALL state that Debian packages are outside `versions.toml` update discovery
