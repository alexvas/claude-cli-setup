## ADDED Requirements

### Requirement: Report host-side build materialization progress
Before the main Docker build starts, the constructor SHALL report the current host-side build-materialization phase in text output mode, including Pi release acquisition, locked dependency assembly, derived-environment validation, and transition to the Docker build. A long-running phase SHALL become visible before it completes. Progress output SHALL obey the same redaction policy as retained diagnostics.

#### Scenario: Pi dependency assembly is long-running
- **WHEN** a text-mode build spends time assembling locked Pi dependencies before the main Docker build
- **THEN** the terminal SHALL identify the Pi assembly phase before it completes
- **AND** redacted assembler warnings or progress SHALL be visible as they are produced

#### Scenario: Build advances to Docker
- **WHEN** host artifact and Pi materialization complete successfully
- **THEN** the constructor SHALL finalize the host-materialization progress state before presenting native Docker build progress

#### Scenario: Structured build output
- **WHEN** a build runs with JSON output
- **THEN** host-materialization progress and assembler output SHALL NOT be written into structured stdout
- **AND** stdout SHALL remain one valid constructor JSON document

#### Scenario: Host materialization fails
- **WHEN** Pi assembly times out or exits unsuccessfully before the main Docker build starts
- **THEN** text output SHALL identify the failed host-materialization phase
- **AND** the main Docker build SHALL NOT execute
