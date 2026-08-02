## MODIFIED Requirements

### Requirement: Include bundled π skills and extensions
The system SHALL make bundled π assets available in the runtime home directory through constructor-managed runtime setup and SHALL NOT ship the obsolete `/home/dev/install-pi-extensions.sh` compatibility endpoint.

#### Scenario: Omitting the legacy extension setup wrapper
- **WHEN** the runtime image is assembled
- **THEN** it SHALL NOT copy `docker/install-pi-extensions.sh` into the image
- **AND** `/home/dev/install-pi-extensions.sh` SHALL be absent

#### Scenario: Installing supported extensions after mounting the Pi home
- **WHEN** `docker/docker-constructor.py run` launches a container with the effective runtime projection and `/home/dev/.pi` mounted
- **THEN** the root entrypoint SHALL repair mounted Pi-home ownership before privilege drop
- **AND** the protected internal runtime installer SHALL run as user `dev`
- **AND** it SHALL install or validate the configured Pi extensions from exact verified local artifacts
- **AND** each extension SHALL match the projected package identity and explicit version
- **AND** the setup SHALL target the mounted Pi home rather than an image-layer directory

#### Scenario: Registering rtk integration
- **WHEN** constructor-managed runtime setup completes extension installation against the mounted Pi home
- **THEN** the entrypoint SHALL apply `rtk init -g --agent pi` as user `dev`
- **AND** it SHALL disable rtk telemetry
- **AND** repeated container launches SHALL not duplicate configuration

#### Scenario: Rejecting an unavailable Pi home
- **WHEN** the effective runtime projection is present but the expected Pi home is not mounted
- **THEN** protected runtime setup SHALL fail with an actionable error before launching Pi
- **AND** it SHALL not install extensions or rtk configuration into the image-provided `/home/dev/.pi`

#### Scenario: Following the supported migration path
- **WHEN** a user needs runtime extension setup after removal of the image-local wrapper
- **THEN** maintained documentation SHALL direct the user through `docker/docker-constructor.py run`
- **AND** it SHALL NOT present direct internal installer invocation as a second public constructor facade
