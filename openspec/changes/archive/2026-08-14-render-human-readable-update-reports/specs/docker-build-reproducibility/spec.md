## MODIFIED Requirements

### Requirement: Discover dependency updates explicitly
The version helper SHALL provide an explicit best-effort `check-updates` operation, including the dedicated `uv-python` provider for uv-managed CPython. Normal builds, launches, validation, and runtime setup SHALL NOT invoke update-provider APIs. Its text output SHALL present a deterministic human-readable summary and per-dependency report rather than a serialized Python data structure.

#### Scenario: Checking for stable updates
- **WHEN** `./docker/docker-constructor.py check-updates` runs
- **THEN** it SHALL query each configured provider for stable candidates
- **AND** SHALL report current, outdated, skipped, unavailable, or incomplete status per dependency
- **AND** its text output SHALL summarize result statuses and render each dependency's path, provider, current value, candidate, status, kind, applicability, authoritative publication time, and available detail in a deterministic report
- **AND** SHALL abbreviate a long hexadecimal revision, digest, or checksum in text-mode `CURRENT` and `CANDIDATE` cells to its first five hexadecimal characters followed by `...`, while retaining any `sha256:` prefix
- **AND** SHALL render `-` rather than repeat a candidate exactly equal to the current value
- **AND** default execution SHALL not fail solely because an update exists or a provider is unavailable

#### Scenario: Reporting publication time
- **WHEN** the selected candidate has an authoritative release/version publication time from its provider
- **THEN** the text report SHALL show it as `YYYY-MM-DD HH:MM:SS GMT`
- **AND** the structured JSON result SHALL retain the complete value as an additive optional field when it uses the supported UTC RFC 3339 profile `YYYY-MM-DDTHH:MM:SS[.fraction](Z|+00:00)`, where `.fraction`, when present, contains one through six decimal digits
- **AND** SHALL show `-` when the provider has no authoritative release/version publication time or supplies a malformed or unsupported timestamp; lowercase `t`/`z` forms and leap seconds are unsupported
- **AND** SHALL NOT infer publication time from response, cache, Git commit, or later supplemental artifact-upload timestamps

#### Scenario: Checking release applicability
- **WHEN** a provider reports a newer prebuilt release
- **THEN** the helper SHALL verify required architecture assets and checksum metadata are available before marking it directly applicable

#### Scenario: Distinguishing a base digest refresh
- **WHEN** the selected Docker base tag resolves to a different manifest digest
- **THEN** the helper SHALL report a digest refresh separately from a major or channel upgrade

### Requirement: Suggest reviewed updates without mutation
The version helper SHALL provide `check-updates --suggest` text output containing a clearly labelled, reviewable TOML fragment for applicable candidate values and SHALL NOT modify repository files.

#### Scenario: Printing an applicable suggestion
- **WHEN** a newer applicable release has a version, required artifact, and published digest
- **THEN** `--suggest` SHALL print the normal human-readable update report followed by a labelled TOML fragment containing the candidate version, URL, and digest
- **AND** it SHALL state that the fragment is review-only and is not applied automatically
- **AND** SHALL leave `docker-constructor.toml` and the working tree unchanged
- **AND** SHALL retain full unabridged candidate versions, URLs, and digests in the TOML fragment

#### Scenario: Finding no applicable suggestion
- **WHEN** `--suggest` finds no applicable outdated release
- **THEN** it SHALL report that no reviewable TOML changes are available
- **AND** it SHALL NOT emit an unlabeled or empty TOML fragment

#### Scenario: Encountering an incomplete release
- **WHEN** a newer release lacks a required artifact or checksum
- **THEN** the helper SHALL describe the missing data
- **AND** SHALL NOT present it as an immediately applicable update
