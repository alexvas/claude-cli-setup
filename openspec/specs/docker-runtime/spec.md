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
The runtime image SHALL expose Pi, OpenSpec, Rust/Cargo tools, uv, ty, rtk, and fd on the existing runtime `PATH` after their build stages or installation prefixes are isolated. The Rust toolchain SHALL use rustup's minimal profile and SHALL explicitly include the stable-toolchain `rustfmt` and `clippy` components. `rtk` and `fd` SHALL be supplied by verified pinned prebuilt release artifacts, and `rtk` integration setup SHALL remain available.

#### Scenario: Running isolated tools in the final image
- **WHEN** the final runtime container is started as user `dev`
- **THEN** `pi`, `openspec`, `cargo`, `rustc`, `rustfmt`, `uv`, `ty`, `rtk`, and `fd` SHALL resolve from `PATH`
- **AND** each required command SHALL execute without requiring build-stage cache mounts
- **AND** `cargo clippy --version` SHALL succeed

#### Scenario: Verifying the minimal Rust profile
- **WHEN** the runtime verification script checks the Rust installation
- **THEN** the active stable toolchain SHALL be available through rustup
- **AND** `rustfmt` SHALL be installed as an explicit component
- **AND** `clippy` SHALL be installed as an explicit component
- **AND** the verification SHALL fail with an actionable error if either component is unavailable

#### Scenario: Running prebuilt Rust tools
- **WHEN** the final runtime container is started as user `dev`
- **THEN** `rtk --version` and `fd --version` SHALL report the pinned release versions

#### Scenario: Configuring rtk integration
- **WHEN** the prebuilt `rtk` executable is assembled into the image
- **THEN** the existing `rtk init -g --agent pi` integration SHALL be applied
- **AND** telemetry SHALL remain disabled
- **AND** generated integration files SHALL be owned by `dev`

#### Scenario: Runtime network isolation
- **WHEN** the final runtime stage is assembled
- **THEN** it SHALL copy the verified `rtk` and `fd` executables from artifact stages
- **AND** SHALL NOT download or install either release from the network

### Requirement: Run as a configurable dev user
The system SHALL create and use a `dev` user whose UID and GID can be aligned with the host.

#### Scenario: Preparing the dev user during image build
- **WHEN** `docker/setup-dev-user.sh` runs with `DEV_UID` and `DEV_GID`
- **THEN** it ensures group `dev` exists with the requested GID
- **AND** ensures user `dev` exists with the requested UID, home directory `/home/dev`, and shell `zsh` when available

### Requirement: Mount host projects 1:1
The system SHALL run the container against host project directories without remapping their paths.

#### Scenario: Launching the base compose service
- **WHEN** `docker run` starts service `pi`
- **THEN** `PROJECT_PATH_1` is required
- **AND** the service working directory is set to `PROJECT_PATH_1`
- **AND** the same absolute host path is bind-mounted into the same absolute path inside the container

#### Scenario: Adding optional extra projects
- **WHEN** additional projects are selected through `--project` flags
- **THEN** `PROJECT_PATH_2` and `PROJECT_PATH_3` are mounted 1:1 through direct Docker bind-mount arguments with consecutive numbering

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

#### Scenario: Providing the protected extension setup script
- **WHEN** the runtime image is assembled
- **THEN** it SHALL copy `docker/install-pi-extensions.sh` to `/home/dev/install-pi-extensions.sh`
- **AND** the file SHALL be owned by `root:root`
- **AND** user `dev` SHALL have read and execute permission
- **AND** user `dev` SHALL not have write permission

#### Scenario: Installing supported extensions after mounting the Pi home
- **WHEN** `/home/dev/.pi` is mounted and user `dev` runs the protected setup script
- **THEN** the script SHALL install or register `@llblab/pi-codex-usage`, `pi-proxy`, and the pinned `@arcanemachine/pi-read` npm package
- **AND** each npm-installed extension SHALL use an explicit version
- **AND** the setup SHALL target the mounted Pi home rather than an image-layer directory

#### Scenario: Registering rtk integration
- **WHEN** user `dev` runs the protected setup script with the Pi home mounted
- **THEN** it SHALL apply `rtk init -g --agent pi`
- **AND** SHALL disable rtk telemetry
- **AND** repeated execution SHALL not duplicate configuration

#### Scenario: Rejecting an unavailable Pi home
- **WHEN** the setup script is run without the expected mounted Pi home
- **THEN** it SHALL fail with an actionable error
- **AND** SHALL not install extensions into the image-provided `/home/dev/.pi`

### Requirement: Present a consistent Pi container interface
The project SHALL identify the developer container, constructor CLI, and supported documentation as Pi-oriented interfaces.

#### Scenario: Following documented build instructions
- **WHEN** a user follows a build command from any maintained README translation
- **THEN** the command SHALL target the Pi container
- **AND** the image SHALL be tagged consistently with the project naming convention

#### Scenario: Following documented run instructions
- **WHEN** a user follows a run or CLI verification command from any maintained README translation
- **THEN** it SHALL invoke the Pi container and the `pi` CLI rather than the retired Claude service or CLI

### Requirement: Document the current runtime image
The Russian, English, and Chinese README files SHALL present the current Docker development environment around the primary user workflows of building the image, launching it with interactive project selection, updating managed components, and performing occasional maintenance. Internal implementation invariants and image-development diagnostics SHALL NOT interrupt those primary workflows.

#### Scenario: Comparing translated documentation
- **WHEN** the maintained README translations are reviewed
- **THEN** their supported commands, workflow order, component taxonomy, update process, and maintenance guidance SHALL be equivalent
- **AND** references to removed files, services, build targets, and proxy bootstrap behavior SHALL be absent

#### Scenario: Following the primary workflow structure
- **WHEN** a user opens a maintained README
- **THEN** build, interactive launch, and component update SHALL appear as the three primary actions
- **AND** a separate general setup section SHALL NOT be required before understanding those actions
- **AND** detailed Dockerfile/cache-development notes, BuildKit cache experiments, shell-prompt internals, Python implementation details, and Python override examples SHALL NOT appear in the primary user flow

#### Scenario: Selecting projects interactively
- **WHEN** a user follows the launch instructions
- **THEN** documentation SHALL use the executable launcher entry point
- **AND** SHALL explain main-project working-directory selection, optional additional 1:1 mounts, and the mounted Pi home

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
- **AND** SHALL omit obsolete-name, missing-extra-project, and ordinary host-gateway guidance from the primary troubleshooting list

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

### Requirement: Verify tools against the effective inventory
The runtime image SHALL expose a root-owned read-only effective version inventory, and runtime verification SHALL compare installed tools and extensions with those effective values.

#### Scenario: Verifying configured runtime tools
- **WHEN** the runtime smoke check runs as `dev`
- **THEN** it SHALL verify Node, Rust/Cargo, rustfmt/clippy, uv, Python, ty, Pi, OpenSpec, rtk, and fd against the effective inventory
- **AND** SHALL report actionable version mismatches

#### Scenario: Verifying configured Pi extensions
- **WHEN** the protected Pi extension setup script installs extensions into the mounted Pi home
- **THEN** it SHALL obtain package identity from each entry's npm source metadata and its version from the same effective inventory entry
- **AND** runtime extension verification SHALL compare installed package metadata with those values
- **AND** neither the runtime entry nor the setup script SHALL duplicate the npm package identity

### Requirement: Preserve direct stable Python selection
The effective inventory and runtime SHALL preserve the direct uv-managed Python contract: the default version SHALL be exactly `3.14.6`; supported overrides SHALL be stable numeric `X.Y.Z` values at or above `3.14.6`; and no standalone pip interface SHALL be exposed.

#### Scenario: Verifying direct Python executables
- **WHEN** runtime verification checks `python` and `python3`
- **THEN** both SHALL resolve directly to the effective uv-managed CPython interpreter
- **AND** SHALL NOT resolve through `uv run`, project-aware wrappers, or shell aliases

#### Scenario: Rejecting an unsupported Python selector
- **WHEN** the effective configuration contains a prerelease, non-numeric selector, or version older than `3.14.6`
- **THEN** validation SHALL fail before the Docker build starts

### Requirement: Require project selection only for runtime launch
Project paths and 1:1 bind mounts SHALL be runtime launch inputs rather than image-build prerequisites.

#### Scenario: Launching with an interactively selected project
- **WHEN** the launcher starts a runtime container after the user selects a main project
- **THEN** it SHALL configure that project as `PROJECT_PATH_1`, the working directory, and a 1:1 bind mount
- **AND** additional selected projects SHALL remain optional runtime mounts

#### Scenario: Running without a selected main project
- **WHEN** a runtime run operation is requested without `PROJECT_PATH_1` or an equivalent launcher selection
- **THEN** runtime configuration SHALL fail with an actionable project-selection error
- **AND** the build-only configuration SHALL remain unaffected
