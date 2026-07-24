## ADDED Requirements

### Requirement: Require project selection only for runtime launch
Project paths and 1:1 bind mounts SHALL be runtime launch inputs rather than image-build prerequisites.

#### Scenario: Launching with an interactively selected project
- **WHEN** the launcher starts a runtime container after the user selects a main project
- **THEN** it SHALL configure that project as `PROJECT_PATH_1`, the working directory, and a 1:1 bind mount
- **AND** additional selected projects SHALL remain optional runtime mounts

#### Scenario: Running without a selected main project
- **WHEN** a runtime run operation is requested without `PROJECT_PATH_1` or an equivalent launcher selection
- **THEN** runtime configuration SHALL fail with an actionable project-selection error
- **AND** the build-only configuration SHALL remain unaffected
