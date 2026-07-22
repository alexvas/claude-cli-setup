# Capability: docker-runtime

## Purpose
Define the current Docker image, compose service, and container startup behavior for the π environment.

## Requirements

### Requirement: Build a developer runtime image
The system SHALL provide a multi-stage Docker image for running π inside an isolated container.

#### Scenario: Builder stage installs developer tooling
- **WHEN** the image is built
- **THEN** the builder stage uses `node:24-trixie-slim`
- **AND** installs developer tooling including git, vim, curl, jq, ripgrep, build-essential, Rust, uv, ty, pi, rtk, and fd
- **AND** bootstraps the MCP Yarn workspace under `/home/dev/mcp`

#### Scenario: Runtime stage includes interactive shell environment
- **WHEN** the runtime stage is built
- **THEN** it uses `node:24-trixie-slim`
- **AND** installs runtime tools including git, vim, less, bat, jq, ripgrep, openssh-client, gh, rpm, gosu, socat, bash, and zsh
- **AND** configures locale `ru_RU.UTF-8`
- **AND** exposes `pi` on the runtime `PATH`

### Requirement: Provide Python through uv
The system SHALL install an explicit uv-managed CPython runtime whose configured version is 3.14.6 or newer, with exactly 3.14.6 as the default build input. The runtime SHALL expose direct `python` and `python3` executables and SHALL NOT implement either command through `uv run`, a project-aware wrapper, or a shell alias. The system SHALL NOT advertise or create a standalone `pip` command or alias; package operations SHALL be documented through explicit `uv pip` subcommands.

#### Scenario: Running python3 in the container
- **WHEN** a user invokes `python3` from any working directory
- **THEN** the configured uv-managed CPython interpreter executes directly
- **AND** invocation SHALL NOT discover or synchronize a project environment through `uv run`
- **AND** the interpreter version SHALL be 3.14.6 or newer

#### Scenario: Building with the default Python version
- **WHEN** the image is built without a Python version override
- **THEN** the image SHALL install exactly CPython 3.14.6
- **AND** build-time verification SHALL confirm the installed version and executable path

#### Scenario: Building with a supported Python override
- **WHEN** the image is built with an available Python version override equal to or newer than 3.14.6
- **THEN** the image SHALL install and expose the requested version
- **AND** Python-backed uv tool installation SHALL use that configured Python selection explicitly

#### Scenario: Building with an unsupported older Python override
- **WHEN** the image is built with a Python version override older than 3.14.6
- **THEN** the build SHALL fail with a clear version-requirement error

#### Scenario: Installing Python packages
- **WHEN** documentation instructs a user to perform a Python package operation
- **THEN** it SHALL use an explicit `uv pip` subcommand and target context
- **AND** it SHALL NOT rely on a `pip` or `pip3` alias supplied by the image

### Requirement: Reuse shared operating-system setup across image stages
The multi-stage Docker image SHALL derive builder and runtime assembly from a shared base stage for their common operating-system packages and user setup, while builder-only packages SHALL remain outside the final runtime lineage when they are not runtime requirements.

#### Scenario: Building builder and runtime descendants
- **WHEN** Docker builds the tool builder and runtime image
- **THEN** common Debian package and dev-user setup SHALL originate from the same cached base layers
- **AND** common package installation SHALL NOT execute independently in both descendants

### Requirement: Preserve the runtime interface after tool isolation
The runtime image SHALL expose Pi, OpenSpec, Rust/Cargo tools, uv, ty, rtk, and fd on the existing runtime `PATH` after their build stages or installation prefixes are isolated.

#### Scenario: Running isolated tools in the final image
- **WHEN** the final runtime container is started as user `dev`
- **THEN** `pi`, `openspec`, `cargo`, `uv`, `ty`, `rtk`, and `fd` SHALL resolve from `PATH`
- **AND** each command SHALL execute without requiring its build-stage cache mounts

### Requirement: Run as a configurable dev user
The system SHALL create and use a `dev` user whose UID and GID can be aligned with the host.

#### Scenario: Preparing the dev user during image build
- **WHEN** `docker/setup-dev-user.sh` runs with `DEV_UID` and `DEV_GID`
- **THEN** it ensures group `dev` exists with the requested GID
- **AND** ensures user `dev` exists with the requested UID, home directory `/home/dev`, and shell `zsh` when available

### Requirement: Mount host projects 1:1
The system SHALL run the container against host project directories without remapping their paths.

#### Scenario: Launching the base compose service
- **WHEN** `docker compose run` starts service `pi`
- **THEN** `PROJECT_PATH_1` is required
- **AND** the service working directory is set to `PROJECT_PATH_1`
- **AND** the same absolute host path is bind-mounted into the same absolute path inside the container

#### Scenario: Adding optional extra projects
- **WHEN** compose fragments `docker/compose.proj2.yml` and `docker/compose.proj3.yml` are included
- **THEN** `PROJECT_PATH_2` and `PROJECT_PATH_3` are mounted 1:1 in the container

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

### Requirement: Configure an interactive zsh environment
The system SHALL install a pinned oh-my-zsh setup for the `dev` user.

#### Scenario: Setting up zsh
- **WHEN** `docker/setup-zsh.sh` runs
- **THEN** it clones oh-my-zsh at the configured pinned git ref
- **AND** writes a minimal `.zshrc` with the `git` plugin enabled
- **AND** loads only the Pi prompt fragment from `.pi-zsh-prompt`

#### Scenario: Only an obsolete prompt customization exists
- **WHEN** an obsolete prompt customization exists but `.pi-zsh-prompt` does not
- **THEN** zsh setup SHALL not load the obsolete customization

### Requirement: Include bundled π skills and extensions
The system SHALL make bundled π assets available in the runtime home directory.

#### Scenario: Copying user assets from the builder stage
- **WHEN** the runtime image is assembled
- **THEN** it copies `/home/dev/.pi`, `/home/dev/.local`, `/home/dev/.rustup`, `/home/dev/.cargo/bin`, and `/home/dev/mcp` from the builder stage
- **AND** installs the `pi-read` package for user `dev`

### Requirement: Present a consistent Pi container interface
The project SHALL identify the developer container, Compose service, wrapper commands, launcher commands, and supported documentation as Pi-oriented interfaces.

#### Scenario: Following documented build instructions
- **WHEN** a user follows a build command from any maintained README translation
- **THEN** the command SHALL target Compose service `pi`
- **AND** the service SHALL exist in the evaluated Compose configuration

#### Scenario: Following documented run instructions
- **WHEN** a user follows a run or CLI verification command from any maintained README translation
- **THEN** it SHALL invoke service `pi` and the `pi` CLI rather than the retired Claude service or CLI

### Requirement: Document the current runtime image
The Russian, English, and Chinese README files SHALL describe the tools, environment variables, project mounts, launcher, build process, and troubleshooting behavior implemented by the current Dockerfile and Compose configuration.

#### Scenario: Comparing translated documentation
- **WHEN** the maintained README translations are reviewed
- **THEN** their supported commands and configuration concepts SHALL be equivalent
- **AND** references to removed files, services, build targets, and proxy bootstrap behavior SHALL be absent

### Requirement: Use the Pi prompt path exclusively
The shell setup SHALL use `/home/dev/.pi-zsh-prompt` as the only project-owned prompt configuration path.

#### Scenario: Pi prompt customization exists
- **WHEN** the dev home contains `/home/dev/.pi-zsh-prompt`
- **THEN** zsh SHALL load that prompt fragment

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
