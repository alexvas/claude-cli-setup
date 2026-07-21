## MODIFIED Requirements

### Requirement: Provide Python through uv
The system SHALL install an explicit uv-managed CPython runtime whose configured version is 3.14.6 or newer, with exactly 3.14.6 as the default build input. The runtime SHALL expose direct `python` and `python3` executables and SHALL NOT implement either command through `uv run`, a project-aware wrapper, or a shell alias. The system SHALL NOT advertise or create a standalone `pip` command or alias; package operations SHALL be documented through explicit `uv pip` subcommands.

#### Scenario: Running python3 in the container
- **WHEN** a user invokes `python3` from any working directory
- **THEN** the configured uv-managed CPython interpreter executes directly
- **AND** invocation SHALL NOT discover or synchronize a project environment through `uv run`
- **AND** the interpreter version SHALL be 3.14.6 or newer

#### Scenario: Building with the default Python version
- **WHEN** the image is built without a Python version override
- **THEN** the image SHALL install exactly CPython 3.14.6
- **AND** build-time verification SHALL confirm the installed version and executable path

#### Scenario: Building with a supported Python override
- **WHEN** the image is built with an available Python version override equal to or newer than 3.14.6
- **THEN** the image SHALL install and expose the requested version
- **AND** Python-backed uv tool installation SHALL use that configured Python selection explicitly

#### Scenario: Building with an unsupported older Python override
- **WHEN** the image is built with a Python version override older than 3.14.6
- **THEN** the build SHALL fail with a clear version-requirement error

#### Scenario: Installing Python packages
- **WHEN** documentation instructs a user to perform a Python package operation
- **THEN** it SHALL use an explicit `uv pip` subcommand and target context
- **AND** it SHALL NOT rely on a `pip` or `pip3` alias supplied by the image
