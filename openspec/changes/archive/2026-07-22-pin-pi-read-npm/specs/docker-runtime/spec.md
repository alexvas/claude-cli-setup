## MODIFIED Requirements

### Requirement: Include bundled π skills and extensions
The system SHALL make bundled π assets available in the runtime home directory.

#### Scenario: Providing the protected extension setup script
- **WHEN** the runtime image is assembled
- **THEN** it SHALL copy `docker/install-pi-extensions.sh` to `/home/dev/install-pi-extensions.sh`
- **AND** the file SHALL be owned by `root:root`
- **AND** user `dev` SHALL have read and execute permission
- **AND** user `dev` SHALL not have write permission

#### Scenario: Installing supported extensions after mounting the Pi home
- **WHEN** `/home/dev/.pi` is mounted and user `dev` runs the protected setup script
- **THEN** the script SHALL install or register `@llblab/pi-codex-usage`, `pi-proxy`, and the pinned `@arcanemachine/pi-read` npm package
- **AND** each npm-installed extension SHALL use an explicit version
- **AND** the setup SHALL target the mounted Pi home rather than an image-layer directory

#### Scenario: Registering rtk integration
- **WHEN** user `dev` runs the protected setup script with the Pi home mounted
- **THEN** it SHALL apply `rtk init -g --agent pi`
- **AND** SHALL disable rtk telemetry
- **AND** repeated execution SHALL not duplicate configuration

#### Scenario: Rejecting an unavailable Pi home
- **WHEN** the setup script is run without the expected mounted Pi home
- **THEN** it SHALL fail with an actionable error
- **AND** SHALL not install extensions into the image-provided `/home/dev/.pi`
