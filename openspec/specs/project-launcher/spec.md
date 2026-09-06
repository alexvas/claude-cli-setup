# Capability: project-launcher

## Purpose
Define the current launcher flow that selects project directories and starts a π container with generated compose overrides.

## Requirements

### Requirement: Load launcher configuration from .env
The system SHALL read launcher defaults from the repository `.env` file.

#### Scenario: Loading environment settings
- **WHEN** `docker/docker-constructor.py run` starts
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

### Requirement: Select terminal execution mode explicitly
The launcher SHALL execute a direct Docker run in interactive streaming mode when either TTY or interactive stdin is enabled, and SHALL use captured mode only when both are disabled.

#### Scenario: Default interactive launch
- **WHEN** the user launches with the default TTY and interactive stdin settings
- **THEN** the launcher selects interactive streaming mode

#### Scenario: Mixed interactive flags
- **WHEN** either TTY or interactive stdin is enabled while the other is disabled
- **THEN** the launcher selects interactive streaming mode

#### Scenario: Fully noninteractive launch
- **WHEN** both TTY and interactive stdin are disabled
- **THEN** the launcher selects captured mode

### Requirement: Stream interactive container terminal I/O
The launcher SHALL inherit host stdin, stdout, and stderr for interactive streaming execution and SHALL NOT capture or replay those streams through facade diagnostics.

#### Scenario: Interactive startup and shell
- **WHEN** an interactive container emits entrypoint output or a shell prompt
- **THEN** the output is visible on the host terminal before the container exits
- **AND** host keyboard input reaches the attached container

#### Scenario: Interactive process completes
- **WHEN** the attached interactive container exits
- **THEN** the launcher preserves its return code
- **AND** does not duplicate output already written to the terminal

### Requirement: Preserve bounded captured diagnostics
The launcher SHALL capture stdout and stderr independently in fully noninteractive mode and SHALL bound each serialized diagnostic stream by the configured UTF-8 byte limit.

#### Scenario: Captured failure output
- **WHEN** a fully noninteractive container exits nonzero with stdout and stderr
- **THEN** structured output includes both captured streams and the original exit code
- **AND** human-readable diagnostics label each non-empty stream

#### Scenario: Oversized captured output
- **WHEN** a captured stream exceeds the configured UTF-8 byte limit
- **THEN** its serialized value fits within that byte limit
- **AND** ends with an explicit truncation marker
- **AND** structured output records that the stream was truncated

### Requirement: Expose run execution mode
The launcher SHALL identify whether run output was streamed interactively or captured in structured facade results.

#### Scenario: Interactive structured result
- **WHEN** an interactive run produces a structured result
- **THEN** the result identifies mode `interactive`
- **AND** preserves run arguments, container name, projection identity, and exit code
- **AND** omits captured stdout and stderr fields

#### Scenario: Captured structured result
- **WHEN** a fully noninteractive run produces a structured result
- **THEN** the result identifies mode `captured`
- **AND** includes captured stdout and stderr fields

### Requirement: Publish implicit launcher state outside constructor and workspaces
The launcher SHALL publish every implicit runtime projection and other launcher-generated control file beneath the invoking-user-owned external namespace whose identity is the canonical path of the selected constructor project. Primary and extra workspaces are mounted workspaces and SHALL NOT receive separate runtime projection namespaces during that launch. Normal launch and verification operations SHALL NOT create `.docker-generated` or another constructor-generated directory beneath the constructor project or any primary or extra workspace. The container-visible projection contents and direct Docker launch contract SHALL remain unchanged by the host-path relocation.

#### Scenario: Launching from foreign-owned readable directories
- **WHEN** the invoking user launches with a readable and traversable constructor project, primary workspace, or extra workspace whose directory or entries are owned by a different user
- **THEN** the launcher SHALL publish its runtime projection beneath the external namespace identified by the constructor project's canonical path
- **AND** SHALL NOT require ownership of or mutate the constructor project or any primary or extra workspace
- **AND** SHALL pass only the required projection file into the container through the existing direct Docker contract

#### Scenario: Launching workspaces through the constructor namespace
- **WHEN** one constructor project, one primary workspace, and one or more extra workspaces participate in a normal launch
- **THEN** the launcher SHALL store its runtime projection only beneath the namespace identified by the canonical path of the selected constructor project
- **AND** SHALL NOT create a namespace or generated entry for a workspace merely because it is mounted for that launch
- **AND** the constructor project, primary workspace, and all extra workspaces SHALL contain no newly created `.docker-generated`, `.docker-cache`, projection, lock, temporary, or evidence entry from that operation

#### Scenario: Preserving side-effect-free dry-run behavior
- **WHEN** the launcher is started with `--dry-run`
- **THEN** it SHALL identify the prospective external project-state location from the canonical path of the selected constructor project without creating the namespace, identity metadata, runtime projection, or any constructor-project, primary-workspace, or extra-workspace generated entry
