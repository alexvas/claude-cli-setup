## ADDED Requirements

### Requirement: Explicit Debian-codenamed Node.js base image
The Docker image SHALL use a Debian-codenamed Node.js slim base image (`node:<major>-<codename>-slim`) pinned to an explicit Debian release. The codename SHALL be `trixie` (Debian 13).

#### Scenario: Base image is Debian 13 Trixie
- **WHEN** the Dockerfile is inspected
- **THEN** the base stage `FROM` line SHALL reference `node:24-trixie-slim`
- **AND** no other stage SHALL introduce a different base image

#### Scenario: Build on Trixie succeeds
- **WHEN** the image is built from scratch on a Docker host
- **THEN** all `apt-get install` commands SHALL resolve packages from Debian 13 (Trixie) repositories
- **AND** all subsequent stages SHALL inherit the Trixie base without modification
