## MODIFIED Requirements

### Requirement: Isolate independently versioned Node tools
The Docker build SHALL install Pi and OpenSpec into independent build stages or prefixes that can be copied into the runtime image separately. Pi extension installation SHALL NOT run during Docker image assembly; extension setup SHALL be performed by the protected runtime setup script after the mounted Pi home is available.

#### Scenario: Changing the Pi version
- **WHEN** only `PI_VERSION` changes
- **THEN** the OpenSpec installation stage SHALL remain cacheable
- **AND** the final image SHALL expose the newly requested Pi and the previously requested OpenSpec

#### Scenario: Changing the OpenSpec version
- **WHEN** only `OPENSPEC_VERSION` changes
- **THEN** the Pi installation stage and Pi-dependent plugin setup SHALL remain cacheable
- **AND** the final image SHALL expose the previously requested Pi and the newly requested OpenSpec

#### Scenario: Changing an extension version
- **WHEN** only a pinned Pi extension version changes
- **THEN** unrelated Docker image stages SHALL remain cacheable
- **AND** the new extension version SHALL be installed by the runtime setup script when invoked
