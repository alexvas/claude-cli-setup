## ADDED Requirements

### Requirement: Report host-side build materialization progress
Before the main Docker build starts, the constructor SHALL report the current host-side build-materialization phase when text output is presented interactively, including Pi release acquisition, locked dependency assembly, derived-environment validation, and transition to the Docker build. A long-running phase SHALL become visible before it completes. Progress output SHALL obey the same redaction policy as retained diagnostics. JSON and noninteractive execution SHALL create no live diagnostic sink and SHALL retain only bounded diagnostics for failure reporting.

#### Scenario: Pi dependency assembly is long-running
- **WHEN** an interactive text-mode build spends time assembling locked Pi dependencies before the main Docker build
- **THEN** the terminal SHALL identify the Pi assembly phase before it completes
- **AND** redacted assembler warnings or progress SHALL be visible as they are produced

#### Scenario: Build advances to Docker
- **WHEN** host artifact and Pi materialization complete successfully
- **THEN** the constructor SHALL finalize the host-materialization progress state before presenting native Docker build progress

#### Scenario: Structured build output
- **WHEN** a build runs with JSON output
- **THEN** host-materialization progress and assembler output SHALL NOT be written into structured stdout
- **AND** stdout SHALL remain one valid constructor JSON document

#### Scenario: Host materialization fails
- **WHEN** Pi assembly times out or exits unsuccessfully before the main Docker build starts
- **THEN** interactive text output SHALL identify the failed host-materialization phase
- **AND** the main Docker build SHALL NOT execute

### Requirement: Integrate host progress through typed presentation-neutral events
The constructor SHALL convey host-materialization lifecycle and live assembler diagnostics through one immutable typed event interface between the facade, build orchestration, Pi materialization, and assembler execution. Lifecycle events SHALL use fixed phase and started/succeeded/failed state classifications. Diagnostic events SHALL identify their fixed phase and stdout/stderr source and SHALL contain only already-redacted text. The facade SHALL own output-mode selection and rendering; domain modules SHALL NOT print directly or depend on terminal presentation details. The sink SHALL remain optional for SDK and injected callers, and a sink failure SHALL NOT replace or change the build result.

#### Scenario: Text output is noninteractive
- **WHEN** text output is redirected or otherwise runs without interactive presentation
- **THEN** the facade SHALL create no live progress or diagnostic sink
- **AND** failures SHALL retain bounded redacted diagnostics without direct domain output

#### Scenario: Host phase completes or fails
- **WHEN** a host-materialization phase starts
- **THEN** its started event SHALL be observable before its potentially blocking work
- **AND** exactly one matching succeeded or failed event SHALL follow
- **AND** no later host phase or Docker build SHALL start after a failed event

#### Scenario: Injected caller omits presentation
- **WHEN** an SDK or injected materializer or executor does not provide the optional event sink
- **THEN** its existing non-presenting behavior SHALL remain compatible
- **AND** domain execution SHALL NOT print directly

#### Scenario: Presentation sink fails
- **WHEN** the event sink raises while presenting host progress or diagnostics
- **THEN** the sink failure SHALL remain secondary
- **AND** SHALL NOT mask a timeout, interruption, assembler failure, or Docker result
