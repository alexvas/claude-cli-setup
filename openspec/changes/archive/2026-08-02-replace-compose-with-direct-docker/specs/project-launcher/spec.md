## MODIFIED Requirements

### Requirement: Run Docker directly with selected projects
The system SHALL launch the canonical Pi runtime image using an explicit direct Docker argument vector.

#### Scenario: Launching the container
- **WHEN** the user starts a session
- **THEN** the launcher SHALL run `docker run` with `--rm`, an allocated `pi-N` name, and interactive terminal behavior
- **AND** SHALL mount the host Pi home at `/home/dev/.pi`
- **AND** SHALL mount the main and additional selected projects 1:1
- **AND** all selected additional projects SHALL be mounted and numbered consecutively
- **AND** SHALL set the main project as the working directory
- **AND** SHALL pass `PROJECT_PATH_1` and any extra project paths through container environment variables
- **AND** SHALL add the resolved `host.docker.internal` mapping

#### Scenario: Dry-run mode
- **WHEN** the launcher is started with `--dry-run`
- **THEN** it SHALL print a shell-escaped representation of the complete `docker run` argument vector
- **AND** SHALL not create temporary configuration files or execute Docker

## REMOVED Requirements

### Requirement: Generate temporary compose fragments for extra projects
**Reason**: Direct Docker supports repeated bind-mount arguments, so generated YAML fragments are unnecessary.
**Migration**: Render one direct Docker mount argument for each selected project.

## RENAMED Requirements

- FROM: `### Requirement: Run docker compose with generated overrides`
- TO: `### Requirement: Run Docker directly with selected projects`
