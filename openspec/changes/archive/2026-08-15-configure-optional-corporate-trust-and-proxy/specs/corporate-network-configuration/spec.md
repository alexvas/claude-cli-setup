## ADDED Requirements

### Requirement: Configure optional local corporate trust
The system SHALL support an optional `[corporate-trust]` section only in the resolved local companion. `enabled` SHALL be a boolean; absent or `false` SHALL disable corporate trust. When `enabled = true`, the system SHALL require the sole trust source to be the repository-local `.docker-local/corporate-ca-bundle.crt` file, validate that it is readable and contains one or more nonempty PEM `CERTIFICATE` blocks, and reject missing, unreadable, malformed, or unknown local configuration before Docker execution. PEM validation SHALL be dependency-free and SHALL require ASCII input, matching complete `BEGIN CERTIFICATE`/`END CERTIFICATE` delimiters, no non-whitespace content outside those blocks, and strictly decodable nonempty Base64 payloads. It SHALL not parse, verify, or assess payloads as X.509 certificates; certificate validity, trust-chain validity, and organizational trust coverage remain the operator's responsibility. The supplied file SHALL be treated as a complete replacement trust bundle.

#### Scenario: Corporate trust is disabled by default
- **WHEN** the local companion is absent or omits `[corporate-trust]`
- **THEN** build and run SHALL retain the standard image trust store
- **AND** SHALL not require `.docker-local/corporate-ca-bundle.crt`

#### Scenario: Enabled corporate trust has a valid fixed bundle
- **WHEN** the local companion declares `[corporate-trust] enabled = true` and the fixed bundle is valid
- **THEN** build and run planning SHALL use that exact file as the only corporate trust source
- **AND** SHALL not read an arbitrary certificate path from configuration

#### Scenario: Enabled corporate trust has no usable bundle
- **WHEN** corporate trust is enabled and the fixed bundle is missing, unreadable, empty, has incomplete or unmatched certificate delimiters, contains non-whitespace text outside certificate blocks, or has an empty or non-Base64-decodable block payload
- **THEN** the invoking command SHALL fail with a path-specific CONFIG error before Docker execution

#### Scenario: Certificate semantics remain an operator responsibility
- **WHEN** an enabled fixed bundle has complete PEM `CERTIFICATE` blocks with nonempty, strictly decodable Base64 payloads
- **THEN** the invoking command SHALL accept the bundle without an X.509 parser or external Python dependency
- **AND** any invalid certificate object, expired certificate, invalid signature, missing trust root, or incomplete corporate coverage SHALL remain an operator responsibility

### Requirement: Preserve default trust configuration when corporate trust is disabled
When `[corporate-trust]` is absent or `enabled = false`, the constructor SHALL preserve the base image's default certificate and trust configuration. It SHALL NOT add, replace, remove, or override trust bundles, certificate paths, certificate directories, or client-specific CA settings at build or runtime. This prohibition includes, but is not limited to, injecting or persisting `SSL_CERT_FILE`, `SSL_CERT_DIR`, `NODE_EXTRA_CA_CERTS`, `REQUESTS_CA_BUNDLE`, `CURL_CA_BUNDLE`, `GIT_SSL_CAINFO`, `NPM_CONFIG_CAFILE`, or analogous settings for other TLS clients. Values already defined by the selected base image SHALL remain unchanged.

#### Scenario: Disabled trust preserves base-image client behavior
- **WHEN** the local companion omits `[corporate-trust]` or declares `enabled = false`
- **THEN** the Dockerfile, build vector, and run vector SHALL introduce no certificate or trust override
- **AND** SHALL not persist or inject any constructor-defined CA path or client-specific trust setting
- **AND** certificate and trust settings inherited from the selected base image SHALL remain unchanged

### Requirement: Apply enabled trust at build and restarted runtime
When corporate trust is enabled, the Dockerfile SHALL validate and replace `/etc/ssl/certs/ca-certificates.crt` with the fixed complete bundle before image-stage network operations. The constructor SHALL bind-mount the same current host file read-only at that path for each launched container. A restarted or newly launched container SHALL receive a changed bundle without rebuilding the image; already-running containers and processes SHALL not be required to reload it. Any certificate-path or client-specific CA setting introduced by the constructor SHALL be scoped to enabled corporate trust and SHALL point to the replacement system bundle.

#### Scenario: Build uses enabled corporate trust before package downloads
- **WHEN** an enabled trust bundle is used to build the image
- **THEN** base-stage networked package and installer operations SHALL run after the system CA bundle replacement
- **AND** the final image SHALL contain the replacement bundle

#### Scenario: Runtime receives an updated bundle after restart
- **WHEN** the fixed host bundle changes after an image was built and a container is subsequently launched or restarted
- **THEN** the container SHALL receive the current file as a read-only mount at the system CA bundle path
- **AND** the image SHALL not need rebuilding for that launch

### Requirement: Configure optional credential-free local proxy
The system SHALL support an optional `[network.proxy]` section only in the resolved local companion. Its required `url` SHALL be a credential-free URI with an explicit host and port and a scheme of exactly `http`, `socks5`, or `socks5h`; userinfo, fragments, unsupported schemes, missing hosts, missing ports, malformed values, and unknown keys SHALL be rejected before Docker execution. Its optional `no_proxy` value SHALL be emitted only when explicitly configured.

#### Scenario: Proxy is absent by default
- **WHEN** the local companion omits `[network.proxy]`
- **THEN** build and run SHALL not emit proxy or bypass environment variables

#### Scenario: Credential-free external proxy is accepted
- **WHEN** the local companion configures `url = "http://proxy.corp.example:3128"`
- **THEN** build and run planning SHALL accept the endpoint without requiring host-access configuration

#### Scenario: Credential-bearing proxy is rejected
- **WHEN** the configured proxy URL includes URI userinfo such as `user:password@`
- **THEN** the invoking command SHALL fail with a path-specific CONFIG error before Docker execution

### Requirement: Propagate local proxy without persisting it in the image
When a local proxy is configured, the constructor SHALL transport its exact URL into the Docker build through constructor-specific build arguments that cannot be shadowed by same-named proxy `ENV` values inherited from the base image. Before every networked build-stage command, the Dockerfile SHALL conditionally export that URL under `HTTP_PROXY`, `http_proxy`, `HTTPS_PROXY`, `https_proxy`, `ALL_PROXY`, and `all_proxy`, overriding inherited values only on the configured path. An explicitly configured bypass list SHALL similarly be transported through a constructor-specific build argument and conditionally exported under both `NO_PROXY` and `no_proxy`; when omitted, the constructor SHALL introduce neither bypass variable. At runtime, the constructor SHALL propagate the standard proxy variables through direct Docker environment arguments. None of these settings SHALL become persistent image `ENV` values. `socks5` and `socks5h` build operation SHALL be best-effort: a build client that does not support the configured SOCKS URL can fail normally.

#### Scenario: HTTP proxy is propagated in all supported forms
- **WHEN** a credential-free HTTP proxy and explicit bypass list are configured
- **THEN** the build vector SHALL carry the exact values through constructor-specific proxy arguments
- **AND** every networked build-stage command SHALL receive each required uppercase and lowercase standard proxy variable with those values, overriding conflicting inherited proxy settings
- **AND** the run vector SHALL contain each required uppercase and lowercase standard proxy variable with those values
- **AND** the image configuration SHALL not persist proxy `ENV` values

#### Scenario: SOCKS build client rejects the configured proxy
- **WHEN** a build-stage client does not support a configured `socks5` or `socks5h` URL
- **THEN** the build MAY fail with that client's normal operational error
- **AND** the constructor SHALL not reinterpret the endpoint or claim universal SOCKS build support

### Requirement: Preserve Docker daemon/client boundary
The project-managed corporate trust and proxy configuration SHALL apply only to Dockerfile build-stage processes and launched runtime containers. It SHALL NOT configure the Docker client or daemon, registry authentication, image registry trust, or base-image pulls performed for `FROM`.

#### Scenario: Docker pulls require separate host configuration
- **WHEN** a Docker daemon needs proxy or trust configuration to pull a base image
- **THEN** the constructor SHALL not claim that local corporate network configuration controls that operation
- **AND** documentation SHALL identify daemon/client configuration as external to this feature
