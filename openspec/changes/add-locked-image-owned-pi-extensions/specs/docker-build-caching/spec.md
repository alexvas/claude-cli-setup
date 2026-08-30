## MODIFIED Requirements

### Requirement: Isolate independently versioned Node tools
The Docker build SHALL install Pi and OpenSpec into independent build stages or prefixes that can be copied into the runtime image separately. The Docker build SHALL assemble locked managed Pi extensions through the host-side assembler boundary and copy the validated closure into an independent image-owned `/opt/pi-extensions` layer. Pi extension installation SHALL NOT run during container startup.

#### Scenario: Changing the Pi version
- **WHEN** only `PI_VERSION` changes
- **THEN** the Pi stage and its dependent final assembly SHALL be invalidated
- **AND** the OpenSpec and locked managed-extension layers SHALL remain eligible for cache reuse when their inputs are unchanged

#### Scenario: Changing an extension version
- **WHEN** reviewed managed extension roots or their checked-in lockfile change
- **THEN** the locked managed-extension layer and dependent final assembly SHALL rebuild
- **AND** unrelated Pi and OpenSpec layers SHALL remain eligible for cache reuse

#### Scenario: Changing the OpenSpec version
- **WHEN** only `OPENSPEC_VERSION` changes
- **THEN** the Pi and locked managed-extension layers SHALL remain eligible for cache reuse
- **AND** the final image SHALL expose the previously requested Pi and newly requested OpenSpec
