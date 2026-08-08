## MODIFIED Requirements

### Requirement: Provide reusable gateway networking services
Gateway diagnosis and rootless override behavior SHALL be implemented in a dedicated internal networking module with a reusable programmatic API. The constructor CLI facade SHALL consume this module rather than own or duplicate its networking logic. Image build orchestration SHALL NOT consume gateway diagnosis or persistence services.

#### Scenario: Reusing gateway diagnosis from the CLI
- **WHEN** `./docker/docker-constructor.py doctor` diagnoses host reachability
- **THEN** the facade SHALL call the dedicated networking module
- **AND** the module SHALL return structured diagnosis results without parsing CLI arguments or selecting process exit codes

#### Scenario: Testing networking independently
- **WHEN** gateway candidate selection, probing, or rootless override behavior is tested
- **THEN** tests SHALL import the dedicated networking module directly
- **AND** SHALL NOT require invoking the constructor CLI facade

### Requirement: Probe host reachability from Docker
The system SHALL test candidate host gateway mappings from inside a temporary container through the explicit `doctor` command.

#### Scenario: Running diagnostics through doctor
- **WHEN** `./docker/docker-constructor.py doctor` performs gateway diagnosis
- **THEN** it SHALL start a temporary HTTP probe server on the host
- **AND** SHALL detect whether Docker is running in rootless mode
- **AND** SHALL test candidate mappings for `host.docker.internal`
- **AND** SHALL print probe results and the chosen `HOST_GATEWAY_IP` when a working route is found

### Requirement: Persist detected host gateway configuration for runtime launch
The system SHALL make a gateway selected by explicit diagnostics available to direct Docker runtime launches without a separate build wrapper and without placing operational host state in either dependency section. Image build SHALL neither depend on nor persist this state.

#### Scenario: Running the unified build command
- **WHEN** `./docker/docker-constructor.py build` executes
- **THEN** it SHALL invoke `docker build` directly with the validated effective build projection
- **AND** it SHALL NOT diagnose gateway reachability, persist `HOST_GATEWAY_IP`, or modify `docker-constructor.toml` or `.env`

#### Scenario: Launching after gateway configuration
- **WHEN** the launcher constructs a direct Docker run with an operational gateway configuration
- **THEN** it SHALL pass that gateway explicitly as `RunRenderInputs.gateway`
- **AND** `render_run_vector()` SHALL emit that value through Docker's `--add-host` option without reading `.env` or using `--env-file`
- **AND** it SHALL NOT expose gateway state as runtime dependency metadata
