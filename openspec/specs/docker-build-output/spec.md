# Docker Build Output

## Purpose

Define Docker build-progress visibility, structured-output isolation, failure reporting, and final build summaries.

## Requirements

### Requirement: Stream build progress in text mode
The constructor SHALL expose Docker build stdout and stderr to the host terminal as they are produced when an actual build runs in text output mode. It SHALL preserve the selected native `--progress auto`, `plain`, or `tty` argument and SHALL NOT buffer the complete build before displaying it.

#### Scenario: Long-running text build
- **WHEN** a user runs `docker-constructor.py build` in text output mode and Docker emits BuildKit progress before exiting
- **THEN** that progress is visible on the host before the Docker process exits

#### Scenario: Explicit progress style
- **WHEN** a user runs a text-mode build with `--progress plain` or `--progress tty`
- **THEN** Docker receives the selected progress style and controls its native presentation

### Requirement: Preserve structured output isolation
The constructor SHALL keep JSON-mode stdout as one valid JSON document. Docker output from a JSON-mode build SHALL be captured rather than streamed into the facade's stdout, and a failed build SHALL retain its captured diagnostic and original exit code in the structured result.

#### Scenario: Successful JSON build
- **WHEN** a user runs a successful build with `--output json`
- **THEN** stdout contains valid constructor JSON without interleaved Docker progress

#### Scenario: Failed JSON build
- **WHEN** Docker emits an error and exits nonzero during a build with `--output json`
- **THEN** the constructor returns an operational failure containing the captured diagnostic and preserving the Docker exit code

### Requirement: Do not duplicate streamed diagnostics
After a streamed text-mode build fails, the constructor SHALL report the failed operation and Docker exit code without replaying output that Docker already wrote to the terminal.

#### Scenario: Streamed build failure
- **WHEN** Docker writes a failure diagnostic during a text-mode build and exits nonzero
- **THEN** the diagnostic is shown once through the inherited stream and the final constructor result does not repeat it

### Requirement: Render an appropriate final build result
After a successful executed text-mode build, the constructor SHALL print a concise success summary instead of the complete Docker build vector. The complete vector SHALL remain available for dry runs, JSON output, and verbose diagnostics.

#### Scenario: Successful executed text build
- **WHEN** an actual text-mode build completes successfully
- **THEN** the constructor prints a concise success summary without printing the full build command as the primary result

#### Scenario: Dry-run build
- **WHEN** a user requests a build dry run
- **THEN** the constructor prints the complete planned Docker build vector and does not execute Docker

#### Scenario: Verbose build diagnostics
- **WHEN** a user requests verbose diagnostics for a build
- **THEN** the complete Docker build vector remains available after rendering
