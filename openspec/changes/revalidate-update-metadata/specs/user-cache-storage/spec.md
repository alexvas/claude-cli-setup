## ADDED Requirements

### Requirement: Persist validated update metadata for revalidation and fallback
The update metadata cache SHALL persist a successful response body only after the owning provider accepts its format, together with request identity, authentication scope, representation scope, ETag and Last-Modified validators when supplied, body fetch time, and last successful validation time. Cache entries SHALL use the existing private `versioning` namespace and SHALL NOT become fresh merely through elapsed-time policy.

#### Scenario: Publishing validated metadata
- **WHEN** an upstream response is successful and the provider validates its format
- **THEN** the cache SHALL atomically publish its body, validators, identity scopes, and timestamps
- **AND** a later matching request MAY use it for conditional revalidation or stale fallback

#### Scenario: Receiving malformed metadata
- **WHEN** upstream returns a successful HTTP response that the provider rejects as malformed
- **THEN** the invalid body SHALL NOT replace the last validated cache entry
- **AND** the prior validated entry MAY be used as explicitly stale fallback with the parse failure as its reason

#### Scenario: Isolating request identities
- **WHEN** request URL, authentication scope, or representation scope differs from a cached entry
- **THEN** that entry SHALL NOT be sent as a validator source or used as stale fallback

#### Scenario: Publishing a multi-request provider response
- **WHEN** a provider makes release-metadata and checksum-asset requests and accepts both response formats
- **THEN** the cache SHALL acknowledge and publish each response independently under its own request identity
- **AND** failure to parse one response SHALL NOT publish that response or prevent separate acknowledgment of another accepted response

### Requirement: Discard the removed TTL cache format
The constructor SHALL provide no compatibility or data migration for the removed TTL response-cache format. Before using the validated metadata cache, it SHALL discard entries that do not use the new format and SHALL repopulate them only from newly fetched provider-validated responses.

#### Scenario: Encountering a removed-format entry
- **WHEN** update discovery finds an entry from the removed TTL cache format
- **THEN** it SHALL discard that entry and query upstream unconditionally
- **AND** SHALL publish a replacement only after receiving and validating a successful response
