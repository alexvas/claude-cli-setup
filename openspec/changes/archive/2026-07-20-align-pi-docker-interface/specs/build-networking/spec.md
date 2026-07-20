## MODIFIED Requirements

### Requirement: Persist detected host gateway configuration before build
The system SHALL write the chosen host gateway IP to `.env` before building the Pi service.

#### Scenario: Running the build wrapper
- **WHEN** `python3 docker/build_wrapper.py build` succeeds in probing host reachability
- **THEN** it updates `.env` with `HOST_GATEWAY_IP=<detected-ip>`
- **AND** removes obsolete `SOCKS_HOST` from `.env` if present
- **AND** runs `docker compose build pi`

### Requirement: Expose host mapping in compose
The system SHALL inject a host mapping for the runtime service without passing unused host-proxy build arguments.

#### Scenario: Starting compose service `pi`
- **WHEN** `docker-compose.yml` is evaluated
- **THEN** service `pi` sets extra-hosts entry `host.docker.internal:${HOST_GATEWAY_IP:-host-gateway}`
- **AND** the build configuration SHALL NOT pass unused `SOCKS_PORT`, `HOST_GATEWAY_IP`, `SOCKS_HOST`, or `EXTERNAL_IP` arguments to the Dockerfile
