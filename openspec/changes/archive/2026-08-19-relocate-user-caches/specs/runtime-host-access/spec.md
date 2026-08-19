## MODIFIED Requirements

### Requirement: Store machine-local constructor state separately
The system SHALL resolve a closed local TOML companion beside the reviewed inventory and SHALL use it only for `[host-access].address`, `[cache].dir`, `[corporate-trust].enabled`, and `[network.proxy]` corporate-network settings. `[cache].dir` SHALL be an absolute path identifying a dedicated constructor-owned root for all machine-local persistent constructor caches, whose consumers use separate named child directories. The local configuration resolver SHALL reject an empty or non-absolute value; it SHALL lexically normalize an absolute value before applying unsafe-root checks: the root SHALL NOT equal `XDG_CACHE_HOME`, the invoking user's home directory, or the filesystem root, and SHALL NOT be an ancestor of `XDG_CACHE_HOME`. Before the selected root is created, secured, or used by a cache consumer, the cache-storage filesystem layer SHALL inspect any existing selected root with no-follow semantics and reject a symlink. The local companion SHALL NOT override reviewed dependency, update, artifact, host-access policy, or cache TTL fields. Corporate trust and proxy settings SHALL remain independent from host-access policy: they SHALL neither require enabled host access nor derive an application proxy URL from `HOST_ACCESS_ADDRESS` or `HOST_PROXY_PORT`.

#### Scenario: Resolving the canonical local companion
- **WHEN** the canonical `docker-constructor.toml` is used
- **THEN** the local companion SHALL be `docker-constructor.local.toml` in the same directory

#### Scenario: Resolving a custom local companion
- **WHEN** `--inventory /path/custom.toml` is used
- **THEN** the local companion SHALL be `/path/custom.local.toml`
- **AND** SHALL NOT fall back to repository-root local state

#### Scenario: Loading a dedicated local cache root without host access
- **WHEN** host access is disabled and the local companion declares a valid absolute dedicated `[cache].dir`
- **THEN** cache consumers SHALL use the validated directory as their shared cache root
- **AND** SHALL NOT require `[host-access]` state

#### Scenario: Rejecting a relative local cache root
- **WHEN** `[cache].dir` is empty or is not an absolute path
- **THEN** local configuration validation SHALL reject it before cache mutation
- **AND** SHALL identify `[cache].dir` as requiring an absolute dedicated directory

#### Scenario: Rejecting XDG_CACHE_HOME as a local cache root
- **WHEN** normalized `[cache].dir` equals `XDG_CACHE_HOME`
- **THEN** local configuration validation SHALL reject it before cache mutation
- **AND** SHALL instruct the user to select a dedicated child directory such as `${XDG_CACHE_HOME}/docker-constructor-custom`
- **AND** SHALL NOT change permissions on `XDG_CACHE_HOME`

#### Scenario: Rejecting shared or dangerous local cache roots
- **WHEN** normalized `[cache].dir` equals the invoking user's home directory or filesystem root, or is an ancestor of `XDG_CACHE_HOME`
- **THEN** local configuration validation SHALL reject it before cache mutation
- **AND** SHALL identify the configured path and instruct the user to choose a dedicated owned directory

#### Scenario: Rejecting a symlinked local cache root
- **WHEN** a cache consumer prepares an existing `[cache].dir` for use
- **AND** the selected root entry is a symlink
- **THEN** cache-storage validation SHALL reject it without following it
- **AND** SHALL identify the configured path
- **AND** SHALL perform no cache mutation, network request, artifact publication, or Docker execution

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
- **THEN** cache consumers SHALL use the XDG-based default constructor cache root when `XDG_CACHE_HOME` is non-empty and absolute, creating a missing XDG directory with `0700` or requiring an existing writable directory
- **AND** SHALL use the `~/.cache`-based default constructor cache root only when `XDG_CACHE_HOME` is empty or non-absolute
- **AND** SHALL reject an explicit absolute non-directory or unwritable XDG path without fallback
- **AND** SHALL NOT require creation of the local companion
