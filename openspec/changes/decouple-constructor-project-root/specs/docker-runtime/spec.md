## REMOVED Requirements

### Requirement: Mount host projects 1:1
**Reason**: Runtime source directories are now workspaces so they cannot be confused with the constructor project directory.

**Migration**: Use `--workspace`/`-w`, repeatable `--extra-workspace`, and `WORKSPACE_PATH_1..N`.

### Requirement: Require project selection only for runtime launch
**Reason**: The behavior is retained under workspace terminology.

**Migration**: Use the replacement “Require workspace selection only for runtime launch” requirement.

## ADDED Requirements

### Requirement: Mount host workspaces 1:1
The system SHALL run the container directly against host workspace directories without remapping their paths or using Compose fragments. Public CLI, domain, TUI, rendering, diagnostics, verification, tests, and maintained documentation SHALL use primary/extra workspace terminology and SHALL NOT retain main/additional project aliases.

#### Scenario: Launching with a primary workspace
- **WHEN** `docker-constructor run --workspace PATH` starts the Pi image through `docker run`
- **THEN** `WORKSPACE_PATH_1` SHALL identify the selected primary workspace
- **AND** the container working directory SHALL be set to `WORKSPACE_PATH_1`
- **AND** the same absolute host path SHALL be bind-mounted into the same absolute path inside the container

#### Scenario: Adding extra workspaces
- **WHEN** the user repeats `--extra-workspace PATH`
- **THEN** each selected path SHALL be added as a separate 1:1 bind mount
- **AND** corresponding consecutive `WORKSPACE_PATH_2..N` environment values SHALL be passed to the container

#### Scenario: Rejecting duplicate workspaces
- **WHEN** normalized primary and extra workspace selections contain the same path more than once
- **THEN** runtime configuration SHALL fail with an actionable workspace-selection error
- **AND** SHALL NOT silently promote, discard, or renumber a duplicate

### Requirement: Require workspace selection only for runtime launch
Workspace paths and 1:1 bind mounts SHALL be runtime launch inputs rather than image-build prerequisites.

#### Scenario: Launching with an interactively selected workspace
- **WHEN** the launcher starts a runtime container after the user selects a primary workspace
- **THEN** it SHALL configure that workspace as `WORKSPACE_PATH_1`, the working directory, and a 1:1 bind mount
- **AND** extra selected workspaces SHALL remain optional runtime mounts

#### Scenario: Running without a selected primary workspace
- **WHEN** a runtime run operation is requested without `WORKSPACE_PATH_1` or an equivalent launcher selection
- **THEN** runtime configuration SHALL fail with an actionable workspace-selection error
- **AND** build-only configuration SHALL remain unaffected

## MODIFIED Requirements

### Requirement: Repair mount ownership on startup
The system SHALL be able to fix ownership and access permissions of mounted workspace worktrees before dropping privileges. The runtime SHALL explicitly install `util-linux` to provide `mountpoint`. The launcher interface SHALL define `WORKSPACE_PATH_*` as host-directory bind mounts. `CHOWN_WORK_ON_START` repair SHALL consider only configured `WORKSPACE_PATH_*` paths, SHALL require each target to be a container mount point (`mountpoint -q`), and SHALL NOT scan or modify ordinary image-layer directories, fixed runtime home paths, or non-workspace mounts.

#### Scenario: CHOWN_WORK_ON_START enabled with mounted workspace paths
- **WHEN** the container starts as root with `CHOWN_WORK_ON_START` set to `1` or `true`
- **THEN** the entrypoint SHALL inspect each configured `WORKSPACE_PATH_*` variable
- **AND** SHALL repair a target only when `mountpoint -q` confirms it is a container mount point
- **AND** for each repaired workspace mount SHALL recursively change ownership only for files and directories not owned by `dev:dev`
- **AND** for each repaired workspace mount SHALL grant user and group read/write access to files and read/write/traversal access to directories
- **AND** SHALL preserve executable-file intent rather than making every regular file executable
- **AND** the recursive scans SHALL NOT follow symbolic links
- **AND** repaired workspace paths SHALL be marked as global Git safe directories for user `dev`
- **AND** the entrypoint SHALL finally execute the requested command as `dev`

#### Scenario: Non-workspace home path is mounted
- **WHEN** `CHOWN_WORK_ON_START` is enabled and `/home/dev/.pi`, `/home/dev/.cargo`, `/home/dev/.npm`, `/home/dev/.npm-global`, or another non-`WORKSPACE_PATH_*` path is mounted
- **THEN** the entrypoint SHALL NOT traverse, repair, or register that mounted path

#### Scenario: Configured workspace path is not a mount point
- **WHEN** `CHOWN_WORK_ON_START` is enabled and a configured `WORKSPACE_PATH_*` exists but `mountpoint -q` fails
- **THEN** the entrypoint SHALL skip ownership repair, permission repair, and safe-directory registration for that path
- **AND** SHALL NOT traverse or modify its contents

#### Scenario: Mount detection is unavailable
- **WHEN** `CHOWN_WORK_ON_START` is enabled but the `mountpoint` command is unavailable
- **THEN** the entrypoint SHALL print an actionable error
- **AND** SHALL exit unsuccessfully before executing the requested command

#### Scenario: CHOWN_WORK_ON_START disabled
- **WHEN** `CHOWN_WORK_ON_START` is neither `1` nor `true`
- **THEN** the entrypoint SHALL perform no ownership or access-permission repair
- **AND** SHALL still execute the requested command as `dev`

### Requirement: Preserve image-provided home ownership without whole-home rewrites
The runtime image SHALL assemble image-provided artifacts under `/home/dev` with ownership matching the configured `dev` user and group. Runtime assembly SHALL NOT recursively change ownership of the complete `/home/dev` tree.

#### Scenario: Assembling runtime home artifacts
- **WHEN** the runtime stage copies Pi, uv/Python, Rust, Cargo binaries, and MCP artifacts from build stages
- **THEN** the copied artifacts SHALL be owned by the runtime `dev` user and group
- **AND** newly created runtime directories SHALL be created with targeted `dev:dev` ownership
- **AND** assembly SHALL NOT execute `chown -R` over `/home/dev`

#### Scenario: Building with custom dev identity
- **WHEN** the image is built with non-default `DEV_UID` and `DEV_GID` values
- **THEN** image-provided paths under `/home/dev` SHALL resolve to the configured runtime `dev` user and group

#### Scenario: Starting with host workspace bind mounts
- **WHEN** the runtime container starts with workspace worktrees mounted from host directories at configured `WORKSPACE_PATH_*` paths
- **THEN** the entrypoint ownership and access repair policy SHALL remain available for those workspace bind mounts
- **AND** removal of build-time whole-home chown SHALL NOT weaken workspace-mount repair

### Requirement: Document the current runtime image
The Russian, English, and Chinese README files SHALL present the current Docker development environment around the primary user workflows of building the image, launching it with interactive workspace selection, updating managed components, and performing occasional maintenance. Internal implementation invariants and image-development diagnostics SHALL NOT interrupt those primary workflows.

#### Scenario: Comparing translated documentation
- **WHEN** the maintained README translations are reviewed
- **THEN** their supported commands, workflow order, component taxonomy, update process, and maintenance guidance SHALL be equivalent
- **AND** references to removed files, options, environment variables, services, build targets, and proxy bootstrap behavior SHALL be absent

#### Scenario: Following the primary workflow structure
- **WHEN** a user opens a maintained README
- **THEN** build, interactive launch, and component update SHALL appear as the three primary actions
- **AND** a separate general setup section SHALL NOT be required before understanding those actions
- **AND** detailed Dockerfile/cache-development notes, BuildKit cache experiments, shell-prompt internals, Python implementation details, and Python override examples SHALL NOT appear in the primary user flow

#### Scenario: Selecting workspaces interactively
- **WHEN** a user follows the launch instructions
- **THEN** documentation SHALL use the executable launcher entry point
- **AND** SHALL explain primary-workspace working-directory selection, optional extra 1:1 mounts, and the mounted Pi home

#### Scenario: Maintaining host state
- **WHEN** a user consults maintenance guidance
- **THEN** image verification, mounted extension refresh, host permission repair, Docker storage cleanup, and user-facing cache cleanup SHALL be grouped under Maintenance
- **AND** permission repair SHALL use `<docker-dev>:<docker-dev>` placeholders and recursive `ug+rwX` semantics
- **AND** every translation SHALL identify `docker-dev` as the user/group typically mapped to host UID/GID `100999` by rootless Docker
- **AND** every translation SHALL show how to add the host user to the `docker-dev` group
- **AND** documentation SHALL warn users to choose the intended host owner before changing shared worktrees

#### Scenario: Troubleshooting current failures
- **WHEN** a user reads troubleshooting guidance
- **THEN** it SHALL focus on actionable current failures such as host EACCES
- **AND** SHALL omit obsolete-name, missing-extra-workspace, and ordinary host-gateway guidance from the primary troubleshooting list
