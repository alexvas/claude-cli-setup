# Delta: Container Runtime

**Change ID:** `add-spec-from-project-code`
**Affects:** docker-compose.yml, docker/compose.proj2.yml, docker/compose.proj3.yml, .env

---

## ADDED

### Requirement: Service Definition

A single service `claude` is defined with build-time args, volume mounts, and environment variables from `.env`.

#### Scenario: Single project mount
- GIVEN `PROJECT_PATH_1=/home/user/my-project` in .env
- AND `COMPOSE_FILE=docker-compose.yml`
- WHEN container starts
- THEN `/home/user/my-project` is bind-mounted 1:1 inside the container
- THEN working_dir is set to `${PROJECT_PATH_1}`

#### Scenario: Two projects
- GIVEN `COMPOSE_FILE=docker-compose.yml:docker/compose.proj2.yml` in .env
- AND `PROJECT_PATH_1` and `PROJECT_PATH_2` are set
- WHEN container starts
- THEN both paths are bind-mounted 1:1 inside the container

#### Scenario: Three projects
- GIVEN `COMPOSE_FILE=docker-compose.yml:docker/compose.proj2.yml:docker/compose.proj3.yml` in .env
- AND `PROJECT_PATH_1`, `PROJECT_PATH_2`, `PROJECT_PATH_3` are set
- WHEN container starts
- THEN all three paths are bind-mounted 1:1 inside the container

### Requirement: Anthropic API Routing

The container routes Anthropic API calls to a local proxy on the host.

#### Scenario: API routing to host proxy
- GIVEN `ANTHROPIC_BASE_URL=http://host.docker.internal:${PROXY_PORT}` (default 3000)
- AND `ANTHROPIC_AUTH_TOKEN=dummy`
- WHEN Claude CLI makes an API call
- THEN the request goes to the proxy on the host at the configured port

### Requirement: Model Configuration

Default models for all tiers are configurable via environment.

#### Scenario: Model env vars
- GIVEN `ANTHROPIC_MODEL=deepseek-v4-pro[1m]`
- AND `ANTHROPIC_DEFAULT_OPUS_MODEL=deepseek-v4-pro[1m]`
- AND `ANTHROPIC_DEFAULT_SONNET_MODEL=deepseek-v4-pro[1m]`
- AND `ANTHROPIC_DEFAULT_HAIKU_MODEL=local-model`
- AND `CLAUDE_CODE_SUBAGENT_MODEL=local-model`
- WHEN Claude CLI is invoked
- THEN it uses the configured models for main queries and subagents

### Requirement: Home Directory Mount

The host `.claude` directory is mounted into the container for persistence.

#### Scenario: Persistent Claude config
- GIVEN `~/.claude` exists on the host
- WHEN container starts
- THEN `/home/dev/.claude` is bind-mounted from `${HOME}/.claude`
- THEN IDE lock files, settings, and history persist across container restarts

### Requirement: Host Gateway Resolution

The container can reach the host via `host.docker.internal`.

#### Scenario: Rootful Docker
- GIVEN Docker is rootful
- AND `HOST_GATEWAY_IP` is not set in .env
- WHEN compose processes `extra_hosts`
- THEN `host.docker.internal` resolves to `host-gateway` (Docker's default)

#### Scenario: Rootless Docker
- GIVEN Docker is rootless
- AND `HOST_GATEWAY_IP` is set to `10.0.2.2` in .env
- WHEN compose processes `extra_hosts`
- THEN `host.docker.internal` resolves to `10.0.2.2`

---

## REMOVED

(None)
