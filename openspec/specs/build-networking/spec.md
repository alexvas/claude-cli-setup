# Capability: build-networking

## Purpose
Define how the project diagnoses host reachability and prepares Docker builds, especially for rootless Docker.

## Requirements

### Requirement: Probe host reachability from Docker
The system SHALL test candidate host gateway mappings from inside a temporary container.

#### Scenario: Running diagnostics
- **WHEN** `python3 docker/build_wrapper.py diagnose` is executed
- **THEN** the script starts a temporary HTTP probe server on the host
- **AND** detects whether Docker is running in rootless mode
- **AND** tests candidate mappings for `host.docker.internal`
- **AND** prints probe results and the chosen `HOST_GATEWAY_IP` when a working route is found

### Requirement: Use different gateway candidates for rootful and rootless Docker
The system SHALL probe different host gateway candidates depending on Docker mode.

#### Scenario: Rootful Docker
- **WHEN** Docker is not rootless
- **THEN** probing prefers `host-gateway`
- **AND** may also probe the detected LAN IP when available

#### Scenario: Rootless Docker
- **WHEN** Docker is rootless
- **THEN** probing prefers `10.0.2.2`
- **AND** may also probe the detected LAN IP
- **AND** also probes `host-gateway`

### Requirement: Install a rootless Docker override
The system SHALL be able to install a user-level Docker systemd override for rootless port forwarding.

#### Scenario: Applying the override through the wrapper
- **WHEN** `python3 docker/build_wrapper.py apply` is executed
- **THEN** the script copies `docker/rootless-docker.override.conf` to `~/.config/systemd/user/docker.service.d/override.conf`
- **AND** reloads the user systemd daemon
- **AND** restarts `docker.service`
- **AND** reruns diagnostics

#### Scenario: Applying the override through the helper script
- **WHEN** `docker/apply-rootless-port-forward.sh` is executed
- **THEN** it installs the same override file
- **AND** restarts rootless Docker
- **AND** runs `docker/build_wrapper.py diagnose`

### Requirement: Persist detected host gateway configuration before build
The system SHALL write the chosen host gateway IP to `.env` before building.

#### Scenario: Running the build wrapper
- **WHEN** `python3 docker/build_wrapper.py build` succeeds in probing host reachability
- **THEN** it updates `.env` with `HOST_GATEWAY_IP=<detected-ip>`
- **AND** removes `SOCKS_HOST` from `.env` if present
- **AND** runs `docker compose build claude`

### Requirement: Expose host mapping in compose
The system SHALL inject a host mapping for the runtime service.

#### Scenario: Starting compose service `pi`
- **WHEN** `docker-compose.yml` is evaluated
- **THEN** service `pi` sets `extra_hosts` entry `host.docker.internal:${HOST_GATEWAY_IP:-host-gateway}`
- **AND** build args pass through `SOCKS_PORT`, `HOST_GATEWAY_IP`, `SOCKS_HOST`, and `EXTERNAL_IP`

### Requirement: Generate model proxy configuration from inf-splitter TOML
The system SHALL generate a π models.json file from an inf-splitter configuration.

#### Scenario: Exporting models from TOML
- **WHEN** `docker/gen-models-json.py` runs against an `inf-splitter.toml` file
- **THEN** it reads TOML sections that define `endpoint_openai`
- **AND** collects all configured model ids except `default`
- **AND** writes `~/.pi/agent/models.json`
- **AND** configures a single `inf-splitter` provider using `http://${HOST_GATEWAY_IP:-127.0.0.1}:${PROXY_PORT:-3000}`
