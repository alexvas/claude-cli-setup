## ADDED Requirements

### Requirement: Present a consistent Pi container interface
The project SHALL identify the developer container, Compose service, wrapper commands, launcher commands, and supported documentation as Pi-oriented interfaces.

#### Scenario: Following documented build instructions
- **WHEN** a user follows a build command from any maintained README translation
- **THEN** the command SHALL target Compose service `pi`
- **AND** the service SHALL exist in the evaluated Compose configuration

#### Scenario: Following documented run instructions
- **WHEN** a user follows a run or CLI verification command from any maintained README translation
- **THEN** it SHALL invoke service `pi` and the `pi` CLI rather than the retired Claude service or CLI

### Requirement: Document the current runtime image
The Russian, English, and Chinese README files SHALL describe the tools, environment variables, project mounts, launcher, build process, and troubleshooting behavior implemented by the current Dockerfile and Compose configuration.

#### Scenario: Comparing translated documentation
- **WHEN** the maintained README translations are reviewed
- **THEN** their supported commands and configuration concepts SHALL be equivalent
- **AND** references to removed files, services, build targets, and proxy bootstrap behavior SHALL be absent

### Requirement: Migrate legacy shell identity safely
The shell setup SHALL use Pi-oriented names for project-owned prompt configuration while preserving an explicit migration path for an existing legacy prompt file if that path is renamed.

#### Scenario: Legacy prompt customization exists
- **WHEN** the dev home contains only the legacy project prompt file during the compatibility period
- **THEN** the shell setup SHALL continue loading that customization or migrate it to the Pi-oriented path
- **AND** SHALL prefer the Pi-oriented path when both files exist
