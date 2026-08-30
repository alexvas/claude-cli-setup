## MODIFIED Requirements

### Requirement: Render a compact deterministic update report by default
The `check-deps` command SHALL render human-readable text by default using exactly the columns `TARGET`, `PROVIDER`, `CURR -> NEXT`, `STATUS`, and `PUBLISHED`. The status SHALL be one of `current`, `update-available`, `metadata-drift`, `integrity-mismatch`, `incomplete`, or `unavailable`. Result ordering and content SHALL not depend on terminal width.

#### Scenario: Rendering ordinary text results
- **WHEN** reconciliation returns results in default text mode
- **THEN** every selected dependency SHALL appear in deterministic order with the fixed compact columns
- **AND** a valid publication timestamp SHALL use `YYYY-MM-DD`, otherwise `-`

#### Scenario: Rendering a build-stage target
- **WHEN** a report or progress message contains a path beginning with `build.stages.`
- **THEN** display SHALL omit exactly that prefix and preserve all other paths

#### Scenario: Rendering current and candidate together
- **WHEN** a result has a distinct candidate
- **THEN** `CURR -> NEXT` SHALL show both values and abbreviate long hexadecimal identifiers using the established format

#### Scenario: Rendering no distinct candidate
- **WHEN** a candidate is absent or equals the selected value
- **THEN** the `CURR -> NEXT` cell SHALL show `<current> -> -`

#### Scenario: Rendering without terminal adaptation
- **WHEN** identical results are rendered under different terminal widths or redirection
- **THEN** report content SHALL not change because of terminal width

### Requirement: Separate reasons from the compact table
The default text report SHALL exclude reason and finding details from table columns and SHALL preserve them in a separate `Details:` section associated with their compact target names.

#### Scenario: Reporting a provider failure
- **WHEN** authority is unavailable with an explanatory reason
- **THEN** the compact row SHALL show `unavailable` and the complete reason SHALL appear under `Details:`

#### Scenario: Reporting an integrity mismatch
- **WHEN** a result has configured and authoritative integrity values that differ
- **THEN** its compact row SHALL show `integrity-mismatch`
- **AND** `Details:` SHALL show the typed integrity kind and both unabridged values

#### Scenario: Reporting results without reasons
- **WHEN** no result has a reason or finding requiring detail
- **THEN** the command SHALL omit the `Details:` section

### Requirement: Provide an explicit detailed text report
The `check-deps --details` option SHALL render `PATH`, `PROVIDER`, `CURRENT`, `CANDIDATE`, `STATUS`, `KIND`, `APPLICABLE`, `PUBLISHED`, and `DETAIL`, retain full target paths, and show valid publication timestamps as `YYYY-MM-DD HH:MM:SS GMT`. It SHALL affect presentation only.

#### Scenario: Requesting detailed text output
- **WHEN** a user runs `check-deps --details`
- **THEN** the report SHALL contain the full diagnostic columns and unabridged paths and findings

#### Scenario: Combining details with suggestions
- **WHEN** a user runs `check-deps --details --suggest`
- **THEN** the command SHALL render both detailed results and review-only replacement suggestions
- **AND** SHALL not change reconciliation or exit policy

### Requirement: Preserve the machine-readable contract
Structured `check-deps` output SHALL expose one primary status and an ordered list of typed findings for each dependency. Findings SHALL preserve configured and authoritative values where relevant, and presentation options SHALL not change structured values, ordering, suggestions, or exit policy.

#### Scenario: Producing JSON output
- **WHEN** JSON output is selected with or without `--details`
- **THEN** stdout SHALL contain complete structured results and suggestions
- **AND** `--details` SHALL introduce no JSON value changes

#### Scenario: Producing multiple findings
- **WHEN** a dependency has an available update and drift in its selected-version metadata
- **THEN** structured output SHALL retain both findings
- **AND** the primary status SHALL be selected by deterministic severity precedence

#### Scenario: Producing JSON with details selected
- **WHEN** JSON output is requested with or without `--details`
- **THEN** both invocations SHALL emit equivalent structured result values

## ADDED Requirements

### Requirement: Classify dependency reconciliation deterministically
A dependency SHALL be `current` only after its selected value and every checked authoritative metadata field agree. Primary status precedence SHALL be `integrity-mismatch`, then `metadata-drift`, then `incomplete`, then `update-available`, then `current`. `unavailable` SHALL be primary when upstream authority cannot be established; independently available local findings SHALL remain attached. Integrity mismatches SHALL use distinct kinds `npm-integrity`, `artifact-sha256`, and `image-digest`.

#### Scenario: Current version with wrong npm integrity
- **WHEN** the selected npm version is latest but its reviewed SRI differs from authoritative `dist.integrity`
- **THEN** the primary status SHALL be `integrity-mismatch`
- **AND** its kind SHALL be `npm-integrity`

#### Scenario: Update and metadata drift coexist
- **WHEN** a newer version exists and selected-version metadata has drifted without an integrity mismatch
- **THEN** both findings SHALL be retained
- **AND** the primary status SHALL be `metadata-drift`

#### Scenario: Upstream is unavailable
- **WHEN** upstream authority cannot be established
- **THEN** the primary status SHALL be `unavailable`
- **AND** the result SHALL NOT be `current`
