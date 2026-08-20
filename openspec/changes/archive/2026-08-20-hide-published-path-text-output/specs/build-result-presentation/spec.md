## ADDED Requirements

### Requirement: Hide internal publication metadata from normal build output
The constructor SHALL omit the effective-projection `published_path` from normal text-mode build output while continuing to publish the effective projection.

#### Scenario: Successful normal text build
- **WHEN** a text-mode build successfully publishes its effective projection without verbose output
- **THEN** the final result does not contain `published_path` or the projection filesystem path
- **AND** the effective projection still exists at the published location

### Requirement: Retain publication metadata in explicit diagnostic modes
The constructor SHALL include the effective-projection path as `published_path` in JSON build output and SHALL make the path visible in verbose text build output.

#### Scenario: Successful JSON build
- **WHEN** a build successfully publishes its effective projection with JSON output selected
- **THEN** the JSON result contains `data.published_path`

#### Scenario: Successful verbose text build
- **WHEN** a text-mode build successfully publishes its effective projection with verbose output selected
- **THEN** the rendered result contains `published_path` and the projection filesystem path
