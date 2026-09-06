# Capability: runtime-host-access

## Purpose
Define optional reviewed host-access policy, machine-local address and cache-directory state, Docker-gateway and external-address launch modes, and the neutral `HOST_ACCESS_ADDRESS` / `HOST_PROXY_PORT` environment-variable contract.

## Requirements

### Requirement: Declare reviewed runtime host-access policy
The system SHALL accept an optional closed `[runtime.host-access]` table in `docker-constructor.toml`. An absent table SHALL be equivalent to disabled host access. The table SHALL support `enabled`, `mode`, and `proxy-port`; enabled host access SHALL require `mode` to be exactly `docker-gateway` or `external-address`, and `proxy-port`, when present, SHALL be an integer from 1 through 65535.

#### Scenario: Host access is absent by default
- **WHEN** `[runtime.host-access]` is absent or declares only `enabled = false`
- **THEN** validation SHALL treat host access as disabled
- **AND** launch SHALL NOT require machine-local host-access state

#### Scenario: Rejecting contradictory disabled policy
- **WHEN** disabled host access also declares `mode` or `proxy-port`
- **THEN** validation SHALL reject the reviewed inventory with an actionable path-specific error

#### Scenario: Validating enabled policy
- **WHEN** host access is enabled
- **THEN** validation SHALL require a supported mode
- **AND** SHALL reject unknown keys, unsupported modes, booleans used as ports, and ports outside 1 through 65535

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

### Requirement: Support Docker-gateway host access
Docker-gateway mode SHALL map `host.docker.internal` to a gateway address selected for the active Docker host and SHALL expose the selected address to the container as `HOST_ACCESS_ADDRESS`.

#### Scenario: Launching through a configured Docker gateway
- **WHEN** host access is enabled in `docker-gateway` mode and valid local address state exists
- **THEN** the direct Docker vector SHALL include `--add-host host.docker.internal:<address>`
- **AND** SHALL include `--env HOST_ACCESS_ADDRESS=<address>`

#### Scenario: Missing Docker-gateway state
- **WHEN** Docker-gateway mode is enabled but no valid local address exists
- **THEN** launch planning SHALL fail with an instruction to run `doctor`
- **AND** SHALL NOT probe Docker implicitly

### Requirement: Support external-address host access
External-address mode SHALL map `host.docker.internal` to an explicitly configured host-interface IP and SHALL expose that IP to the container as `HOST_ACCESS_ADDRESS`.

#### Scenario: Launching through an external host address
- **WHEN** host access is enabled in `external-address` mode with a valid local IP address
- **THEN** the direct Docker vector SHALL include `--add-host host.docker.internal:<address>`
- **AND** SHALL include `--env HOST_ACCESS_ADDRESS=<address>`
- **AND** SHALL NOT require Docker gateway diagnosis or rootless override state

#### Scenario: Rejecting Docker token as an external address
- **WHEN** external-address mode supplies `host-gateway` instead of an IP address
- **THEN** local-state validation SHALL reject it

### Requirement: Expose optional host proxy port
The system SHALL expose a configured reviewed proxy port as `HOST_PROXY_PORT` without selecting a proxy protocol or constructing an application proxy URL.

#### Scenario: Launching with a proxy port
- **WHEN** enabled host access declares `proxy-port = 1080`
- **THEN** the direct Docker vector SHALL include `--env HOST_PROXY_PORT=1080`
- **AND** SHALL leave application-specific proxy URL construction to user-owned runtime configuration

#### Scenario: Launching without a proxy port
- **WHEN** enabled host access omits `proxy-port`
- **THEN** the container SHALL receive `HOST_ACCESS_ADDRESS`
- **AND** SHALL NOT receive `HOST_PROXY_PORT`, `PI_PROXY_URL`, `HTTP_PROXY`, `HTTPS_PROXY`, or `ALL_PROXY` from this capability

### Requirement: Keep disabled host access absent from launch
The system SHALL omit all host-access effects when reviewed host access is disabled.

#### Scenario: Launching an ordinary Pi session
- **WHEN** host access is disabled
- **THEN** the direct Docker vector SHALL NOT add a mapping for `host.docker.internal`
- **AND** SHALL NOT set `HOST_ACCESS_ADDRESS` or `HOST_PROXY_PORT`
- **AND** SHALL NOT read or require a local host address

### Requirement: Resolve runtime projection state through the external constructor-project namespace
Runtime projection publication and host-path validation SHALL use the invoking-user-owned external project-state namespace beneath the resolved constructor cache root whose identity is the canonical path of the selected constructor project. Primary and extra workspaces are mounted workspaces and SHALL NOT receive separate runtime projection namespaces during that launch. The namespace SHALL remain separate from global runtime-artifact and versioning cache namespaces. Runtime projection validation SHALL accept only contained regular projection files beneath the verified runtime-generated child of that namespace and SHALL reject checkout-local `.docker-generated/runtime` paths, cross-constructor-project paths, symlinks, unsafe types, identity mismatches, and containment escapes before Docker execution. Ownership of the constructor project, primary workspace, or any extra workspace SHALL NOT be required when the invoking user has the read and traversal access needed for reviewed inputs, and none of those directories SHALL be mutated.

#### Scenario: Publishing a runtime projection externally
- **WHEN** a non-dry-run launch with one constructor project, one primary workspace, and zero or more extra workspaces requires an effective runtime projection
- **THEN** the constructor SHALL resolve and verify the external namespace identified by the canonical path of the selected constructor project through the configured or default constructor cache root
- **AND** SHALL atomically publish the projection beneath that namespace's runtime-generated child
- **AND** SHALL create no separate runtime projection namespace for a primary or extra workspace
- **AND** SHALL leave the constructor project, primary workspace, and every extra workspace unchanged

#### Scenario: Rejecting a project-local runtime projection
- **WHEN** launch execution receives a runtime projection host path beneath `.docker-generated/runtime` in the constructor project, primary workspace, or any extra workspace
- **THEN** host-path validation SHALL reject it before Docker execution
- **AND** SHALL NOT adopt, move, delete, or modify the legacy entry

#### Scenario: Rejecting another constructor project's runtime projection
- **WHEN** a runtime projection path is contained by a valid external namespace whose complete identity differs from the canonical path identity of the selected constructor project
- **THEN** host-path validation SHALL reject it before Docker execution
- **AND** SHALL leave both constructor-project namespaces and every constructor-project, primary-workspace, or extra-workspace directory unchanged

#### Scenario: Planning runtime projection state without side effects
- **WHEN** dry-run or another side-effect-free planning operation resolves runtime launch inputs
- **THEN** it SHALL perform no external namespace creation, identity-metadata publication, projection publication, cache mutation, creation of a namespace for a primary or extra workspace, or mutation of any constructor-project, primary-workspace, or extra-workspace directory

### Requirement: Represent an empty runtime extension selection explicitly
The runtime projection schema SHALL require an `extensions` table and SHALL permit that table to contain zero entries. An empty extension selection SHALL serialize as an explicit `[extensions]` table, SHALL remain subject to the same closed-schema validation and external publication lifecycle as a non-empty projection, and SHALL produce no runtime artifact materialization or extension installation. A projection that omits the `extensions` table, gives it a non-table value, or contains unknown top-level or extension fields SHALL be rejected before container execution.

#### Scenario: Launching without runtime extensions
- **WHEN** the effective runtime selection contains zero extensions
- **THEN** the constructor SHALL publish a runtime projection containing an explicit empty `[extensions]` table
- **AND** the runtime installer SHALL accept it as an empty installation plan
- **AND** SHALL download and install no runtime artifacts

#### Scenario: Rejecting an invalid empty-projection schema
- **WHEN** a runtime projection omits the mandatory `extensions` table, represents it with a non-table value, or includes an unknown field
- **THEN** runtime projection validation SHALL reject it before container execution
- **AND** SHALL NOT treat the malformed projection as an empty extension selection
