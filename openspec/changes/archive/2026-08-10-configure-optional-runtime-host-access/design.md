## Context

The direct-Docker launcher inherited an unconditional `host.docker.internal` mapping from the removed Compose topology. Current repository-owned runtime behavior does not require host connectivity, while users may optionally need either Docker-managed gateway access or access through a known external host interface. The reviewed `docker-constructor.toml` is authoritative and committed, so machine-specific addresses must not be written into it; the existing `.env` gateway boundary is implicit, weakly typed, and conflates unrelated launcher defaults with diagnostic state.

The archived `decouple-build-from-gateway-diagnostics` change correctly removed gateway diagnosis from image builds but intentionally retained unconditional runtime mapping and moved persistence to `doctor` and `.env` as a transitional boundary. This design preserves that build isolation while superseding those runtime-mapping and `.env`-persistence decisions.

The runtime inventory and effective dependency projection are intentionally closed. Host-access policy belongs to the reviewed runtime source but controls only host-side launch rendering. Machine-local address state must remain outside the mounted projection and container dependency metadata. The reviewed source also currently permits `cache.dir`, even though an absolute cache path is machine-specific; that path belongs in the same local companion, while portable cache policy such as `cache.ttl` remains reviewed.

## Goals / Non-Goals

**Goals:**
- Make host access absent by default and explicit when enabled.
- Support Docker-managed gateway and known external-address modes through one stable container hostname.
- Keep reviewed policy separate from machine-local address and cache-path state while using human-readable TOML for both.
- Expose neutral `HOST_ACCESS_ADDRESS` and optional `HOST_PROXY_PORT` variables without selecting a proxy protocol or constructing a proxy URL.
- Keep builds independent of host access and make diagnostics and verification policy-aware.

**Non-Goals:**
- Configure `PI_PROXY_URL`, `HTTP_PROXY`, `HTTPS_PROXY`, `ALL_PROXY`, or application-specific proxy settings.
- Detect or validate the protocol spoken by a configured proxy port.
- Automatically discover an external interface address for external-address mode.
- Put machine-local addresses in the reviewed inventory or effective runtime dependency projection.
- Probe host reachability during ordinary launch planning.

## Decisions

### Supersede the transitional runtime gateway boundary

Build orchestration remains fully independent of gateway reachability and operational host state, as established by `decouple-build-from-gateway-diagnostics`. Its unconditional direct-run mapping and doctor-to-`.env` persistence are replaced by the opt-in policy and local TOML state below. The archived proposal remains a historical record of the narrower build-isolation step rather than the final runtime architecture.

### Separate reviewed policy from local address state

The reviewed source accepts an optional closed table:

```toml
[runtime.host-access]
enabled = true
mode = "docker-gateway"
proxy-port = 1080
```

Absence is equivalent to `enabled = false`. When disabled, `mode` and `proxy-port` are forbidden. When enabled, `mode` is required and is exactly `docker-gateway` or `external-address`; `proxy-port`, when present, is an integer from 1 through 65535.

A separate ignored companion contains machine-specific values:

```toml
[host-access]
address = "10.0.2.2"

[cache]
dir = "/home/user/.cache/pi-cli/versioning"
```

For `docker-constructor.toml`, the companion is `docker-constructor.local.toml`. An explicit inventory named `<stem>.toml` resolves `<stem>.local.toml` beside it. A tracked `docker-constructor.local.example.toml` documents the closed local schema. This avoids generic overlay semantics: the local file can supply only `[host-access].address` and `[cache].dir`; it cannot override reviewed dependencies, host-access policy, or `cache.ttl`. The local companion may therefore be useful even when host access is disabled.

`cache.dir` is removed from the reviewed schema and accepted only as local state. Existing reviewed `cache.dir` values fail with migration guidance rather than being silently preferred or merged. Cache consumers resolve the local directory from the companion and continue to derive the default from `XDG_CACHE_HOME` when no local directory is configured. Reviewed `cache.ttl` remains in `docker-constructor.toml` because it is portable cache policy rather than a machine path.

Alternative: continue using `.env`. Rejected because dotenv is untyped, obscures source precedence, and no longer represents the direct-Docker configuration model. Alternative: store machine paths or the address in `docker-constructor.toml`. Rejected because diagnostics would mutate reviewed source and committed absolute paths are not portable.

### Use one address contract for two access modes

Both modes require a validated local address and render:

```text
--add-host host.docker.internal:<address>
--env HOST_ACCESS_ADDRESS=<address>
```

`docker-gateway` means the address is selected and maintained by `doctor` from Docker gateway candidates, including rootless repair when explicitly requested. `external-address` means the user supplies a reachable IPv4 or IPv6 address for a host interface; `doctor` does not replace it or install gateway repair. In both modes, applications use the stable name `host.docker.internal`; only the mapping target differs.

The local `address` accepts an IP address. Docker's literal `host-gateway` token may be accepted only in Docker-gateway mode if the launcher and verification contract can represent its resolved runtime address consistently; otherwise `doctor` persists the concrete successful resolved IP. External-address mode never accepts `host-gateway`.

Alternative: expose separate hostnames for the modes. Rejected because it leaks routing choice into user configuration and prevents a stable proxy URL.

### Keep proxy-port optional and protocol-neutral

When `proxy-port` is configured, launch additionally renders:

```text
--env HOST_PROXY_PORT=<port>
```

The launcher does not derive a URL. User-owned entrypoint or Pi configuration may construct, for example, `socks5://host.docker.internal:${HOST_PROXY_PORT}`. Without `proxy-port`, `HOST_PROXY_PORT` is absent even when general host access is enabled.

### Make launch and verification conditional

Host access disabled means no local-address requirement, no local gateway read, no `--add-host`, and no host-access environment variables. Enabled access requires a valid local address before artifact materialization or Docker execution. Ordinary `run` does not probe or mutate local state.

Runtime verification skips the host mapping and host-access environment checks when disabled. When enabled, it verifies that `host.docker.internal` resolves to the configured address and that `HOST_ACCESS_ADDRESS` matches; it verifies `HOST_PROXY_PORT` only when configured and does not attempt a protocol-specific connection.

### Make doctor mode-aware and local-file-safe

In Docker-gateway mode, `doctor` diagnoses candidates and atomically updates only `[host-access].address` in the local companion while preserving other recognized local settings. A failed diagnosis leaves prior local state unchanged. Rootless repair remains explicit and consent-gated. In external-address mode, `doctor` reports that the address is user-managed and may validate its syntax, but does not discover, overwrite, or repair it. When host access is disabled, it performs no persistence or repair.

The local file has a closed schema, is ignored by Git, and is written atomically. Unknown keys and malformed values fail before launch; read errors are not silently replaced with defaults.

## Risks / Trade-offs

- [Existing users rely on unconditional mapping] → Treat this as an explicit migration: enable host access and populate the local companion before launch.
- [A saved Docker gateway becomes stale after Docker/network changes] → Keep launch side-effect free and provide `doctor` as the explicit refresh path with actionable errors.
- [An external service binds only to loopback or is blocked by firewall] → Document interface binding and firewall responsibility; do not claim that hostname mapping proves service reachability.
- [IPv6 formatting differs in Docker host mappings] → Validate and render IPv6 through focused vector tests rather than string concatenation assumptions.
- [Two TOML files could appear to be generic overlays] → Limit the local companion to `[host-access].address` and `[cache].dir`, and prohibit dependency or policy overrides.
- [Existing inventories declare `cache.dir`] → Reject the retired reviewed field with migration guidance to move it to the corresponding local companion; leave `cache.ttl` unchanged.

## Migration Plan

1. Add typed reviewed and local schemas while retaining no enabled host access by default.
2. Stop reading and writing `HOST_GATEWAY_IP` in `.env`; add the ignored local companion and tracked example, and migrate any reviewed `cache.dir` into `[cache].dir` there.
3. Make run rendering and verification conditional and update doctor ownership.
4. Remove obsolete gateway lines from `.env.example` and document opt-in migration in all README translations.
5. Users requiring host access enable `[runtime.host-access]`, choose a mode, and either run `doctor` for Docker-gateway mode or write an external address to the local companion.

Rollback restores unconditional mapping and `.env` persistence, but reintroduces implicit host connectivity and split configuration.

## Open Questions

None.
