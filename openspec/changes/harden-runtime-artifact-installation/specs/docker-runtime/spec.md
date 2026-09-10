## MODIFIED Requirements

### Requirement: Expose only effective runtime dependency metadata to the container
The project SHALL derive a narrow effective runtime projection from the reviewed `runtime` section of `docker-constructor.toml` after applying validated runtime overrides. Each reviewed runtime extension SHALL own an artifact catalog keyed by exact version, with exact artifact identity and integrity in every entry, and its selected default version SHALL have a matching catalog entry. The projection SHALL contain only effective package identity, version, the selected artifact identity, checksum/integrity, explicit closed artifact installation type, and validation metadata required for runtime installation and SHALL exclude the reviewed source, unselected artifact alternatives, build section, and host-only runtime metadata. Current runtime extensions SHALL use the `npm-tarball` installation type.

#### Scenario: Mounting runtime dependency configuration
- **WHEN** the constructor facade launches a container
- **THEN** it SHALL validate and mount the generated effective runtime projection read-only at `/run/pi-cli/docker-constructor.runtime.toml`
- **AND** it SHALL NOT mount `docker-constructor.toml` or a host-side effective build projection

#### Scenario: Isolating concurrent runtime projections
- **WHEN** multiple runtime launches use different effective selections
- **THEN** each launch SHALL atomically create and mount a private projection beneath the selected constructor project's external runtime namespace
- **AND** one launch SHALL NOT rewrite another launch's mounted projection
- **AND** the launcher SHALL remove its private host file after Docker exits or launch fails

#### Scenario: Applying a runtime override
- **WHEN** a supported runtime override is supplied to `run`
- **THEN** the resolver SHALL validate it against policy in the reviewed runtime source entry
- **AND** it SHALL select the reviewed artifact catalog entry whose exact version key matches the effective overridden version
- **AND** the mounted projection SHALL contain that version and its matching artifact identity, integrity, and installation type
- **AND** an otherwise policy-valid version with no matching reviewed catalog entry SHALL be rejected before projection creation
- **AND** the resolver SHALL NOT discover artifacts over the network, synthesize artifact URLs, or reuse integrity from another version
- **AND** the reviewed `docker-constructor.toml` SHALL remain unchanged

#### Scenario: Installing Pi extensions at runtime
- **WHEN** the entrypoint or protected installer detects a missing or mismatched configured Pi extension
- **THEN** it SHALL resolve the exact runtime package artifact declared by the effective runtime projection
- **AND** it SHALL reject an unsupported artifact installation type before package mutation
- **AND** it SHALL verify the declared checksum/integrity before installation
- **AND** it SHALL install idempotently into the mounted Pi home
- **AND** it SHALL validate installed package identity and version after installation

#### Scenario: Rejecting host-only metadata at runtime
- **WHEN** the effective runtime projection is generated and validated
- **THEN** its closed DTO schema SHALL reject build entries, update-provider metadata, update/override policy, source fields not needed for runtime installation, and unknown artifact installation types
- **AND** runtime code SHALL NOT require those fields

## ADDED Requirements

### Requirement: Attribute runtime acceptance evidence to its launch
The runtime-artifact acceptance collector SHALL record the offline policy wrapper selected for an offline cache-hit scenario and SHALL inspect only the container belonging to its own launch.

#### Scenario: Recording offline policy provenance
- **WHEN** the acceptance coordinator runs the cache-hit offline scenario through a caller-supplied wrapper
- **THEN** it SHALL record the wrapper path and the scenario command in that scenario's evidence directory

#### Scenario: Concurrent container launches
- **WHEN** another container using the same runtime image is running or starts during evidence collection
- **THEN** the collector SHALL identify and inspect only its own launch container
- **AND** it SHALL record the launch identity and inspected container ID in its evidence directory
