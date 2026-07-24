## ADDED Requirements

### Requirement: Docker Hub checks use the Registry API
The update checker SHALL resolve Docker Hub registry aliases to the canonical Docker Hub Registry API endpoint before authentication probes and manifest requests.

#### Scenario: Conventional Docker Hub alias is configured
- **WHEN** a digest update check is run for an image whose configured registry is `docker.io`
- **THEN** the checker SHALL request authentication and manifest data from `registry-1.docker.io`
- **AND** it SHALL evaluate the manifest's `Docker-Content-Digest` value

### Requirement: Custom registry endpoints are preserved
The update checker SHALL use a configured non-Docker-Hub registry endpoint without rewriting its hostname.

#### Scenario: Custom registry is configured
- **WHEN** a digest update check is run for an image hosted on a non-Docker-Hub registry
- **THEN** authentication probes and manifest requests SHALL use that configured registry hostname

### Requirement: Registry failures remain explicit
The update checker SHALL report a registry update target as unavailable when the Registry API cannot provide a valid manifest digest.

#### Scenario: Manifest response has no digest
- **WHEN** the Registry API returns a successful response without a `Docker-Content-Digest` header
- **THEN** the target SHALL be reported as unavailable with a diagnostic reason
