## MODIFIED Requirements

### Requirement: Store machine-local constructor state separately
The system SHALL resolve a closed local TOML companion beside the reviewed inventory and SHALL use it only for `[host-access].address`, `[cache].dir`, `[corporate-trust].enabled`, and `[network.proxy]` corporate-network settings. The local companion SHALL NOT override reviewed dependency, update, artifact, host-access policy, or cache TTL fields. Corporate trust and proxy settings SHALL remain independent from host-access policy: they SHALL neither require enabled host access nor derive an application proxy URL from `HOST_ACCESS_ADDRESS` or `HOST_PROXY_PORT`.

#### Scenario: Resolving the canonical local companion
- **WHEN** the canonical `docker-constructor.toml` is used
- **THEN** the local companion SHALL be `docker-constructor.local.toml` in the same directory

#### Scenario: Resolving a custom local companion
- **WHEN** `--inventory /path/custom.toml` is used
- **THEN** the local companion SHALL be `/path/custom.local.toml`
- **AND** SHALL NOT fall back to repository-root local state

#### Scenario: Loading a local cache directory without host access
- **WHEN** host access is disabled and the local companion declares `[cache].dir`
- **THEN** cache consumers SHALL use the validated local directory
- **AND** SHALL NOT require `[host-access]` state

#### Scenario: Using corporate proxy without host access
- **WHEN** host access is disabled and the local companion declares a valid external `[network.proxy]` endpoint
- **THEN** build and run planning SHALL accept the proxy configuration
- **AND** SHALL NOT emit host-access mappings or require gateway diagnosis

#### Scenario: Rejecting malformed local state
- **WHEN** a consumer reads an unknown local key, malformed TOML, invalid host address, invalid cache directory value, or invalid corporate network setting
- **THEN** the operation SHALL fail before network, cache mutation, artifact materialization, or Docker execution
- **AND** SHALL provide path-specific recovery guidance

#### Scenario: Falling back when local cache directory is absent
- **WHEN** the local companion is absent or omits `[cache].dir`
- **THEN** cache consumers SHALL use the existing `XDG_CACHE_HOME`-based default
- **AND** SHALL NOT require creation of the local companion
