## Why

Corporate TLS interception causes build-time and runtime clients to reject otherwise valid upstream certificates, and corporate networks may require a proxy. The image currently has no constructor-managed corporate trust or proxy configuration, while such machine-specific endpoints and trust material must not enter the reviewed dependency inventory.

## What Changes

- Add optional, local-only corporate trust configuration backed by one fixed complete PEM bundle at `.docker-local/corporate-ca-bundle.crt`.
- Replace the image system CA bundle from that file during build when explicitly enabled, and bind-mount the same file read-only at runtime so a restarted container receives trust updates without rebuilding the image.
- Add optional, local-only proxy configuration for credential-free `http`, `socks5`, and `socks5h` endpoints, with an explicitly configured optional `no_proxy` list.
- Propagate configured proxy values to build-stage clients and runtime containers through uppercase and lowercase `HTTP_PROXY`, `HTTPS_PROXY`, `ALL_PROXY`, and, when configured, `NO_PROXY` variables; SOCKS build support is best-effort.
- Validate enabled local corporate-network inputs before Docker execution and fail closed for missing or malformed bundles, unsupported URLs, or embedded proxy credentials.
- Document that this feature does not configure the Docker client/daemon and therefore does not control registry authentication or `FROM` image pulls.

## Capabilities

### New Capabilities
- `corporate-network-configuration`: Local-only credential-free proxy and complete corporate trust-bundle configuration, validation, build propagation, runtime propagation, and scope boundaries.

### Modified Capabilities
- `runtime-host-access`: Extend the closed local companion schema for independent corporate network settings while preserving host access as a protocol-neutral reachability feature.
- `docker-build-reproducibility`: Allow an explicitly enabled local complete trust bundle and local proxy build arguments without placing them in the reviewed dependency inventory.
- `docker-runtime`: Mount the enabled local trust bundle read-only and inject the configured proxy environment into direct runtime launches.

## Impact

Affected areas include `Dockerfile`, the ignored local configuration and build-context convention, constructor local-config parsing/validation, build orchestration and vector rendering, launcher/run-vector rendering, runtime verification, documentation, and focused unit and acceptance tests. Docker daemon/client proxy and trust configuration remain outside the project-managed interface.
