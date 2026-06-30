# Capability: project-launcher

## Purpose
Define the current launcher flow that selects project directories and starts a π container with generated compose overrides.

## Requirements

### Requirement: Load launcher configuration from .env
The system SHALL read launcher defaults from the repository `.env` file.

#### Scenario: Loading environment settings
- **WHEN** `launch-pi.py` starts
- **THEN** it parses `.env` as simple `KEY=VALUE` pairs
- **AND** uses `BASE_PROJECT_DIR` from `.env` unless overridden by `--base-project-dir`

### Requirement: Discover launchable directories from a filesystem tree
The system SHALL allow selecting projects from a directory tree.

#### Scenario: Building the tree view
- **WHEN** a base project directory is available
- **THEN** the launcher enumerates subdirectories only
- **AND** sorts them alphabetically
- **AND** lazily expands subdirectories up to depth 5

#### Scenario: Falling back to the home directory
- **WHEN** no live IDE projects and no base directory are configured
- **THEN** the launcher uses the current user's home directory as the tree root

### Requirement: Allocate unique container names
The system SHALL name launched containers sequentially as `pi-N`.

#### Scenario: Computing the next container number
- **WHEN** the launcher starts
- **THEN** it inspects existing Docker container names matching `pi-<number>`
- **AND** chooses the smallest positive integer not currently in use

### Requirement: Provide an interactive terminal UI
The system SHALL provide a curses-based TUI for selecting a main project and optional additional projects.

#### Scenario: Navigating the tree
- **WHEN** the TUI is open
- **THEN** arrow keys or `j`/`k` move the selection
- **AND** right arrow expands a tree node
- **AND** left arrow collapses a tree node

#### Scenario: Scrolling downward through a long tree
- **WHEN** the current selection reaches the bottom visible row of a tree list that exceeds the viewport height
- **THEN** pressing Down or `j` SHALL keep the highlighted row visible
- **AND** the launcher SHALL scroll the tree upward by one row to reveal the next item

#### Scenario: Scrolling upward through a shifted tree
- **WHEN** the tree has been scrolled upward and the current selection reaches the top visible row
- **THEN** pressing Up or `k` SHALL keep the highlighted row visible
- **AND** the launcher SHALL scroll the tree downward by one row to reveal the previous item

#### Scenario: Managing selections
- **WHEN** the user presses `Enter`
- **THEN** the current item becomes the main project

#### Scenario: Marking additional projects
- **WHEN** the user presses `Space`
- **THEN** the current item cycles between unselected, additional, and main according to current selection state

#### Scenario: Launching from the TUI
- **WHEN** the user double-presses `Enter`, presses `F5`, or presses `r`
- **THEN** the launcher returns the selected main project and additional projects for execution

### Requirement: Generate temporary compose fragments for extra projects
The system SHALL generate ephemeral compose files describing the selected mounts.

#### Scenario: Preparing launch files
- **WHEN** one or more additional projects are selected
- **THEN** the launcher creates a temporary fragment for each extra project mount
- **AND** creates a temporary override file that exports `PROJECT_PATH_1..N` in compose environment
- **AND** registers those temporary files for cleanup on process exit

### Requirement: Run docker compose with generated overrides
The system SHALL launch the `pi` service using the generated compose file chain.

#### Scenario: Launching the container
- **WHEN** the user starts a session
- **THEN** the launcher sets `COMPOSE_FILE` to `docker-compose.yml` plus generated fragments and override file
- **AND** runs `docker compose --project-directory <repo-root> run --rm --remove-orphans --name pi-N pi`
- **AND** passes `PROJECT_PATH_1` and any extra project paths through the environment

#### Scenario: Dry-run mode
- **WHEN** the launcher is started with `--dry-run`
- **THEN** it prints the computed environment, generated override content, and docker compose command
- **AND** does not execute Docker
