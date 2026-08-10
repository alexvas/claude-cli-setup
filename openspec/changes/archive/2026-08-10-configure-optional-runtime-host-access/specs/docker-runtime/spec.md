## ADDED Requirements

### Requirement: Verify runtime host access conditionally
Runtime verification SHALL derive host-access expectations from validated reviewed policy and its resolved local address rather than assuming every container has a host mapping.

#### Scenario: Verifying enabled host access
- **WHEN** runtime verification inspects a container launched with enabled host access
- **THEN** it SHALL verify that `host.docker.internal` resolves to the configured address
- **AND** SHALL verify that `HOST_ACCESS_ADDRESS` equals that address
- **AND** SHALL verify `HOST_PROXY_PORT` equals the reviewed proxy port when one is configured
- **AND** SHALL NOT require a protocol-specific connection to the proxy port

#### Scenario: Verifying disabled host access
- **WHEN** runtime verification inspects a container launched with disabled host access
- **THEN** it SHALL skip the positive host mapping requirement
- **AND** SHALL verify that constructor launch did not set `HOST_ACCESS_ADDRESS` or `HOST_PROXY_PORT`

### Requirement: Document opt-in host connectivity
Maintained documentation SHALL describe host access as an optional runtime capability rather than a build or ordinary launch prerequisite.

#### Scenario: Following host-access documentation
- **WHEN** a user needs a container to reach a service on the host
- **THEN** all maintained README translations SHALL explain the Docker-gateway and external-address modes
- **AND** SHALL explain the local TOML companion and optional `HOST_PROXY_PORT`
- **AND** SHALL NOT instruct ordinary build or run users to configure a gateway
