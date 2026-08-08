## Why

Direct Docker launches currently add `host.docker.internal` to every container even though ordinary Pi sessions do not require host connectivity. Host access should be explicit, disabled by default, and able to target either a Docker-managed gateway or a known external host address without storing machine-specific state in the reviewed inventory.

## What Changes

- Add an optional, closed `[runtime.host-access]` policy to `docker-constructor.toml`, defaulting to disabled when absent, with explicit `docker-gateway` and `external-address` modes and an optional proxy port.
- Add an ignored, human-readable local TOML companion for machine-specific host-access values and cache directory paths, plus a tracked example file; custom inventories resolve a correspondingly named local companion.
- **BREAKING** Move `cache.dir` from reviewed `docker-constructor.toml` to `[cache].dir` in the local companion while retaining reviewed `cache.ttl` policy.
- Make direct Docker launch omit host mapping and host-access environment variables by default.
- When host access is enabled, map `host.docker.internal` to the configured local address and expose that address as `HOST_ACCESS_ADDRESS`; expose `HOST_PROXY_PORT` only when a proxy port is configured.
- Make `doctor` configure and refresh local address state only for Docker-gateway mode, while external-address mode remains explicitly user-configured.
- Make runtime verification conditional on the selected host-access policy and remove `.env` as the gateway-state boundary.
- Supersede the unconditional runtime-mapping and `.env` gateway-persistence decisions recorded by the archived `decouple-build-from-gateway-diagnostics` change while preserving that change's build-isolation outcome.

## Capabilities

### New Capabilities
- `runtime-host-access`: Define opt-in host connectivity policy, local address state, Docker-gateway and external-address modes, proxy-port exposure, validation, and diagnostics.

### Modified Capabilities
- `build-networking`: Scope gateway diagnosis, repair, and persistence to explicit Docker-gateway runtime access rather than builds or unconditional launches.
- `project-launcher`: Render host mapping and host-access environment variables conditionally from validated policy and local state.
- `docker-build-reproducibility`: Extend the closed reviewed runtime schema with host-only launch policy, move machine-specific `cache.dir` to local TOML, and keep local state and host-access metadata out of effective dependency projections.
- `docker-runtime`: Verify and document host connectivity only when explicitly enabled.

## Impact

- Affected configuration: `docker-constructor.toml`, a new ignored local TOML companion and tracked example, migration of `cache.dir`, and removal of gateway ownership from `.env`.
- Affected code: inventory/model validation, constructor facade, networking diagnostics, direct-run DTOs/rendering, launcher orchestration, and runtime verification.
- Affected tests and docs: semantic-source fixtures, configuration validation, doctor/networking, run-vector, launcher, verification, `.gitignore`, and all maintained README translations.
- Existing unconditional `host.docker.internal` mappings become opt-in; users relying on implicit host access must enable and configure the new policy.
- Relationship to prior work: this change preserves build/gateway decoupling from `decouple-build-from-gateway-diagnostics` but replaces its transitional runtime mapping and `.env` persistence model.
