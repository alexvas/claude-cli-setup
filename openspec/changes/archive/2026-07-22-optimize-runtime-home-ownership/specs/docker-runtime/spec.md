## ADDED Requirements

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

#### Scenario: Starting with host project bind mounts
- **WHEN** the runtime container starts with project worktrees mounted from host directories at configured `PROJECT_PATH_*` paths
- **THEN** the entrypoint ownership and access repair policy SHALL remain available for those project bind mounts
- **AND** removal of build-time whole-home chown SHALL NOT weaken project-mount repair

### Requirement: Verify image-provided runtime home ownership
The runtime smoke check SHALL inspect required image-provided paths under `/home/dev` and SHALL fail when any inspected entry is not owned by `dev:dev`. Verification SHALL be read-only and SHALL NOT follow symbolic links.

#### Scenario: Runtime ownership is correct
- **WHEN** `docker/verify-runtime.sh` checks a built image without host volumes
- **THEN** it SHALL inspect required Pi, uv/Python, Rust/Cargo, MCP, work, and npm paths
- **AND** SHALL run with startup ownership repair disabled
- **AND** SHALL succeed when every inspected entry is owned by `dev:dev`

#### Scenario: Runtime ownership mismatch is present
- **WHEN** an inspected image-provided path contains an entry not owned by `dev:dev`
- **THEN** `docker/verify-runtime.sh` SHALL print an actionable mismatch identifying the path
- **AND** SHALL exit unsuccessfully without changing ownership

## MODIFIED Requirements

### Requirement: Repair mount ownership on startup
The system SHALL be able to fix ownership and access permissions of mounted project worktrees before dropping privileges. The runtime SHALL explicitly install `util-linux` to provide `mountpoint`. The supported Compose and launcher interfaces SHALL define `PROJECT_PATH_*` as host-directory bind mounts. `CHOWN_WORK_ON_START` repair SHALL consider only configured `PROJECT_PATH_*` paths, SHALL require each target to be a container mount point (`mountpoint -q`), and SHALL NOT scan or modify ordinary image-layer directories, fixed runtime home paths, or non-project mounts.

#### Scenario: CHOWN_WORK_ON_START enabled with mounted project paths
- **WHEN** the container starts as root with `CHOWN_WORK_ON_START` set to `1` or `true`
- **THEN** the entrypoint SHALL inspect each configured `PROJECT_PATH_*` variable
- **AND** SHALL repair a target only when `mountpoint -q` confirms it's a container mount point
- **AND** for each repaired project mount SHALL recursively change ownership only for files and directories not owned by `dev:dev`
- **AND** for each repaired project mount SHALL grant user and group read/write access to files and read/write/traversal access to directories
- **AND** SHALL preserve executable-file intent rather than making every regular file executable
- **AND** the recursive scans SHALL NOT follow symbolic links
- **AND** repaired project paths SHALL be marked as global Git safe directories for user `dev`
- **AND** the entrypoint SHALL finally execute the requested command as `dev`

#### Scenario: Non-project home path is mounted
- **WHEN** `CHOWN_WORK_ON_START` is enabled and `/home/dev/.pi`, `/home/dev/.cargo`, `/home/dev/.npm`, `/home/dev/.npm-global`, or another non-`PROJECT_PATH_*` path is mounted
- **THEN** the entrypoint SHALL NOT traverse, repair, or register that mounted path

#### Scenario: Configured project path is not a mount point
- **WHEN** `CHOWN_WORK_ON_START` is enabled and a configured `PROJECT_PATH_*` exists but `mountpoint -q` fails
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
