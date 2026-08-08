## MODIFIED Requirements

### Requirement: Run Docker directly with selected projects
The system SHALL launch the canonical Pi runtime image using an explicit direct Docker argument vector after validating reviewed launch policy and machine-local state and after all selected runtime artifacts have been materialized and verified on the host.

#### Scenario: Launching the container
- **WHEN** the user starts a session
- **THEN** the launcher SHALL validate reviewed host-access policy and any required local address before launch effects
- **AND** it SHALL resolve the effective runtime selection before launch effects
- **AND** it SHALL ensure every unique selected artifact is present and valid in the content-addressed host cache before Docker execution
- **AND** it SHALL run `docker run` with `--rm`, an allocated `pi-N` name, and interactive terminal behavior
- **AND** SHALL mount the host Pi home at `/home/dev/.pi`
- **AND** SHALL mount the main and additional selected projects 1:1
- **AND** SHALL mount each unique selected cache blob as an individual read-only file at its deterministic fixed artifact target
- **AND** SHALL NOT mount the cache root or any unselected cache blob
- **AND** SHALL set the main project as the working directory
- **AND** SHALL pass `PROJECT_PATH_1` and any extra project paths through container environment variables
- **AND** SHALL add `host.docker.internal` and host-access environment variables only when reviewed host access is enabled

#### Scenario: Reusing a valid cached artifact
- **WHEN** a selected integrity identity already has a regular cache blob whose bytes match the declared integrity
- **THEN** launch preparation SHALL reuse that blob without network access
- **AND** it SHALL still include the individual read-only artifact mount in the Docker argument vector

#### Scenario: Materializing a cache miss
- **WHEN** a selected integrity identity is absent from the cache
- **THEN** launch preparation SHALL download only its reviewed selected URL into private temporary state
- **AND** it SHALL verify integrity before atomic publication
- **AND** Docker execution SHALL not begin until every selected cache miss has been successfully published and revalidated

#### Scenario: Recovering from a corrupt cache entry
- **WHEN** a selected cache path is unsafe, non-regular, symlinked, or has bytes that do not match its integrity identity
- **THEN** launch preparation SHALL not mount or use that entry
- **AND** it SHALL repair the entry under per-identity coordination by rematerializing verified bytes
- **AND** it SHALL fail before Docker if repair cannot succeed

#### Scenario: Preparing concurrent launches
- **WHEN** concurrent launches select the same uncached integrity identity
- **THEN** they SHALL coordinate publication per identity
- **AND** no launch SHALL observe or mount partial downloaded bytes
- **AND** all successful launches SHALL resolve to a blob with the declared integrity

#### Scenario: Failing host materialization
- **WHEN** download, integrity verification, cache publication, cancellation, or interruption prevents a selected artifact from becoming valid
- **THEN** launch preparation SHALL clean private temporary state
- **AND** it SHALL not publish an invalid cache hit, create a falsely complete runtime projection, or execute Docker
- **AND** it SHALL return an actionable structured failure

#### Scenario: Dry-run mode
- **WHEN** the launcher is started with `--dry-run`
- **THEN** it SHALL perform only read-only local-state and cache inspection
- **AND** it SHALL report selected artifact identities and cache hits or planned materialization for misses
- **AND** it SHALL print a shell-escaped representation of the complete planned `docker run` argument vector, including deterministic artifact mounts and conditional host-access arguments
- **AND** it SHALL not download, publish, create cache or projection files, execute package tooling, mutate local host-access state, or execute Docker
