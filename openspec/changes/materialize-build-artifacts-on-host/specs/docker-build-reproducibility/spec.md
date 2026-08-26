## ADDED Requirements

### Requirement: Construct pinned build inputs without Dockerfile artifact downloads
The canonical build SHALL resolve `linux-amd64` reviewed artifacts before Docker execution and SHALL supply their verified local snapshot to BuildKit. Dockerfile stages for rustup, uv, rtk, and fd SHALL perform no network request for those artifacts. Existing Docker images SHALL be self-contained and SHALL not depend on retained source blobs.

#### Scenario: Building with materialized artifacts
- **WHEN** the canonical image build starts with all selected artifacts verified
- **THEN** Docker SHALL consume them from the dedicated local named context
- **AND** the corresponding stages SHALL not receive or fetch artifact URLs

#### Scenario: Running an existing image after cache cleanup
- **WHEN** source blobs used to build an existing image have been removed from the checkout cache
- **THEN** that image and its containers SHALL remain operational

### Requirement: Install Pi from its authoritative locked release metadata
The reviewed Pi source SHALL declare npm package `@earendil-works/pi-coding-agent`, release repository `earendil-works/pi`, and release tag prefix `v`. For selected version `<version>`, the authoritative release base URL SHALL be exactly `https://github.com/earendil-works/pi/releases/download/v<version>/`, and the required asset names SHALL be exactly `pi-coding-agent-install-package.json`, `pi-coding-agent-install-package-lock.json`, and `SHA256SUMS`. The build SHALL use the two installation files only after their bytes match their respective entries in that release's `SHA256SUMS`. Pi SHALL be installed with lockfile-frozen `npm ci` semantics and lifecycle scripts disabled. The installed Pi command and SDK layout under `/opt/pi` SHALL preserve the existing container interface. Pi's npm tarballs MAY be fetched inside BuildKit and SHALL be verified by npm against lockfile integrity values.

#### Scenario: Deriving authoritative Pi release URLs
- **WHEN** reviewed Pi version `0.84.3`, repository `earendil-works/pi`, and tag prefix `v` are selected
- **THEN** the constructor SHALL request `https://github.com/earendil-works/pi/releases/download/v0.84.3/SHA256SUMS`
- **AND** SHALL request the two exact installation asset names beneath the same release base URL

#### Scenario: Installing a valid Pi release
- **WHEN** the selected authoritative Pi release publishes matching installation package, lockfile, and SHA256SUMS entries
- **THEN** the build SHALL verify the two files and run lockfile-frozen installation with scripts disabled
- **AND** the final image SHALL expose the selected Pi through the established command and module paths

#### Scenario: Rejecting incomplete Pi installation metadata
- **WHEN** the release repository or tag prefix is absent or invalid, any required asset is absent, either installation checksum is absent, or installation bytes do not match SHA256SUMS
- **THEN** host materialization SHALL fail before snapshot publication, npm installation, or Docker execution

#### Scenario: Preserving npm integrity checks
- **WHEN** npm fetches a dependency selected by the official lockfile
- **THEN** it SHALL verify the package against that lockfile entry's integrity
- **AND** an integrity mismatch SHALL fail the build
