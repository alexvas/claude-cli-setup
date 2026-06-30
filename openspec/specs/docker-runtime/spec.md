# Capability: docker-runtime

## Purpose
Define the current Docker image, compose service, and container startup behavior for the π environment.

## Requirements

### Requirement: Build a developer runtime image
The system SHALL provide a multi-stage Docker image for running π inside an isolated container.

#### Scenario: Builder stage installs developer tooling
- **WHEN** the image is built
- **THEN** the builder stage uses `node:24-bookworm-slim`
- **AND** installs developer tooling including git, vim, curl, jq, ripgrep, build-essential, Rust, uv, ty, pi, rtk, and fd
- **AND** bootstraps the MCP Yarn workspace under `/home/dev/mcp`

#### Scenario: Runtime stage includes interactive shell environment
- **WHEN** the runtime stage is built
- **THEN** it uses `node:24-bookworm-slim`
- **AND** installs runtime tools including git, vim, less, bat, jq, ripgrep, openssh-client, gh, rpm, gosu, socat, bash, and zsh
- **AND** configures locale `ru_RU.UTF-8`
- **AND** exposes `pi` on the runtime `PATH`

### Requirement: Provide Python through uv
The system SHALL expose Python tooling through `uv` instead of an apt-installed `python3` package.

#### Scenario: Running python3 in the container
- **WHEN** a user invokes `python3`
- **THEN** the command executes `uv run python`
- **AND** shell aliases provide `python3='uv run python'` and `pip='uv pip --system'`

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
The system SHALL be able to fix ownership of mounted work directories before dropping privileges.

#### Scenario: CHOWN_WORK_ON_START enabled
- **WHEN** the container starts as root and `CHOWN_WORK_ON_START` is `1` or `true`
- **THEN** the entrypoint recursively `chown`s each configured `PROJECT_PATH_*` directory to `dev:dev`
- **AND** marks each mounted git directory as a global safe directory for user `dev`
- **AND** `chown`s `/home/dev/.pi`, `/home/dev/.cargo`, `/home/dev/.npm`, and `/home/dev/.npm-global`
- **AND** finally executes the requested command as `dev`

### Requirement: Configure an interactive zsh environment
The system SHALL install a pinned oh-my-zsh setup for the `dev` user.

#### Scenario: Setting up zsh
- **WHEN** `docker/setup-zsh.sh` runs
- **THEN** it clones oh-my-zsh at the configured pinned git ref
- **AND** writes a minimal `.zshrc` with the `git` plugin enabled
- **AND** loads a custom prompt fragment from `.claude-cli-zsh-prompt`

### Requirement: Include bundled π skills and extensions
The system SHALL make bundled π assets available in the runtime home directory.

#### Scenario: Copying user assets from the builder stage
- **WHEN** the runtime image is assembled
- **THEN** it copies `/home/dev/.pi`, `/home/dev/.local`, `/home/dev/.rustup`, `/home/dev/.cargo/bin`, and `/home/dev/mcp` from the builder stage
- **AND** installs the `pi-read` package for user `dev`
