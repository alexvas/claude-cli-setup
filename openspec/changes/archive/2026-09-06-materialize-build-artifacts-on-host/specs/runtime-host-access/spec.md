## ADDED Requirements

### Requirement: Resolve runtime projection state through the external constructor-project namespace
Runtime projection publication and host-path validation SHALL use the invoking-user-owned external project-state namespace beneath the resolved constructor cache root whose identity is the canonical path of the selected constructor project. Primary and extra workspaces are mounted workspaces and SHALL NOT receive separate runtime projection namespaces during that launch. The namespace SHALL remain separate from global runtime-artifact and versioning cache namespaces. Runtime projection validation SHALL accept only contained regular projection files beneath the verified runtime-generated child of that namespace and SHALL reject checkout-local `.docker-generated/runtime` paths, cross-constructor-project paths, symlinks, unsafe types, identity mismatches, and containment escapes before Docker execution. Ownership of the constructor project, primary workspace, or any extra workspace SHALL NOT be required when the invoking user has the read and traversal access needed for reviewed inputs, and none of those directories SHALL be mutated.

#### Scenario: Publishing a runtime projection externally
- **WHEN** a non-dry-run launch with one constructor project, one primary workspace, and zero or more extra workspaces requires an effective runtime projection
- **THEN** the constructor SHALL resolve and verify the external namespace identified by the canonical path of the selected constructor project through the configured or default constructor cache root
- **AND** SHALL atomically publish the projection beneath that namespace's runtime-generated child
- **AND** SHALL create no separate runtime projection namespace for a primary or extra workspace
- **AND** SHALL leave the constructor project, primary workspace, and every extra workspace unchanged

#### Scenario: Rejecting a project-local runtime projection
- **WHEN** launch execution receives a runtime projection host path beneath `.docker-generated/runtime` in the constructor project, primary workspace, or any extra workspace
- **THEN** host-path validation SHALL reject it before Docker execution
- **AND** SHALL NOT adopt, move, delete, or modify the legacy entry

#### Scenario: Rejecting another constructor project's runtime projection
- **WHEN** a runtime projection path is contained by a valid external namespace whose complete identity differs from the canonical path identity of the selected constructor project
- **THEN** host-path validation SHALL reject it before Docker execution
- **AND** SHALL leave both constructor-project namespaces and every constructor-project, primary-workspace, or extra-workspace directory unchanged

#### Scenario: Planning runtime projection state without side effects
- **WHEN** dry-run or another side-effect-free planning operation resolves runtime launch inputs
- **THEN** it SHALL perform no external namespace creation, identity-metadata publication, projection publication, cache mutation, creation of a namespace for a primary or extra workspace, or mutation of any constructor-project, primary-workspace, or extra-workspace directory

### Requirement: Represent an empty runtime extension selection explicitly
The runtime projection schema SHALL require an `extensions` table and SHALL permit that table to contain zero entries. An empty extension selection SHALL serialize as an explicit `[extensions]` table, SHALL remain subject to the same closed-schema validation and external publication lifecycle as a non-empty projection, and SHALL produce no runtime artifact materialization or extension installation. A projection that omits the `extensions` table, gives it a non-table value, or contains unknown top-level or extension fields SHALL be rejected before container execution.

#### Scenario: Launching without runtime extensions
- **WHEN** the effective runtime selection contains zero extensions
- **THEN** the constructor SHALL publish a runtime projection containing an explicit empty `[extensions]` table
- **AND** the runtime installer SHALL accept it as an empty installation plan
- **AND** SHALL download and install no runtime artifacts

#### Scenario: Rejecting an invalid empty-projection schema
- **WHEN** a runtime projection omits the mandatory `extensions` table, represents it with a non-table value, or includes an unknown field
- **THEN** runtime projection validation SHALL reject it before container execution
- **AND** SHALL NOT treat the malformed projection as an empty extension selection
