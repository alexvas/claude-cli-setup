## MODIFIED Requirements

### Requirement: Discover dependency updates explicitly
The version helper SHALL provide an explicit `check-deps` operation that reconciles only dependencies declaratively managed by `docker-constructor.toml` with their authoritative upstream sources, including the dedicated `uv-python` provider for uv-managed CPython. It SHALL check selected versions or revisions and provider-verifiable reviewed artifact metadata only for records whose active schema declares such metadata. For managed Pi extension roots, ordinary `check-deps` SHALL use a dedicated root-version provider whose sole authority is `https://registry.npmjs.org/`, compare each exact reviewed root version with its latest eligible stable version, and neither fetch nor reconcile tarball URL/SRI metadata. Ordinary `check-deps` SHALL NOT resolve or read a transitive lockfile closure, require removed managed-extension runtime artifact URLs or SRI fields, create a runtime catalog or blob cache, or modify a checked-in lockfile. It SHALL exclude transitive dependency discovery, vulnerability analysis, and license analysis. Normal builds, launches, offline validation, and runtime setup SHALL NOT invoke provider APIs. Reporting SHALL conform to `update-check-reporting`.

#### Scenario: Checking for stable updates
- **WHEN** `./docker/docker-constructor.py check-deps` runs
- **THEN** it SHALL query each selected provider for stable candidates and authoritative metadata for the selected version
- **AND** SHALL report every selected managed dependency using the statuses defined by `update-check-reporting`
- **AND** SHALL not inspect unrelated project dependencies, vulnerabilities, or licenses

#### Scenario: Requesting detailed diagnostic output
- **WHEN** `./docker/docker-constructor.py check-deps --details` runs in text mode
- **THEN** it SHALL select the detailed report defined by `update-check-reporting`
- **AND** SHALL NOT change reconciliation, findings, suggestions, ordering, or exit policy

#### Scenario: Checking an unscoped managed root without lock resolution
- **WHEN** ordinary `check-deps` processes an exact unscoped managed root `<name>@<version>`
- **THEN** its dedicated root-version provider SHALL request package metadata only from `https://registry.npmjs.org/<name>` and compare the reviewed version with the latest eligible stable version
- **AND** SHALL NOT fetch or compare tarball URL/SRI metadata, invoke npm dependency resolution, read closure packages, or modify the checked-in lockfile

#### Scenario: Checking a scoped managed root without lock resolution
- **WHEN** ordinary `check-deps` processes an exact scoped managed root `@<scope>/<name>@<version>`
- **THEN** its dedicated root-version provider SHALL request package metadata only from `https://registry.npmjs.org/@<scope>%2F<name>` and compare the reviewed version with the latest eligible stable version
- **AND** SHALL NOT derive registry authority from a runtime artifact URL, scope mapping, runtime catalog, projection, or blob cache

#### Scenario: Failing to establish managed-root authority
- **WHEN** the fixed public-registry request fails or its package metadata cannot establish the latest eligible stable root version
- **THEN** ordinary `check-deps` SHALL report the managed root as `unavailable`
- **AND** SHALL NOT fall back to a custom registry, removed runtime artifact URL, transitive lock data, or npm resolution

#### Scenario: Checking metadata for a current npm version
- **WHEN** an artifact-backed npm dependency record whose active schema declares a reviewed tarball URL and SRI has a configured version equal to the latest eligible version
- **THEN** the ordinary artifact-backed npm provider SHALL still retrieve that exact version's authoritative tarball URL and integrity
- **AND** SHALL compare both values with the selected reviewed artifact entry
- **AND** SHALL NOT apply this metadata check to a managed root whose closure is owned by a checked-in lockfile

#### Scenario: Reporting publication time
- **WHEN** the selected candidate has an authoritative release/version publication time from its provider
- **THEN** text presentation SHALL format it according to `update-check-reporting`
- **AND** structured output SHALL retain a valid supported UTC RFC 3339 value without inferring one from unrelated timestamps

#### Scenario: Checking release applicability
- **WHEN** a provider reports a newer prebuilt release
- **THEN** the helper SHALL verify required architecture assets and integrity metadata before marking it directly applicable

#### Scenario: Distinguishing a base digest refresh
- **WHEN** the selected Docker base tag resolves to a different manifest digest
- **THEN** the helper SHALL report an integrity mismatch with the image-digest kind

### Requirement: Suggest reviewed updates without mutation
The version helper SHALL provide `check-deps --suggest` text output containing clearly labelled, complete, manually replaceable TOML fragments for applicable version updates and metadata corrections, and SHALL NOT modify repository files. Each fragment SHALL represent one schema-defined replaceable reviewed inventory block, retain unaffected reviewed leaves, and overlay all applicable authoritative values affecting that block.

#### Scenario: Printing an applicable complete replacement fragment
- **WHEN** a newer applicable release has all required authoritative metadata
- **THEN** `--suggest` SHALL propose that version and its authoritative artifact metadata in one complete replacement fragment

#### Scenario: Correcting metadata without changing version
- **WHEN** a selected current artifact-backed npm record has schema-declared reviewed tarball URL or integrity different from its authoritative registry metadata
- **THEN** `--suggest` SHALL retain the selected version
- **AND** SHALL replace the URL and integrity together from that exact registry version record
- **AND** SHALL NOT emit a tarball URL or SRI TOML correction for a lockfile-owned managed root

#### Scenario: Suggesting a managed root version update
- **WHEN** the fixed public-registry root-version provider finds a newer eligible stable version for a managed Pi extension root
- **THEN** ordinary `check-deps --suggest` SHALL propose only the new exact reviewed root version
- **AND** SHALL NOT include tarball URL, integrity, transitive closure, or lockfile edits in that suggestion
- **AND** SHALL leave the reviewed inventory, checked-in lockfiles, transitive closure, and working tree unchanged

#### Scenario: Combining updates within one replacement block
- **WHEN** multiple applicable findings belong to one replaceable reviewed block
- **THEN** `--suggest` SHALL emit one non-overlapping fragment containing all applicable authoritative values

#### Scenario: Preserving unmodified platform artifacts
- **WHEN** one platform artifact changes in a block with additional platforms
- **THEN** the fragment SHALL update that platform and retain all others unchanged

#### Scenario: Displaying visual replacement boundaries
- **WHEN** a replacement fragment is rendered
- **THEN** it SHALL begin with the established visual comment and retain complete canonical TOML paths

#### Scenario: Colouring a visual replacement boundary in a terminal
- **WHEN** `check-deps --suggest` renders text to a terminal with colour enabled
- **THEN** only the visual comment header SHALL use the established ANSI styling

#### Scenario: Preserving plain replacement fragments without terminal colour
- **WHEN** colour is disabled, stdout is non-terminal, or JSON output is selected
- **THEN** replacement data SHALL contain no ANSI escape sequences

#### Scenario: Finding no applicable suggestion
- **WHEN** no applicable update or metadata correction exists
- **THEN** `--suggest` SHALL report that no reviewable replacement block is available
- **AND** SHALL NOT emit an empty fragment

#### Scenario: Encountering an incomplete release
- **WHEN** a candidate lacks required artifact metadata
- **THEN** the helper SHALL describe the missing data
- **AND** SHALL NOT suggest it as applicable

#### Scenario: Preserving review-only operation
- **WHEN** any suggestion is rendered
- **THEN** the fragment SHALL be suitable for manual whole-block replacement and ordinary inventory validation
- **AND** `docker-constructor.toml` and the working tree SHALL remain unchanged

## ADDED Requirements

### Requirement: Resolve npm authority from the reviewed registry
For an artifact-backed npm dependency record whose active schema includes a reviewed runtime artifact URL and SRI, `check-deps` SHALL derive the metadata registry base from the complete reviewed artifact URL rather than unconditionally using the public npm registry or reducing the URL to its origin. This requirement SHALL apply only to that ordinary artifact-backed npm provider contract. Given the known package identity, an eligible HTTPS artifact path SHALL match exactly `/(<prefix>/)*<name>/-/<leaf>.tgz` for an unscoped package or `/(<prefix>/)*@<scope>/<name>/-/<leaf>.tgz` for a scoped package, where the prefix has zero or more non-empty canonical segments and the tarball leaf is non-empty. The URL SHALL contain no userinfo, query, or fragment. Empty or dot segments, duplicate separators, percent-encoded separators or package structure, non-canonical package segments, a package suffix inconsistent with the known identity, and a malformed `/-/<leaf>.tgz` suffix SHALL be rejected before network access.

`check-deps` SHALL remove the exact terminal package/tarball suffix to obtain the registry base while preserving every registry path-prefix segment. It SHALL construct the metadata endpoint as `<base>/<name>` for an unscoped package and `<base>/@<scope>%2F<name>` for a scoped package. It SHALL prohibit all npm registry credentials. Before cache or provider activity, it SHALL detect supported credential/configuration entities only by case-insensitive environment-variable name or by existence at a predetermined npm-config path. Supported environment entities SHALL include `NPM_TOKEN`, `NODE_AUTH_TOKEN`, `NPM_CONFIG_USERCONFIG`, and every `NPM_CONFIG_*` name whose normalized npm key denotes `_auth`, `_authToken`, `username`, `_password`, `password`, `otp`, `certfile`, or `keyfile`, including registry- and scope-qualified forms. Supported config entities SHALL include only conventional project, user, and global npm config files at their predetermined paths. `NPM_CONFIG_USERCONFIG` SHALL be detected and reported only by variable name; `check-deps` SHALL NOT read its value or discover, test, or report the explicitly selected path. `check-deps` SHALL NOT read matching credential environment values or config-file bytes. When entities are present, it SHALL warn with every safe variable name or predetermined config path, state that they are ignored, remove matching variables from provider/transport inputs, load no npm config, and continue credential-free. A warning for `NPM_CONFIG_USERCONFIG` SHALL state that the variable and the config it selects are ignored without naming the unknown selected path. When none are present, it SHALL emit no credential/config warning. Sanitization SHALL complete before the first registry request, and values, file contents, encoded secrets, and secret-derived data SHALL NOT enter diagnostics, cache identity, provider state, or requests. Metadata requests SHALL follow only a bounded chain of same-origin HTTPS redirects: origin is the normalized scheme, host, and effective port and is only the redirect-security boundary; every hop SHALL be validated before its request is sent; and any cross-origin redirect, HTTPS-to-HTTP downgrade, malformed or unsupported Location, credential-bearing URL, or redirect-limit excess SHALL be rejected.

#### Scenario: Deriving public unscoped package metadata
- **WHEN** a reviewed artifact URL is `https://registry.npmjs.org/example/-/example-1.0.0.tgz` for package `example`
- **THEN** `check-deps` SHALL request metadata from `https://registry.npmjs.org/example`

#### Scenario: Deriving public scoped package metadata
- **WHEN** a reviewed artifact URL is `https://registry.npmjs.org/@scope/example/-/example-1.0.0.tgz` for package `@scope/example`
- **THEN** `check-deps` SHALL request metadata from `https://registry.npmjs.org/@scope%2Fexample`

#### Scenario: Preserving a registry path prefix
- **WHEN** a reviewed artifact URL is `https://registry.example/npm/virtual/@scope/example/-/example-1.0.0.tgz` for package `@scope/example`
- **THEN** `check-deps` SHALL request metadata from `https://registry.example/npm/virtual/@scope%2Fexample`
- **AND** SHALL treat metadata from that prefixed endpoint as authoritative for comparison

#### Scenario: Rejecting encoded package structure
- **WHEN** a reviewed artifact path represents a separator or package structure with percent encoding, including `%2F`, `%5C`, or an encoded scope/package boundary
- **THEN** `check-deps` SHALL reject the artifact URL before making a registry request
- **AND** SHALL NOT decode and reinterpret the path as another registry base

#### Scenario: Rejecting malformed path segments
- **WHEN** a reviewed artifact path contains an empty segment, duplicate separator, or `.` or `..` segment
- **THEN** `check-deps` SHALL reject the artifact URL before making a registry request

#### Scenario: Rejecting a malformed package suffix
- **WHEN** a reviewed artifact path names a different package than the known package identity or lacks the exact `/-/<leaf>.tgz` suffix
- **THEN** `check-deps` SHALL reject the artifact URL before making a registry request
- **AND** SHALL NOT guess a registry base from a shorter path prefix

#### Scenario: Rejecting non-path URL components
- **WHEN** a reviewed artifact URL contains userinfo, a query, or a fragment
- **THEN** `check-deps` SHALL reject the artifact URL before making a registry request

#### Scenario: Ignoring direct npm token variables
- **WHEN** `NPM_TOKEN` or `NODE_AUTH_TOKEN` is present for `check-deps`
- **THEN** the command SHALL identify the variable by name without reading its value
- **AND** SHALL warn that the named entity is ignored
- **AND** SHALL continue credential-free after removing it from provider and transport inputs

#### Scenario: Ignoring auth-related npm configuration variables
- **WHEN** an auth-related `NPM_CONFIG_*` or `npm_config_*` variable is present, including a registry- or scope-qualified auth token, username, password, OTP, certificate, key, or userconfig entity
- **THEN** the command SHALL identify every matching variable by safe name without reading any value
- **AND** SHALL sanitize all matching variables before the first registry request
- **AND** when the variable is `NPM_CONFIG_USERCONFIG`, SHALL warn that the variable and its selected config are ignored without discovering, testing, or reporting the selected path

#### Scenario: Ignoring npm configuration files
- **WHEN** a conventional project, user, or global npm config file exists at its predetermined path
- **THEN** the command SHALL identify the config by safe path without reading its bytes
- **AND** SHALL warn that the config is ignored
- **AND** SHALL not load or project the config during reconciliation

#### Scenario: Warning about multiple ignored entities
- **WHEN** multiple supported credential/config entities are present
- **THEN** one or more warnings SHALL enumerate every ignored entity by safe variable name or config path
- **AND** SHALL contain no value, file content, encoded secret, or secret-derived data

#### Scenario: Running without ignored credential entities
- **WHEN** no supported npm credential/config entity is present
- **THEN** `check-deps` SHALL emit no credential/config warning
- **AND** SHALL perform the same credential-free reconciliation

#### Scenario: Verifying the sanitized request boundary
- **WHEN** ignored credential/config entities are present and `check-deps` proceeds to npm metadata retrieval
- **THEN** sanitization SHALL complete before the first registry request
- **AND** provider state, transport inputs, cache identity, diagnostics, and requests SHALL contain none of their values, contents, or secret-derived data
- **AND** authenticated npm registry access SHALL remain unsupported

#### Scenario: Following a same-origin redirect
- **WHEN** a validated HTTPS metadata request receives a bounded redirect to the same normalized origin
- **THEN** `check-deps` SHALL validate the hop and request the redirect target

#### Scenario: Rejecting a cross-origin redirect before follow
- **WHEN** a metadata request receives a redirect to another normalized origin
- **THEN** `check-deps` SHALL reject it before sending a request to that target

#### Scenario: Rejecting unsafe redirect targets
- **WHEN** any redirect hop downgrades HTTPS, exceeds the redirect limit, or has a malformed, unsupported, or userinfo-bearing Location
- **THEN** `check-deps` SHALL reject the redirect before sending its next request

#### Scenario: Validating every redirect hop
- **WHEN** a metadata redirect chain contains multiple hops
- **THEN** `check-deps` SHALL validate every hop against the original allowed origin before following it

#### Scenario: Registry metadata cannot be obtained
- **WHEN** the exact package/version metadata cannot be safely retrieved or validated without npm registry credentials
- **THEN** the dependency SHALL be `unavailable` or `incomplete` as appropriate
- **AND** SHALL NOT be reported as `current`

#### Scenario: Excluding lockfile-owned managed roots
- **WHEN** ordinary `check-deps` processes a managed npm root whose complete closure is owned by a checked-in lockfile
- **THEN** it SHALL use only the fixed-public-registry root-version provider and SHALL NOT invoke this artifact-backed npm metadata provider, derive registry authority from a removed runtime artifact URL, or compare or suggest reviewed tarball URL/SRI fields
- **AND** closure resolution and lockfile publication SHALL remain outside the ordinary `check-deps` reconciliation contract

### Requirement: Protect fixed-public-registry managed-root metadata transport
The managed-root version provider SHALL issue credential-free metadata requests only from exact initial URLs beneath `https://registry.npmjs.org/`, with normalized allowed origin `https://registry.npmjs.org:443`. Its provider/transport boundary SHALL accept only explicit request inputs and SHALL NOT receive, inspect, detect, load, or interpret npm environment variables, `.npmrc` files, npm scope mappings, npm credential/configuration state, ambient HTTP authentication, `.netrc`, or a cookie jar. Request headers SHALL be constructed from a closed allowlist that excludes `Authorization`, `Proxy-Authorization`, and `Cookie`; optional proxy and CA inputs SHALL enter only through their separately validated credential-free policy. Neither initial nor redirected requests SHALL contain URL userinfo or credential/config-derived request data. The production transport SHALL disable automatic redirects and follow only a bounded chain of HTTPS redirects whose normalized origin remains exactly the allowed public-registry origin. It SHALL validate every Location before sending the next request and reject malformed or unsupported URLs, userinfo, HTTP downgrade, cross-origin targets, and redirect-limit exhaustion. A rejected redirect SHALL NOT be requested or stored as a successful metadata cache entry.

#### Scenario: Requesting protected unscoped root metadata
- **WHEN** ordinary `check-deps` checks managed root `example`
- **THEN** the provider SHALL make a credential-free request to `https://registry.npmjs.org/example`
- **AND** SHALL use `https://registry.npmjs.org:443` as the redirect-security boundary

#### Scenario: Requesting protected scoped root metadata
- **WHEN** ordinary `check-deps` checks managed root `@scope/example`
- **THEN** the provider SHALL make a credential-free request to `https://registry.npmjs.org/@scope%2Fexample`
- **AND** SHALL NOT apply an ambient scope registry mapping

#### Scenario: Excluding ambient credential and npm configuration ingress from root metadata
- **WHEN** ambient npm credentials, npm configuration variables or files, scope mappings, HTTP authentication state, `.netrc`, or cookies exist outside a managed-root metadata check
- **THEN** the provider and transport SHALL neither receive nor inspect those ambient inputs and SHALL emit no warning derived from their presence
- **AND** the request SHALL be constructed only from explicit allowlisted credential-free inputs without authorization or cookie headers
- **AND** ambient values, contents, paths, and secret-derived data SHALL remain absent from provider state, cache identity, diagnostics, and requests

#### Scenario: Following a same-origin public-registry redirect
- **WHEN** managed-root metadata receives a bounded HTTPS redirect whose normalized origin is `https://registry.npmjs.org:443` and whose URL is otherwise valid
- **THEN** the transport SHALL validate the Location before requesting it
- **AND** SHALL follow it without adding credentials

#### Scenario: Rejecting an unsafe managed-root redirect before follow
- **WHEN** managed-root metadata receives a redirect that is cross-origin, downgrades to HTTP, contains userinfo, is malformed or unsupported, or exceeds the hop limit
- **THEN** the transport SHALL reject it before sending the next request
- **AND** SHALL NOT cache the rejected target as successful metadata

### Requirement: Apply dependency reconciliation exit policy
`check-deps` SHALL exit successfully only when every result is `current` or `update-available`. Any `metadata-drift`, `integrity-mismatch`, `incomplete`, or `unavailable` result SHALL produce a non-zero command exit.

#### Scenario: Reporting only available updates
- **WHEN** every dependency is current or has only an available version update
- **THEN** `check-deps` SHALL exit zero

#### Scenario: Reporting unverifiable or inconsistent dependencies
- **WHEN** any dependency has drifted metadata, mismatched integrity, incomplete metadata, or unavailable validation
- **THEN** `check-deps` SHALL exit non-zero
