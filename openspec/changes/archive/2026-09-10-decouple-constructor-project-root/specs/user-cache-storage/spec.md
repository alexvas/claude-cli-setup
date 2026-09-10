## ADDED Requirements

### Requirement: Use selected constructor-project identity for external generated state
The constructor SHALL pass the normalized absolute physical path of the selected constructor project to the existing external project-state resolver and SHALL use the resolver's resulting namespace for implicit build projections, runtime projections, and default evidence output. Primary and extra workspaces SHALL remain namespace-neutral and SHALL NOT be supplied as namespace identities merely because they participate in a launch. Explicit `verify --runtime-projection PATH` and evidence `--output-dir DIR` values SHALL remain caller-directed. The constructor SHALL NOT implicitly mutate the constructor project, primary workspace, or any extra workspace. This requirement SHALL NOT redefine cache-root resolution, namespace naming, identity metadata, security, containment, retention, or generated-state routing infrastructure owned by `materialize-build-artifacts-on-host`.

#### Scenario: Selecting one constructor project with multiple workspaces
- **WHEN** a launch selects one constructor project, one primary workspace, and one or more extra workspaces
- **THEN** command orchestration SHALL pass only the normalized absolute physical constructor-project path to the external project-state resolver
- **AND** SHALL use the returned namespace for implicit runtime projection state
- **AND** SHALL NOT request or create a namespace for the primary or any extra workspace

#### Scenario: Integrating implicit generated outputs
- **WHEN** build projection, runtime projection, or default evidence publication requires implicit generated state
- **THEN** command orchestration SHALL use the namespace returned for the selected constructor-project identity
- **AND** SHALL NOT independently derive a cache root, namespace name, identity metadata path, containment boundary, or retention policy

#### Scenario: Preserving explicit runtime projection input
- **WHEN** `verify --runtime-projection PATH` supplies an explicit valid projection
- **THEN** verification SHALL read exactly the caller-directed path
- **AND** SHALL NOT replace it with the constructor project's external default lookup path
- **AND** SHALL NOT change namespace identity

#### Scenario: Preserving explicit evidence output
- **WHEN** an evidence command supplies `--output-dir DIR`
- **THEN** evidence SHALL be written to the caller-directed directory
- **AND** SHALL NOT change the selected constructor project or its external namespace identity

#### Scenario: Leaving constructor project and workspaces unchanged
- **WHEN** an operation succeeds or fails after selecting a constructor project and zero or more workspaces
- **THEN** it SHALL NOT implicitly create `.docker-generated`, `.docker-cache`, projection, evidence, lock, marker, manifest, temporary, or namespace entries beneath the constructor project, primary workspace, or any extra workspace
