## ADDED Requirements

### Requirement: Expose only effective runtime dependency metadata to the container
The project SHALL derive a narrow effective runtime projection from the reviewed `runtime` section of `docker-constructor.toml` after applying validated runtime overrides. The projection SHALL contain only effective package identity, version, artifact identity, checksum/integrity, and validation metadata required for runtime installation and SHALL exclude the reviewed source, build section, and host-only runtime metadata.

#### Scenario: Mounting runtime dependency configuration
- **WHEN** the constructor facade launches a container
- **THEN** it SHALL validate and mount the generated effective runtime projection read-only at `/run/pi-cli/docker-constructor.runtime.toml`
- **AND** it SHALL NOT mount `docker-constructor.toml` or a host-side effective build projection

#### Scenario: Isolating concurrent runtime projections
- **WHEN** multiple runtime launches use different effective selections
- **THEN** each launch SHALL atomically create and mount a private projection under `.docker-generated/runtime/`
- **AND** one launch SHALL NOT rewrite another launch's mounted projection
- **AND** the launcher SHALL remove its private host file after Docker exits or launch fails

#### Scenario: Applying a runtime override
- **WHEN** a supported runtime override is supplied to `run`
- **THEN** the resolver SHALL validate it against policy in the reviewed runtime source entry
- **AND** the mounted projection SHALL contain the effective overridden version and matching artifact integrity
- **AND** the reviewed `docker-constructor.toml` SHALL remain unchanged

#### Scenario: Installing Pi extensions at runtime
- **WHEN** the entrypoint or protected installer detects a missing or mismatched configured Pi extension
- **THEN** it SHALL resolve the exact runtime package artifact declared by the effective runtime projection
- **AND** it SHALL verify the declared checksum/integrity before installation
- **AND** it SHALL install idempotently into the mounted Pi home
- **AND** it SHALL validate installed package identity and version after installation

#### Scenario: Rejecting host-only metadata at runtime
- **WHEN** the effective runtime projection is generated and validated
- **THEN** its closed DTO schema SHALL reject build entries, update-provider metadata, update/override policy, and source fields not needed for runtime installation
- **AND** runtime code SHALL NOT require those fields

### Requirement: Expose one constructor CLI facade
The project SHALL expose `docker/docker-constructor.py` as the sole supported user-facing command entry point. The facade SHALL provide primary commands `build`, `run`, and `check-updates` and auxiliary commands `validate`, `show`, `doctor`, and `verify`; it SHALL NOT expose a `schema` command in this change.

#### Scenario: Delegating a facade command
- **WHEN** a user invokes any supported constructor command with command-specific or global flags
- **THEN** the facade SHALL parse and validate user arguments, coordinate prompts, render output, and map errors to exit codes
- **AND** it SHALL delegate inventory, networking, project selection, provider, Docker orchestration, and verification behavior to internal APIs

#### Scenario: Verifying through the facade
- **WHEN** a user invokes `docker-constructor.py verify` with selected verification flags
- **THEN** internal verification APIs SHALL execute the requested checks and return structured results
- **AND** the facade SHALL only select checks and present those results

#### Scenario: Avoiding competing entry points
- **WHEN** maintained documentation or repository-owned automation invokes constructor behavior
- **THEN** it SHALL use `docker/docker-constructor.py`
- **AND** it SHALL NOT invoke `versions.py`, `launch-pi.py`, standalone verification scripts, Compose, or `build_wrapper.py` as user-facing commands

## MODIFIED Requirements

### Requirement: Mount host projects 1:1
The system SHALL run the container directly against host project directories without remapping their paths or using Compose fragments.

#### Scenario: Launching with a main project
- **WHEN** `docker/docker-constructor.py run` starts the Pi image through `docker run`
- **THEN** `PROJECT_PATH_1` SHALL identify the selected main project
- **AND** the container working directory SHALL be set to `PROJECT_PATH_1`
- **AND** the same absolute host path SHALL be bind-mounted into the same absolute path inside the container

#### Scenario: Adding optional extra projects
- **WHEN** the user selects additional projects
- **THEN** each selected path SHALL be added as a separate 1:1 bind mount
- **AND** corresponding `PROJECT_PATH_2` and `PROJECT_PATH_3` environment values SHALL be passed to the container

### Requirement: Present a consistent Pi container interface
The project SHALL identify the developer image, direct Docker build command, launcher command, and supported documentation as Pi-oriented interfaces without requiring a Compose service.

#### Scenario: Following documented build instructions
- **WHEN** a user follows a build command from any maintained README translation
- **THEN** the command SHALL invoke `./docker/docker-constructor.py build`
- **AND** SHALL produce the canonical tagged Pi runtime image

#### Scenario: Following documented run instructions
- **WHEN** a user follows runtime launch instructions from any maintained README translation
- **THEN** the launcher SHALL invoke the Pi image and Pi CLI through direct Docker
- **AND** SHALL NOT require Compose files or a Compose service

### Requirement: Require project selection only for runtime launch
Project paths and 1:1 bind mounts SHALL be direct Docker runtime launch inputs rather than image-build prerequisites.

#### Scenario: Launching with an interactively selected project
- **WHEN** the launcher starts a runtime container after the user selects a main project
- **THEN** it SHALL configure that project as `PROJECT_PATH_1`, the working directory, and a 1:1 bind mount
- **AND** additional selected projects SHALL remain optional runtime mounts

#### Scenario: Running without a selected main project
- **WHEN** a runtime launch is requested without a selected main project
- **THEN** the launcher SHALL fail with an actionable project-selection error
- **AND** the direct build command SHALL remain unaffected
