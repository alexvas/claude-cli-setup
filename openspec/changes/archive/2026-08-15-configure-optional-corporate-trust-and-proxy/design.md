## Context

The Node/Debian image performs network operations in its base stage (`apt-get`) and later stages (`curl`, `uv`, `npm`, and tool installers), then runs developer tooling in the resulting container. The constructor currently accepts only reviewed inventory plus a closed local companion for cache and host-access state. Host access deliberately exposes neutral address/port variables and must remain independent from application proxy configuration.

Corporate TLS interception requires a complete corporate trust bundle, while machine-specific proxy endpoints and local trust files must not be committed to the reviewed version inventory. Dockerfile build arguments do not configure the Docker daemon, so this change cannot control registry access or the initial `FROM` pull.

## Goals / Non-Goals

**Goals:**

- Provide optional local-only complete PEM trust replacement for build stages and a read-only runtime mount of the same source file.
- Provide optional credential-free local proxy configuration for `http`, `socks5`, and `socks5h` endpoints.
- Apply a configured proxy consistently in both build-stage processes and launched containers, while retaining no proxy values in image `ENV`.
- Validate all enabled local inputs before Docker execution and preserve existing no-configuration behavior.
- Keep host-access policy and its neutral `HOST_ACCESS_ADDRESS` / `HOST_PROXY_PORT` contract unchanged.

**Non-Goals:**

- Configure Docker client/daemon proxy, daemon trust, registry credentials, image pulls, or `FROM` resolution.
- Support proxy credentials, arbitrary environment passthrough, PAC/WPAD, proxy auto-discovery, or proxy health checks.
- Promise SOCKS support in every build client; SOCKS build operation is best-effort and a client such as `apt` can fail normally.
- Hot-reload CA trust inside an already running process or container; a restart/new launch receives the current mounted bundle.
- Augment the system trust store, infer a missing bundle, parse or verify supplied certificate payloads as X.509, or prove a supplied bundle contains every required public/corporate root.

## Decisions

### Local companion is the sole configuration source

Add closed local-companion sections for corporate trust and network proxy. Neither endpoint nor trust material enters `docker-constructor.toml`, effective dependency projections, suggestions, or source control. A custom inventory continues to resolve its companion beside that inventory.

`[corporate-trust] enabled = true` is explicit intent; it requires the exact repository-local file `.docker-local/corporate-ca-bundle.crt`. The authoritative root for that fixed bundle is the repository root (the directory containing `docker/` and the canonical `docker-constructor.toml`), never the directory of a custom `--inventory`; a custom inventory still resolves its companion beside that inventory, but its enabled corporate trust bundle remains the repository-local file. Absence or `enabled = false` preserves standard trust behavior. Explicit enablement avoids treating a deleted file as a silent feature disablement.

`[network.proxy]` is enabled by its required `url`; absence disables proxy. `no_proxy` is optional and is emitted only when explicitly configured. Accepted proxy URL schemes are `http`, `socks5`, and `socks5h`; URLs require a host and explicit port and reject userinfo, fragments, unsupported schemes, and malformed values. The configuration contains no credential channel.

An alternative reviewed policy plus local values was rejected because network endpoint use varies per workstation and CI host. An alternative arbitrary host certificate path was rejected because it weakens the one-file contract and makes build-context and mount identity ambiguous.

### One fixed complete bundle serves build and runtime

The fixed bundle is a complete replacement for `/etc/ssl/certs/ca-certificates.crt`, not an added root. The Dockerfile consumes the optional local build-context input before any networked package/install action and validates it as nonempty PEM certificate material before replacement. Client-specific CA environment settings point at the final system-bundle path where needed for consistent curl/OpenSSL/Node behavior.

Host-side validation remains dependency-free because it runs before Docker can establish the configured corporate trust/proxy path. It validates ASCII PEM framing only: complete matching `CERTIFICATE` delimiters, no non-whitespace data outside blocks, and nonempty strict-Base64 payloads. It deliberately does not parse DER or validate X.509 semantics, signatures, expiry, chains, or trust coverage. This avoids a host Python dependency/bootstrap cycle; those semantic properties remain the operator's responsibility and are ultimately exercised by the consuming TLS clients.

At launch, the constructor bind-mounts that same resolved host source file read-only over `/etc/ssl/certs/ca-certificates.crt`. A new launch or restart therefore sees a changed bundle without rebuilding the image. A running process is not expected to reload it.

The optional Dockerfile input needs a tracked empty-directory/placeholder or equivalent generated build-context convention, so a missing disabled bundle never makes `COPY` fail. The actual bundle remains ignored by Git and included in Docker build context only through that controlled location.

### Proxy propagation is explicit and stage-local

When configured, build-vector rendering transports the endpoint and optional bypass list through constructor-specific Docker build arguments such as `PI_CORPORATE_PROXY_URL` and `PI_CORPORATE_NO_PROXY`. The Dockerfile redeclares those arguments in each networked stage and sources a stage-local helper before every networked `RUN`. The helper conditionally exports the standard client variables and therefore overrides conflicting proxy `ENV` values inherited from the base image only when local proxy configuration is active. The constructor-specific transport avoids relying on same-named proxy `ARG`s, which can be shadowed by inherited image `ENV` values. Neither transport arguments nor standard proxy variables are converted to persistent image `ENV` values. Runtime vector rendering explicitly supplies the standard variables with `docker run --env`.

For every configured endpoint, networked build commands and launched runtime containers receive `HTTP_PROXY`, `http_proxy`, `HTTPS_PROXY`, `https_proxy`, `ALL_PROXY`, and `all_proxy`. An explicitly configured bypass list is supplied under `NO_PROXY` and `no_proxy`; omission introduces neither bypass variable. The endpoint is copied verbatim across these variables: this deliberately makes SOCKS support best-effort instead of pretending every client accepts it.

The alternative of deriving a proxy URL from `[runtime.host-access]` was rejected: host access only establishes reachability to a host service, whereas proxy configuration can name any reachable external or host endpoint and chooses application proxy semantics.

### Validation and observability fail closed without treating values as secrets

Before build planning or run-vector execution, local parsing validates the complete closed local-companion schema — including unknown top-level keys, invalid `[host-access]` values, invalid `[cache]` values, corporate intent, bundle presence/type, PEM framing/Base64 decodability, and proxy URI shape. Invalid local state produces a path-specific CONFIG result before Docker execution. The bundle’s semantic completeness remains operator responsibility; validation establishes complete PEM certificate blocks with nonempty decodable payloads but does not establish X.509 validity or organizational trust coverage.

Endpoints contain no credentials by contract, but command displays and structured build data still require deterministic handling and must not add generic environment dumps. Tests verify that proxy configuration is not injected when absent and never becomes an image `ENV` declaration.

## Risks / Trade-offs

- [Replacing rather than augmenting system trust can remove public roots] → Document that the configured file must be a complete bundle; validate syntax and fail before replacement.
- [SOCKS URLs can be unsupported by `apt` or another build client] → Document best-effort build semantics and surface the client’s normal build failure; recommend an HTTP proxy/bridge when deterministic package access is required.
- [Docker daemon base-image pulls remain blocked in a corporate network] → State the daemon/client boundary prominently in documentation and diagnostics.
- [File bind mounts do not guarantee live refresh for running processes] → Guarantee refresh on restart/new launch only.
- [Proxy endpoint is exposed to container processes and Docker inspection] → Prohibit credentials and avoid persistent image `ENV` or broad environment passthrough.

## Migration Plan

The feature is disabled by default, so existing inventories, build vectors, runtime vectors, and images remain valid. Users who need corporate networking create the ignored local configuration and fixed bundle, rebuild once to apply the trust replacement to image build stages, and restart/new-launch containers after future bundle changes. Removing local configuration returns future builds/runs to the existing standard trust/no-proxy behavior. Rollback consists of removing the local configuration and bundle and reverting the feature code; Docker daemon configuration is unaffected.

## Open Questions

None. The exact placeholder or generated-context mechanism is an implementation detail constrained by the optional fixed-file contract.
