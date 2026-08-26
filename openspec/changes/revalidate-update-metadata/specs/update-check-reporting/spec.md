## ADDED Requirements

### Requirement: Report update metadata freshness independently
Every structured update result SHALL identify metadata freshness as exactly one of `fresh`, `stale`, `unavailable`, or `not-applicable`. `fresh` and `stale` apply to results derived from one or more HTTP metadata responses; `unavailable` applies when an HTTP-backed provider cannot obtain every required response and has no validated fallback for at least one required request; `not-applicable` applies when the provider uses no HTTP metadata, including `git-ref`, or exits before making an HTTP request. A stale result SHALL include provenance for every stale contributing response. Freshness SHALL NOT alter result status, candidate, applicability, ordering, suggestions, or exit policy.

#### Scenario: Rendering structured fresh metadata
- **WHEN** an update result was derived from HTTP metadata and every required response was freshly fetched or successfully conditionally validated
- **THEN** its structured result SHALL identify the metadata as fresh
- **AND** a `304 Not Modified` validation SHALL be fresh rather than stale

#### Scenario: Rendering structured stale metadata
- **WHEN** an update result was derived from HTTP metadata and at least one required response used validated stale fallback while no required response was unavailable
- **THEN** its structured result SHALL identify the metadata as stale
- **AND** SHALL include the fallback reason and relevant fetch and validation-attempt times for every stale response

#### Scenario: Rendering unavailable HTTP freshness
- **WHEN** an HTTP-backed provider cannot obtain a required response and has no validated fallback for that request
- **THEN** its structured result SHALL identify metadata freshness as unavailable

#### Scenario: Rendering non-HTTP freshness
- **WHEN** a provider such as `git-ref` uses no HTTP metadata
- **THEN** its structured result SHALL identify metadata freshness as not-applicable

### Requirement: Preserve compact output while disclosing stale fallback
Text output SHALL preserve the established compact table columns and version status values. For each stale result it SHALL add a complete diagnostic under `Details:` naming the compact target, the fact that cached metadata was used, its age or fetch time, and the failed validation reason; the summary SHALL disclose the number of stale results.

#### Scenario: Showing stale compact output
- **WHEN** compact text output contains one or more stale results
- **THEN** the compact table SHALL retain exactly its established columns
- **AND** the summary SHALL report the stale-result count
- **AND** `Details:` SHALL disclose stale provenance for every affected target

#### Scenario: Showing only fresh output
- **WHEN** all update metadata was freshly fetched or conditionally validated
- **THEN** no stale warning SHALL be rendered
