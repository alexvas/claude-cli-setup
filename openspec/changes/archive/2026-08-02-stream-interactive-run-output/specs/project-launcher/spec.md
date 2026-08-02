## ADDED Requirements

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
