## MODIFIED Requirements

### Requirement: Document the current runtime image
The Russian, English, and Chinese README files SHALL present the current Docker development environment around the primary user workflows of building the image, launching it with interactive project selection, updating managed components, and performing occasional maintenance. Internal implementation invariants and image-development diagnostics SHALL NOT interrupt those primary workflows.

#### Scenario: Comparing translated documentation
- **WHEN** the maintained README translations are reviewed
- **THEN** their supported commands, workflow order, component taxonomy, update process, and maintenance guidance SHALL be equivalent
- **AND** references to removed files, services, build targets, and proxy bootstrap behavior SHALL be absent

#### Scenario: Following the primary workflow structure
- **WHEN** a user opens a maintained README
- **THEN** build, interactive launch, and component update SHALL appear as the three primary actions
- **AND** a separate general setup section SHALL NOT be required before understanding those actions
- **AND** detailed Dockerfile/cache-development notes, BuildKit cache experiments, shell-prompt internals, Python implementation details, and Python override examples SHALL NOT appear in the primary user flow

#### Scenario: Selecting projects interactively
- **WHEN** a user follows the launch instructions
- **THEN** documentation SHALL use the executable launcher entry point
- **AND** SHALL explain main-project working-directory selection, optional additional 1:1 mounts, and the mounted Pi home

#### Scenario: Maintaining host state
- **WHEN** a user consults maintenance guidance
- **THEN** image verification, mounted extension refresh, host permission repair, Docker storage cleanup, and user-facing cache cleanup SHALL be grouped under Maintenance
- **AND** permission repair SHALL use `<docker-dev>:<docker-dev>` placeholders and recursive `ug+rwX` semantics
- **AND** every translation SHALL identify `docker-dev` as the user/group typically mapped to host UID/GID `100999` by rootless Docker
- **AND** every translation SHALL show how to add the host user to the `docker-dev` group
- **AND** documentation SHALL warn users to choose the intended host owner before changing shared worktrees

#### Scenario: Troubleshooting current failures
- **WHEN** a user reads troubleshooting guidance
- **THEN** it SHALL focus on actionable current failures such as host EACCES
- **AND** SHALL omit obsolete-name, missing-extra-project, and ordinary host-gateway guidance from the primary troubleshooting list
