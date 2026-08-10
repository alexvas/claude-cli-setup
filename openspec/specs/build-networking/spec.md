# Capability: build-networking

## Purpose
Define how the project diagnoses host reachability for Docker-gateway host access and prepares rootless Docker overrides.

## Requirements

### Requirement: Provide reusable gateway networking services
Gateway diagnosis and rootless override behavior SHALL be implemented in a dedicated internal networking module with a reusable programmatic API. The constructor CLI facade SHALL consume this module rather than own or duplicate its networking logic. Image build orchestration and disabled or external-address runtime access SHALL NOT consume gateway diagnosis or persistence services.

#### Scenario: Reusing gateway diagnosis from the CLI
- **WHEN** `./docker/docker-constructor.py doctor` diagnoses explicitly enabled Docker-gateway host access
- **THEN** the facade SHALL call the dedicated networking module
- **AND** the module SHALL return structured diagnosis results without parsing CLI arguments or selecting process exit codes

#### Scenario: Testing networking independently
- **WHEN** gateway candidate selection, probing, or rootless override behavior is tested
- **THEN** tests SHALL import the dedicated networking module directly
- **AND** SHALL NOT require invoking the constructor CLI facade

### Requirement: Probe host reachability from Docker
The system SHALL test candidate host gateway mappings from inside a temporary container through the explicit `doctor` command only for Docker-gateway host-access mode.

#### Scenario: Running Docker-gateway diagnostics
- **WHEN** `./docker/docker-constructor.py doctor` runs with reviewed host access enabled in `docker-gateway` mode
- **THEN** it SHALL start a temporary HTTP probe server on the host
- **AND** SHALL detect whether Docker is running in rootless mode
- **AND** SHALL test candidate mappings for `host.docker.internal`
- **AND** SHALL report the probes and chosen address

#### Scenario: Avoiding gateway diagnostics for other policies
- **WHEN** reviewed host access is disabled or uses `external-address` mode
- **THEN** `doctor` SHALL NOT probe Docker gateway candidates
- **AND** SHALL NOT install a rootless override or replace the user-managed external address

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
The system SHALL be able to install a user-level Docker systemd override for explicitly enabled Docker-gateway host access through the constructor facade.

#### Scenario: Applying the override through the unified command
- **WHEN** the user explicitly requests rootless override application through `docker-constructor.py doctor` in Docker-gateway mode
- **THEN** the command SHALL copy `docker/rootless-docker.override.conf` to `~/.config/systemd/user/docker.service.d/override.conf`
- **AND** SHALL reload the user systemd daemon
- **AND** SHALL restart `docker.service`
- **AND** SHALL rerun diagnostics

#### Scenario: Applying the override through the helper script
- **WHEN** `docker/apply-rootless-port-forward.sh` is executed for enabled Docker-gateway access
- **THEN** it SHALL install the same override file
- **AND** SHALL restart rootless Docker
- **AND** SHALL invoke the constructor facade's `doctor` command

### Requirement: Persist diagnosed gateway in local TOML state
A successful Docker-gateway diagnosis SHALL atomically persist its selected address in the local TOML companion without modifying the reviewed inventory or unrelated recognized local settings.

#### Scenario: Saving a successful diagnosis
- **WHEN** `doctor` selects a working Docker-gateway address
- **THEN** it SHALL atomically write that address to `[host-access].address` in the resolved local companion
- **AND** SHALL preserve other recognized local settings
- **AND** SHALL NOT modify `docker-constructor.toml` or `.env`

#### Scenario: Preserving prior state after failure
- **WHEN** diagnosis, repair, or persistence fails before a new address is safely published
- **THEN** any prior local companion SHALL remain intact
- **AND** `doctor` SHALL report an operational failure
