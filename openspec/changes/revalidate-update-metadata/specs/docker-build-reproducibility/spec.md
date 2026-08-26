## ADDED Requirements

### Requirement: Revalidate update metadata on every explicit check
Each selected HTTP-backed update query SHALL contact its upstream on every `check-updates` invocation. When a validated cached response has an `ETag` or `Last-Modified` validator, the query SHALL send the corresponding conditional request; when no validator exists, it SHALL perform a full request. A cache entry SHALL NOT suppress the upstream request based on its age.

#### Scenario: Revalidating with an ETag
- **WHEN** a selected provider has a validated cached response with an ETag
- **THEN** update discovery SHALL send `If-None-Match` for that response
- **AND** a `304 Not Modified` response SHALL make the cached body freshly validated for this invocation

#### Scenario: Revalidating with a modification time
- **WHEN** a selected provider has a validated cached response with no ETag and a Last-Modified value
- **THEN** update discovery SHALL send `If-Modified-Since` for that response

#### Scenario: Querying without a validator
- **WHEN** a selected provider has no cached validator
- **THEN** update discovery SHALL perform a full upstream request
- **AND** SHALL NOT reuse a cached body merely because a configured duration has not elapsed

### Requirement: Fall back explicitly to validated stale metadata
When an update request fails because of a transport error, timeout, HTTP 408, HTTP 429, or HTTP 5xx response, or when a fresh HTTP 200 body is rejected by the owning provider's metadata parser, update discovery SHALL use a previously provider-validated response for the same request identity when available and SHALL mark every result derived from it as stale. A parser rejection means that provider metadata cannot be decoded or does not satisfy the provider's response schema; it is distinct from an artifact, checksum, signature, or other integrity failure. Discovery SHALL preserve the version classification and applicability derived from the cached body while recording the fallback reason, cached-body fetch time, and current validation-attempt time. Non-retryable identity, authentication, authorization, not-found, and integrity failures SHALL NOT be hidden by stale fallback.

#### Scenario: Using stale metadata after a transient failure
- **WHEN** revalidation returns HTTP 504 and a previously validated response exists for the same request identity
- **THEN** discovery SHALL derive results from that cached response
- **AND** SHALL mark those results stale with the HTTP 504 reason

#### Scenario: Falling back after malformed fresh metadata
- **WHEN** upstream returns HTTP 200 for the same request identity, the owning provider rejects that fresh body as malformed, and a previously provider-validated response exists
- **THEN** discovery SHALL leave the malformed body uncommitted
- **AND** SHALL derive results from the prior response as stale with the parser rejection as the fallback reason

#### Scenario: Preserving integrity failures
- **WHEN** an artifact, checksum, signature, or other integrity check fails
- **THEN** discovery SHALL report that failure
- **AND** SHALL NOT substitute cached provider metadata

#### Scenario: Having no stale fallback
- **WHEN** a transient request failure or fresh-body parser rejection occurs and no validated cached response exists
- **THEN** the provider result SHALL remain unavailable under the existing best-effort policy

#### Scenario: Rejecting fallback for a non-retryable response
- **WHEN** upstream returns HTTP 401, HTTP 404, or another non-retryable failure
- **THEN** discovery SHALL report that failure
- **AND** SHALL NOT substitute cached metadata

#### Scenario: Preserving version policy under fallback
- **WHEN** stale metadata produces a current or outdated result
- **THEN** its status, candidate, applicability, suggestions, and policy exit behavior SHALL be computed by the same rules as fresh metadata
- **AND** freshness SHALL remain an independent property

### Requirement: Aggregate multi-request metadata provenance deterministically
A provider that makes multiple HTTP requests SHALL track and acknowledge each request independently. Each successful fresh body SHALL be acknowledged only after the owning parser accepts that response, and each stale fallback SHALL retain its own request identity, reason, body fetch time, and validation-attempt time. The final result SHALL be `unavailable` when any required request has neither a valid fresh response nor a validated fallback; otherwise it SHALL be `stale` when any required response is stale, and `fresh` only when every required response is fresh. A non-HTTP provider or a provider that exits before making an HTTP request SHALL be `not-applicable` for HTTP metadata freshness.

#### Scenario: Aggregating fresh release metadata and stale checksum metadata
- **WHEN** a provider freshly validates release metadata and uses stale fallback for a required checksum asset response
- **THEN** it SHALL acknowledge the two responses independently
- **AND** the final update result SHALL be stale with the checksum response's fallback provenance

#### Scenario: Aggregating an unavailable required subrequest
- **WHEN** one required response is fresh or stale but another required HTTP request fails without validated fallback
- **THEN** the final provider result SHALL be unavailable
- **AND** its metadata freshness SHALL be unavailable

#### Scenario: Acknowledging multiple fresh responses
- **WHEN** a provider parses fresh release metadata and a fresh required checksum response
- **THEN** it SHALL acknowledge each accepted body under its own request identity
- **AND** the final result SHALL be fresh

#### Scenario: Classifying a non-HTTP provider
- **WHEN** `git-ref` completes through its Git transport without an HTTP metadata request
- **THEN** its version result SHALL retain the existing classification
- **AND** its metadata freshness SHALL be not-applicable

### Requirement: Bypass all metadata cache behavior explicitly
`check-updates --no-cache` SHALL neither read cached metadata or validators nor write responses, validators, or timestamps, and SHALL never use stale fallback.

#### Scenario: Running without cache
- **WHEN** the user runs `check-updates --no-cache`
- **THEN** every selected HTTP provider SHALL perform an unconditional upstream request
- **AND** no metadata cache entry SHALL be read, created, refreshed, or used as fallback

## MODIFIED Requirements

### Requirement: Keep cache directory paths machine-local
The reviewed `docker-constructor.toml` SHALL NOT accept `cache.dir`; a custom dedicated constructor cache root SHALL be read only from an absolute `[cache].dir` in the resolved local TOML companion. When it is absent, cache consumers SHALL use `${XDG_CACHE_HOME}/docker-constructor` when `XDG_CACHE_HOME` is non-empty and absolute, creating a missing XDG directory with `0700` or requiring an existing writable directory; they SHALL use `~/.cache/docker-constructor` only when XDG is empty or non-absolute, and SHALL reject an explicit absolute non-directory or unwritable XDG path without fallback. Cache consumers SHALL derive their separate named subdirectories beneath the resolved root rather than storing unrelated cache formats in one directory. The reviewed inventory SHALL NOT contain HTTP cache freshness or TTL configuration.

#### Scenario: Migrating a reviewed cache directory
- **WHEN** validation encounters `cache.dir` in `docker-constructor.toml`
- **THEN** it SHALL reject the field as unsupported without migration instructions
- **AND** SHALL NOT copy, merge, or prefer the reviewed path

#### Scenario: Resolving cache settings from separate sources
- **WHEN** local `[cache].dir` is configured and update metadata caching is enabled by normal command behavior
- **THEN** cache consumers SHALL use the local directory as the dedicated constructor cache root without resolving any reviewed TTL or freshness setting
- **AND** the local value SHALL NOT enter an effective build or runtime projection

#### Scenario: Separating cache formats under a local root
- **WHEN** a local `[cache].dir` is configured
- **THEN** update-discovery HTTP cache data SHALL use its `versioning` child
- **AND** verified runtime artifacts SHALL use its `runtime-artifacts/blobs` child

#### Scenario: Rejecting the removed HTTP-only command-line cache directory
- **WHEN** a user supplies unsupported `check-updates --cache-dir`
- **THEN** command-line parsing SHALL reject the supplied option as unsupported
- **AND** SHALL NOT interpret it, select a cache path, or migrate cache data

## REMOVED Requirements

### Requirement: Keep cache TTL in reviewed policy
**Reason**: Metadata freshness is now established by an upstream request or conditional revalidation on every explicit check; a TTL can hide newly published versions and is no longer part of the update-discovery contract.

**Migration**: None. This pre-release project does not preserve compatibility for `[cache].ttl` or legacy TTL cache entries; both are removed outright.
