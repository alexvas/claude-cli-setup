# Capability: project-launcher

## Purpose
Define the current launcher flow that selects project directories and starts a π container with generated compose overrides.

## Requirements

### Requirement: Allocate unique container names
The system SHALL name launched containers sequentially as `pi-N`.

#### Scenario: Computing the next container number
- **WHEN** the launcher starts
- **THEN** it inspects existing Docker container names matching `pi-<number>`
- **AND** chooses the smallest positive integer not currently in use

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

### Requirement: Load workspace launcher configuration from constructor-project .env
The system SHALL read launcher defaults from `.env` beneath the selected constructor project directory.

#### Scenario: Loading workspace settings
- **WHEN** `docker-constructor run` starts
- **THEN** it SHALL parse the selected project's `.env` as simple `KEY=VALUE` pairs
- **AND** SHALL use `WORKSPACE_ROOT` from `.env` unless overridden by `--workspace-root`
- **AND** SHALL NOT read `BASE_PROJECT_DIR` or an installation-root `.env`

### Requirement: Discover launchable workspaces from a filesystem tree
The system SHALL allow selecting workspaces from a directory tree.

#### Scenario: Building the tree view
- **WHEN** a workspace root is available
- **THEN** the launcher SHALL enumerate subdirectories only
- **AND** SHALL sort them alphabetically
- **AND** SHALL lazily expand subdirectories up to depth 5

#### Scenario: Falling back to the home directory
- **WHEN** no live IDE workspaces and no workspace root are configured
- **THEN** the launcher SHALL use the current user's home directory as the tree root

### Requirement: Provide an interactive workspace terminal UI
The system SHALL provide a curses-based TUI for selecting one primary workspace and optional extra workspaces.

#### Scenario: Navigating the tree
- **WHEN** the TUI is open
- **THEN** arrow keys or `j`/`k` SHALL move the selection
- **AND** right arrow SHALL expand a tree node
- **AND** left arrow SHALL collapse a tree node

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
- **THEN** the current item SHALL become the primary workspace

#### Scenario: Marking extra workspaces
- **WHEN** the user presses `Space`
- **THEN** the current item SHALL cycle between unselected, extra workspace, and primary workspace according to current selection state

#### Scenario: Launching from the TUI
- **WHEN** the user double-presses `Enter`, presses `F5`, or presses `r`
- **THEN** the launcher SHALL return the selected primary workspace and extra workspaces for execution

### Requirement: Run Docker directly with selected workspaces
The system SHALL launch the canonical Pi runtime image using an explicit direct Docker argument vector after validating reviewed launch policy and machine-local state and after all selected runtime artifacts have been materialized and verified on the host.

#### Scenario: Launching the container
- **WHEN** the user starts a session with `--workspace`, repeatable `--extra-workspace`, or an equivalent TUI selection
- **THEN** the launcher SHALL validate reviewed host-access policy and any required local address before launch effects
- **AND** it SHALL resolve the effective runtime selection before launch effects
- **AND** it SHALL ensure every unique selected artifact is present and valid in the content-addressed host cache before Docker execution
- **AND** it SHALL run `docker run` with `--rm`, an allocated `pi-N` name, and interactive terminal behavior
- **AND** SHALL mount the host Pi home at `/home/dev/.pi`
- **AND** SHALL mount the primary and extra selected workspaces 1:1
- **AND** SHALL mount each unique selected cache blob as an individual read-only file at its deterministic fixed artifact target
- **AND** SHALL NOT mount the cache root or any unselected cache blob
- **AND** SHALL set the primary workspace as the working directory
- **AND** SHALL pass consecutive `WORKSPACE_PATH_1..N` values through container environment variables
- **AND** SHALL add `host.docker.internal` and host-access environment variables only when reviewed host access is enabled

#### Scenario: Rejecting removed workspace aliases
- **WHEN** a caller supplies `--main-project`, `-m`, `--project`, or `--base-project-dir`
- **THEN** argument parsing SHALL fail with a CLI error
- **AND** the launcher SHALL NOT translate a removed alias

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
