## MODIFIED Requirements

### Requirement: Use a fixed project-owned layout
The selected leaf constructor project SHALL own the fixed paths `docker-constructor.toml`, `docker-constructor.local.toml`, `.env`, `.docker-assets-local/`, and `.docker-generated/` directly beneath its root. Every explicit constructor-project layer SHALL own its fixed reviewed inventory at `docker-constructor.toml`, MAY own reviewed build inputs beneath `docker-assets/`, and MAY supply `Dockerfile` plus its paired `.dockerignore`. Validation, display, update discovery, build, run, doctor, and verification SHALL derive merged reviewed inputs from the explicit project chain while deriving machine-local inputs and generated outputs only from the selected leaf. Caller-directed overrides that remain part of the public contract, including verify `--runtime-projection PATH`, SHALL retain their explicit paths without changing the leaf constructor-project root or any other project-owned path. The CLI SHALL NOT accept `--inventory`, discover a project from the tool installation, or search filesystem ancestors implicitly.

#### Scenario: Resolving leaf-owned and inherited paths
- **WHEN** a leaf constructor project at `/envs/agent` explicitly inherits one or more parent projects
- **THEN** the leaf reviewed inventory SHALL begin at `/envs/agent/docker-constructor.toml`
- **AND** the local companion SHALL be `/envs/agent/docker-constructor.local.toml`
- **AND** local assets and generated outputs SHALL resolve beneath `/envs/agent/.docker-assets-local` and `/envs/agent/.docker-generated`
- **AND** reviewed parent inventories and `docker-assets/` SHALL resolve only through explicit `parent-project` references

#### Scenario: Missing reviewed leaf inventory
- **WHEN** a command requiring reviewed configuration selects a leaf project without `docker-constructor.toml`
- **THEN** it SHALL fail with a CONFIG error containing the absolute expected path
- **AND** SHALL NOT search the constructor installation, filesystem ancestors, or alternate filenames

#### Scenario: Rejecting the removed inventory option
- **WHEN** a caller supplies `--inventory`
- **THEN** argument parsing SHALL fail with a CLI error
- **AND** no compatibility alias or custom inventory basename SHALL be accepted

#### Scenario: Verifying an explicit external runtime projection
- **WHEN** `verify --runtime-projection PATH` supplies a valid projection outside the selected leaf constructor project
- **THEN** verification SHALL read the projection from exactly `PATH`
- **AND** SHALL NOT replace it with the leaf-local default lookup path
- **AND** SHALL NOT change the leaf constructor-project root, parent chain, or location of any other project-owned file

## REMOVED Requirements

### Requirement: Build the selected self-contained project Dockerfile
**Reason**: Explicit parent-project composition replaces the self-contained leaf context and permits the nearest child-side Dockerfile to be inherited.

**Migration**: Use the replacement “Build the selected composed project Dockerfile” requirement, place reviewed build inputs beneath `docker-assets/`, and keep machine-local build inputs beneath leaf `.docker-assets-local/`.

## ADDED Requirements

### Requirement: Build the selected composed project Dockerfile
The canonical build command SHALL materialize one private context from the selected leaf and its explicit parent-project chain. It SHALL select the nearest regular `Dockerfile` while traversing leaf to terminal base and SHALL use only that file's same-layer `.dockerignore` when present. The constructor SHALL NOT use a source project root directly as the Docker context, accept an alternate Dockerfile selector, add an implicit parent, or inject build assets from its installation directory.

#### Scenario: Building a composed constructor project
- **WHEN** build selects `/envs/agent` with a valid explicit parent chain
- **THEN** the rendered Docker command SHALL use the private leaf-owned composed directory as its context
- **AND** SHALL use the nearest child-side Dockerfile materialized in that context
- **AND** SHALL include reviewed inputs only through the composed `docker-assets/` namespace

#### Scenario: Inheriting a parent Dockerfile
- **WHEN** the selected leaf has no Dockerfile and an explicit parent supplies the nearest regular Dockerfile
- **THEN** build SHALL use that parent Dockerfile and only its paired `.dockerignore`
- **AND** SHALL NOT require a root Dockerfile in the leaf

#### Scenario: Missing Dockerfile across the chain
- **WHEN** no project in the explicit chain contains a Dockerfile
- **THEN** build and full project validation SHALL fail with a path-specific CONFIG error before projection publication or Docker execution

#### Scenario: Non-build command without Dockerfile
- **WHEN** a non-build, non-validate command selects a valid project chain with no Dockerfile
- **THEN** that command SHALL NOT fail solely because Dockerfile is absent
