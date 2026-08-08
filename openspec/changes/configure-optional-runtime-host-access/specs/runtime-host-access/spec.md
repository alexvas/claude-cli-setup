## ADDED Requirements

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
The system SHALL resolve a closed local TOML companion beside the reviewed inventory and SHALL use it only for `[host-access].address` and `[cache].dir`. The local companion SHALL NOT override reviewed dependency, update, artifact, host-access policy, or cache TTL fields.

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

#### Scenario: Rejecting malformed local state
- **WHEN** a consumer reads an unknown local key, malformed TOML, invalid host address, or invalid cache directory value
- **THEN** the operation SHALL fail before network, cache mutation, artifact materialization, or Docker execution
- **AND** SHALL provide path-specific recovery guidance

#### Scenario: Falling back when local cache directory is absent
- **WHEN** the local companion is absent or omits `[cache].dir`
- **THEN** cache consumers SHALL use the existing `XDG_CACHE_HOME`-based default
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
