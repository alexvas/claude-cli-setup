## ADDED Requirements

### Requirement: Select one constructor project directory
Every facade invocation SHALL select exactly one constructor project directory from global `--project-directory DIR` when supplied and from the process current working directory otherwise. A relative explicit path SHALL be interpreted relative to the process current working directory. The selected directory SHALL be normalized to an absolute physical path and SHALL remain authoritative for the complete command transaction.

#### Scenario: Using the current working directory
- **WHEN** a facade command runs without `--project-directory`
- **THEN** the constructor project directory SHALL be the normalized absolute physical path of the process current working directory
- **AND** the constructor SHALL NOT fall back to the tool installation or source checkout

#### Scenario: Selecting an explicit project directory
- **WHEN** a facade command runs with `--project-directory DIR`
- **THEN** the constructor SHALL resolve `DIR` relative to the process current working directory when necessary
- **AND** SHALL use its normalized absolute physical path as the constructor project directory

#### Scenario: Rejecting an invalid project directory
- **WHEN** the selected path is missing or is not a directory
- **THEN** the command SHALL fail with an actionable CLI or CONFIG diagnostic identifying the path
- **AND** SHALL perform no project mutation, network request, artifact materialization, or Docker execution

### Requirement: Use a fixed project-owned layout
The selected constructor project SHALL own the fixed paths `docker-constructor.toml`, `docker-constructor.local.toml`, `Dockerfile`, `.env`, `.docker-local/`, and `.docker-generated/` directly beneath its root. Validation, display, update discovery, build, run, doctor, and verification SHALL derive all applicable project-owned inputs, outputs, and default lookup paths from that same root. Caller-directed overrides that remain part of the public contract, including verify `--runtime-projection PATH`, SHALL retain their explicit paths without changing the constructor-project root or any other project-owned path. The CLI SHALL NOT accept `--inventory` or discover an inventory from the tool installation or a parent directory.

#### Scenario: Resolving project-owned paths
- **WHEN** a constructor project at `/envs/agent` is selected
- **THEN** the reviewed inventory SHALL be `/envs/agent/docker-constructor.toml`
- **AND** the local companion SHALL be `/envs/agent/docker-constructor.local.toml`
- **AND** local inputs and generated outputs SHALL resolve beneath `/envs/agent/.docker-local` and `/envs/agent/.docker-generated`

#### Scenario: Missing reviewed inventory
- **WHEN** a command requiring reviewed configuration selects a project without `docker-constructor.toml`
- **THEN** it SHALL fail with a CONFIG error containing the absolute expected path
- **AND** SHALL NOT search the constructor installation, ancestors, or alternate filenames

#### Scenario: Rejecting the removed inventory option
- **WHEN** a caller supplies `--inventory`
- **THEN** argument parsing SHALL fail with a CLI error
- **AND** no compatibility alias or custom inventory basename SHALL be accepted

#### Scenario: Verifying an explicit external runtime projection
- **WHEN** `verify --runtime-projection PATH` supplies a valid projection outside the selected constructor project
- **THEN** verification SHALL read the projection from exactly `PATH`
- **AND** SHALL NOT replace it with the project-local default lookup path
- **AND** SHALL NOT change the constructor-project root or the location of any other project-owned file

### Requirement: Build the selected self-contained project Dockerfile
The canonical build command SHALL use the selected constructor project directory as its Docker build context and the file named exactly `Dockerfile` at that root. The constructor SHALL NOT accept an alternate Dockerfile selector, merge another context, or inject build assets from its installation directory.

#### Scenario: Building a selected constructor project
- **WHEN** build selects `/envs/agent` containing the reviewed inventory and `Dockerfile`
- **THEN** the rendered Docker command SHALL use `/envs/agent` as its build context
- **AND** SHALL use `/envs/agent/Dockerfile` as the sole canonical Dockerfile

#### Scenario: Missing project Dockerfile
- **WHEN** build selects a project whose root has no `Dockerfile`
- **THEN** build SHALL fail with a path-specific CONFIG error before projection publication or Docker execution

#### Scenario: Non-build command without Dockerfile
- **WHEN** a non-build command selects a project with a valid inventory but no Dockerfile
- **THEN** that command SHALL NOT fail solely because Dockerfile is absent
