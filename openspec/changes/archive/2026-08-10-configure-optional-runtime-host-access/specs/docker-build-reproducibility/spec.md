## ADDED Requirements

### Requirement: Separate reviewed launch policy from local runtime state
The closed `runtime` section of `docker-constructor.toml` SHALL own reviewed host-access launch policy, while machine-specific host addresses SHALL reside only in the closed local TOML companion. Neither reviewed host-access policy nor local host address state SHALL enter the effective runtime dependency projection.

#### Scenario: Validating host-access policy with runtime scope
- **WHEN** the reviewed inventory contains `[runtime.host-access]`
- **THEN** runtime-scope validation SHALL validate its closed typed policy schema
- **AND** build-only validation and build projection resolution SHALL remain independent of that policy

#### Scenario: Generating the effective runtime dependency projection
- **WHEN** runtime extension selection is resolved for launch
- **THEN** the mounted effective runtime projection SHALL continue to contain only selected dependency and artifact-validation metadata
- **AND** SHALL exclude host-access mode, host address, proxy port, local companion paths, and local state

#### Scenario: Protecting reviewed source from local diagnostics
- **WHEN** `doctor` discovers or refreshes a machine-specific Docker gateway address
- **THEN** it SHALL NOT modify `docker-constructor.toml`
- **AND** ordinary inventory serialization and update discovery SHALL NOT incorporate the local companion

### Requirement: Keep cache directory paths machine-local
The reviewed `docker-constructor.toml` SHALL NOT accept `cache.dir`; a custom cache directory SHALL be read only from `[cache].dir` in the resolved local TOML companion. Reviewed `cache.ttl` SHALL remain supported in `docker-constructor.toml` as portable cache policy.

#### Scenario: Migrating a reviewed cache directory
- **WHEN** validation encounters `cache.dir` in `docker-constructor.toml`
- **THEN** it SHALL reject the retired field with an instruction to move the value to the corresponding local companion
- **AND** SHALL NOT silently copy, merge, or prefer the reviewed path

#### Scenario: Resolving cache settings from separate sources
- **WHEN** reviewed `cache.ttl` and local `[cache].dir` are both configured
- **THEN** cache consumers SHALL use the reviewed TTL and local directory together
- **AND** neither value SHALL enter an effective build or runtime projection
