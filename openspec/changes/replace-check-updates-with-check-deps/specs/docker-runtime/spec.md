## MODIFIED Requirements

### Requirement: Expose one constructor CLI facade
The project SHALL expose `docker/docker-constructor.py` as the sole supported user-facing command entry point. The facade SHALL provide primary commands `build`, `run`, and `check-deps` and auxiliary commands `validate`, `show`, `doctor`, and `verify`; it SHALL NOT expose `check-updates`, a compatibility alias for it, a command-specific migration hint, or a `schema` command.

#### Scenario: Delegating a facade command
- **WHEN** a user invokes any supported constructor command with command-specific or global flags
- **THEN** the facade SHALL parse and validate user arguments, coordinate prompts, render output, and map errors to exit codes
- **AND** it SHALL delegate inventory, networking, project selection, provider, Docker orchestration, and verification behavior to internal APIs

#### Scenario: Verifying through the facade
- **WHEN** a user invokes `docker-constructor.py verify` with selected verification flags
- **THEN** internal verification APIs SHALL execute the requested checks and return structured results
- **AND** the facade SHALL only select checks and present those results

#### Scenario: Avoiding competing entry points
- **WHEN** maintained documentation or repository-owned automation invokes constructor behavior
- **THEN** it SHALL use `docker/docker-constructor.py`
- **AND** it SHALL NOT invoke `versions.py`, `launch-pi.py`, standalone verification scripts, Compose, or `build_wrapper.py` as user-facing commands

#### Scenario: Rejecting the removed command
- **WHEN** a user invokes `docker-constructor.py check-updates`
- **THEN** normal unknown-command handling SHALL reject it
- **AND** the facade SHALL NOT provide a dedicated migration hint

## ADDED Requirements

### Requirement: Warn about unreachable runtime artifact alternatives
Offline inventory validation SHALL warn for each runtime extension artifact catalog version that is neither the selected default nor selectable under the extension's declared override policy. Such warnings SHALL not require network access and SHALL not make an otherwise valid inventory fail validation.

#### Scenario: Warning about an unreachable artifact version
- **WHEN** `validate` reads a runtime extension whose catalog contains a non-default version excluded by its override policy
- **THEN** validation SHALL identify the extension and unreachable version in a warning
- **AND** SHALL complete without network access
- **AND** SHALL preserve a successful exit when no validation error exists

#### Scenario: Retaining a reachable rollback version
- **WHEN** a non-default artifact version satisfies the extension's override policy
- **THEN** validation SHALL NOT warn merely because that artifact is not the default
