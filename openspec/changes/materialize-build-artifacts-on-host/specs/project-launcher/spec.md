## ADDED Requirements

### Requirement: Publish implicit launcher state outside constructor and workspaces
The launcher SHALL publish every implicit runtime projection and other launcher-generated control file beneath the invoking-user-owned external namespace whose identity is the canonical path of the selected constructor project. Primary and extra workspaces are mounted workspaces and SHALL NOT receive separate runtime projection namespaces during that launch. Normal launch and verification operations SHALL NOT create `.docker-generated` or another constructor-generated directory beneath the constructor project or any primary or extra workspace. The container-visible projection contents and direct Docker launch contract SHALL remain unchanged by the host-path relocation.

#### Scenario: Launching from foreign-owned readable directories
- **WHEN** the invoking user launches with a readable and traversable constructor project, primary workspace, or extra workspace whose directory or entries are owned by a different user
- **THEN** the launcher SHALL publish its runtime projection beneath the external namespace identified by the constructor project's canonical path
- **AND** SHALL NOT require ownership of or mutate the constructor project or any primary or extra workspace
- **AND** SHALL pass only the required projection file into the container through the existing direct Docker contract

#### Scenario: Launching workspaces through the constructor namespace
- **WHEN** one constructor project, one primary workspace, and one or more extra workspaces participate in a normal launch
- **THEN** the launcher SHALL store its runtime projection only beneath the namespace identified by the canonical path of the selected constructor project
- **AND** SHALL NOT create a namespace or generated entry for a workspace merely because it is mounted for that launch
- **AND** the constructor project, primary workspace, and all extra workspaces SHALL contain no newly created `.docker-generated`, `.docker-cache`, projection, lock, temporary, or evidence entry from that operation

#### Scenario: Preserving side-effect-free dry-run behavior
- **WHEN** the launcher is started with `--dry-run`
- **THEN** it SHALL identify the prospective external project-state location from the canonical path of the selected constructor project without creating the namespace, identity metadata, runtime projection, or any constructor-project, primary-workspace, or extra-workspace generated entry
