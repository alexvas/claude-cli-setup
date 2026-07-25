## ADDED Requirements

### Requirement: Provide reusable gateway networking services
Gateway diagnosis and rootless override behavior SHALL be implemented in a dedicated internal networking module with a reusable programmatic API. The constructor CLI facade SHALL consume this module rather than own or duplicate its networking logic.

#### Scenario: Reusing gateway diagnosis from the CLI
- **WHEN** `./docker/docker-constructor.py build` diagnoses host reachability
- **THEN** the facade SHALL call the dedicated networking module
- **AND** the module SHALL return structured diagnosis results without parsing CLI arguments or selecting process exit codes

#### Scenario: Testing networking independently
- **WHEN** gateway candidate selection, probing, or rootless override behavior is tested
- **THEN** tests SHALL import the dedicated networking module directly
- **AND** SHALL NOT require invoking the constructor CLI facade

## MODIFIED Requirements

### Requirement: Probe host reachability from Docker
The system SHALL test candidate host gateway mappings from inside a temporary container through the unified version command.

#### Scenario: Running diagnostics for a build
- **WHEN** `./docker/docker-constructor.py build` performs gateway diagnosis
- **THEN** it SHALL start a temporary HTTP probe server on the host
- **AND** SHALL detect whether Docker is running in rootless mode
- **AND** SHALL test candidate mappings for `host.docker.internal`
- **AND** SHALL print probe results and the chosen `HOST_GATEWAY_IP` when a working route is found

### Requirement: Install a rootless Docker override
The system SHALL be able to install a user-level Docker systemd override for rootless port forwarding through the unified version command surface.

#### Scenario: Applying the override through the unified command
- **WHEN** the user explicitly requests rootless override application through `docker-constructor.py doctor`
- **THEN** the command SHALL copy `docker/rootless-docker.override.conf` to `~/.config/systemd/user/docker.service.d/override.conf`
- **AND** SHALL reload the user systemd daemon
- **AND** SHALL restart `docker.service`
- **AND** SHALL rerun diagnostics

#### Scenario: Applying the override through the helper script
- **WHEN** `docker/apply-rootless-port-forward.sh` is executed
- **THEN** it SHALL install the same override file
- **AND** SHALL restart rootless Docker
- **AND** SHALL invoke the constructor facade's `doctor` command

### Requirement: Persist detected host gateway configuration before build
The system SHALL make the chosen host gateway mapping available to direct Docker build and launch workflows without a separate build wrapper and without placing operational host state in either dependency section.

#### Scenario: Running the unified build command
- **WHEN** `./docker/docker-constructor.py build` succeeds in probing host reachability
- **THEN** it SHALL persist `HOST_GATEWAY_IP=<detected-value>` through the existing operational host configuration boundary
- **AND** it SHALL invoke `docker build` directly with the validated effective build projection
- **AND** `docker-constructor.toml` SHALL NOT be modified

#### Scenario: Launching after gateway persistence
- **WHEN** the launcher constructs a direct Docker run after a successful diagnosis
- **THEN** it SHALL use the persisted operational gateway for Docker's host mapping
- **AND** it SHALL NOT expose gateway state as runtime dependency metadata

### Requirement: Expose host mapping in direct Docker runs
The system SHALL inject a host mapping into runtime container launches without Compose.

#### Scenario: Starting the Pi container
- **WHEN** the launcher constructs a direct `docker run` command
- **THEN** it SHALL add `host.docker.internal:<resolved-gateway>` through Docker's host-mapping option
- **AND** the Docker build SHALL NOT receive unused host-proxy arguments

## REMOVED Requirements

### Requirement: Generate model proxy configuration from inf-splitter TOML
**Reason**: The generator is not used by the image build, launcher, runtime setup, or any maintained workflow, and its environment configuration is stale.
**Migration**: Manage custom Pi provider configuration in the external integration that owns the proxy, or maintain Pi `models.json` directly outside this repository.

## RENAMED Requirements

- FROM: `### Requirement: Expose host mapping in compose`
- TO: `### Requirement: Expose host mapping in direct Docker runs`
