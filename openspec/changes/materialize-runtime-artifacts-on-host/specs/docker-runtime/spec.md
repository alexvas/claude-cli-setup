## MODIFIED Requirements

### Requirement: Expose only effective runtime dependency metadata to the container
The project SHALL derive a narrow effective runtime projection from the reviewed `runtime` section of `docker-constructor.toml` after applying validated runtime overrides. Each reviewed runtime extension SHALL own an artifact catalog keyed by exact version, with exact artifact identity and integrity in every entry, and its selected default version SHALL have a matching catalog entry. Before container launch, the host SHALL materialize each selected artifact into a verified content-addressed cache. The projection SHALL contain only effective package identity, version, canonical mounted-artifact identity, checksum/integrity, and validation metadata required for runtime installation; it SHALL exclude downloadable URLs, host cache paths, the reviewed source, unselected artifact alternatives, build entries, and host-only runtime metadata.

#### Scenario: Mounting runtime dependency configuration and artifacts
- **WHEN** the constructor facade launches a container
- **THEN** it SHALL validate and mount the generated effective runtime projection read-only at `/run/pi-cli/docker-constructor.runtime.toml`
- **AND** it SHALL mount each unique selected artifact as an individual read-only file beneath `/run/pi-cli/runtime-artifacts`
- **AND** it SHALL NOT mount the artifact cache root, an unselected artifact, `docker-constructor.toml`, or a host-side effective build projection

#### Scenario: Isolating concurrent runtime projections
- **WHEN** multiple runtime launches use different effective selections
- **THEN** each launch SHALL atomically create and mount a private projection under `.docker-generated/runtime/`
- **AND** one launch SHALL NOT rewrite another launch's mounted projection
- **AND** each launch SHALL mount only its selected immutable cache blobs
- **AND** the launcher SHALL remove its private projection after Docker exits or launch fails without deleting shared published cache blobs

#### Scenario: Applying a runtime override
- **WHEN** a supported runtime override is supplied to `run`
- **THEN** the resolver SHALL validate it against policy in the reviewed runtime source entry
- **AND** it SHALL select the reviewed artifact catalog entry whose exact version key matches the effective overridden version
- **AND** host launch planning SHALL retain that entry's exact URL and integrity for materialization
- **AND** the mounted projection SHALL contain the selected version, canonical mounted-artifact identity, and matching integrity but SHALL omit the URL and host path
- **AND** an otherwise policy-valid version with no matching reviewed catalog entry SHALL be rejected before materialization
- **AND** the resolver SHALL NOT discover artifacts over the network, synthesize an artifact URL, or reuse integrity from another version
- **AND** the reviewed `docker-constructor.toml` SHALL remain unchanged

#### Scenario: Installing Pi extensions from mounted artifacts
- **WHEN** the entrypoint or protected installer detects a missing or mismatched configured Pi extension
- **THEN** it SHALL locate the selected artifact only beneath the fixed mounted-artifact root
- **AND** it SHALL reject a missing, writable, symlinked, non-regular, traversal, identity-mismatched, or integrity-mismatched artifact
- **AND** it SHALL verify the declared checksum/integrity before package execution
- **AND** package execution SHALL consume the exact verified bytes without reopening a mutable named file
- **AND** it SHALL install idempotently into the mounted Pi home
- **AND** it SHALL validate installed package identity, version, and ownership after installation

#### Scenario: Avoiding runtime artifact downloads
- **WHEN** protected runtime installation requires an artifact
- **THEN** container code SHALL read the individually mounted read-only blob
- **AND** it SHALL NOT download the artifact, query a registry, consume the reviewed URL, or create a download workspace

#### Scenario: Rejecting host-only metadata at runtime
- **WHEN** the effective runtime projection is generated and validated
- **THEN** its closed DTO schema SHALL reject downloadable URLs, host cache roots or paths, build entries, update-provider metadata, update/override policy, and source fields not needed for mounted-artifact validation
- **AND** runtime code SHALL NOT require those fields
