# Delta: Docker Build System

**Change ID:** `add-spec-from-project-code`
**Affects:** Dockerfile, docker/build_wrapper.py, docker/bootstrap-claude-build.sh, docker/entrypoint.sh

---

## ADDED

### Requirement: Multi-stage Docker Build

The image is built in two stages: builder (compiles tools, installs Claude) and runtime (minimal copy of artifacts). The builder stage has access to SOCKS proxy for downloading external tools. The runtime stage has no build proxy tooling.

#### Scenario: Build stage installs toolchains
- GIVEN SOCKS proxy is available on host at `0.0.0.0:${SOCKS_PORT}`
- AND build args include NODE_VERSION, YARN_VERSION, CLAUDE_TARGET, ASTRO_VERSION
- WHEN `docker compose build claude` runs
- THEN Node ${NODE_VERSION} is installed via install-node.sh
- THEN Yarn ${YARN_VERSION} is installed
- THEN Claude CLI is bootstrapped via claude-bootstrap.sh with target ${CLAUDE_TARGET}
- THEN Rust stable toolchain is installed via rustup
- THEN uv, ty, mcp-server-git, mcp-server-fetch, mcp-server-uv are installed via uv tool
- THEN Astro CLI ${ASTRO_VERSION} is installed globally via npm

#### Scenario: Runtime stage has minimal tooling
- GIVEN builder stage has completed successfully
- WHEN runtime image is assembled
- THEN runtime has: git, vim, less, bat, curl, wget, jq, ripgrep, locales (ru_RU.UTF-8), openssh-client, gh, socat, zsh, gosu
- THEN runtime does NOT have: privoxy, build-essential XZ headers, npm registry caches
- THEN runtime has NO SOCKS proxy configuration

#### Scenario: Python is provided via uv
- GIVEN runtime image is running
- WHEN `python3` is invoked
- THEN it executes `uv run python` (thin wrapper at /usr/local/bin/python3)
- WHEN `pip` is invoked
- THEN it executes `uv pip --system`

### Requirement: Dev User Setup

The container runs under user `dev` with UID/GID matching the host project owner.

#### Scenario: UID/GID alignment
- GIVEN DEV_UID and DEV_GID are set in .env (default 1000)
- WHEN the image is built
- THEN user `dev` is created with UID=${DEV_UID}, GID=${DEV_GID}
- THEN project bind-mounts are owned by dev:dev inside the container

### Requirement: Build Wrapper for Rootless Docker

Rootless Docker requires special handling: the host gateway IP is discovered via ephemeral HTTP probe, and port forwarding rules may need to be applied.

#### Scenario: Rootful build
- GIVEN Docker is running in rootful mode
- WHEN `docker compose build claude` is called directly
- THEN `host-gateway` resolves correctly and the build succeeds

#### Scenario: Rootless build with wrapper
- GIVEN Docker is running in rootless mode
- WHEN `docker/build_wrapper.py build` is called
- THEN the wrapper probes for the host gateway IP via ephemeral HTTP
- THEN sets HOST_GATEWAY_IP in .env
- THEN builds the image with correct extra_hosts pointing to host gateway
- THEN if port forwarding is needed, suggests applying apply-rootless-port-forward.sh

### Requirement: Container Entrypoint

The entrypoint runs as root, optionally chowns the working directory, then drops privileges to dev.

#### Scenario: CHOWN_WORK_ON_START enabled (default)
- GIVEN `CHOWN_WORK_ON_START=1` (default)
- AND the bind-mounted project directory is owned by root
- WHEN container starts
- THEN entrypoint.sh changes ownership of working dir to dev:dev
- THEN drops to user dev via gosu

#### Scenario: CHOWN_WORK_ON_START disabled
- GIVEN `CHOWN_WORK_ON_START=0`
- WHEN container starts
- THEN entrypoint.sh skips chown
- THEN drops to user dev via gosu

---

## REMOVED

(None)
