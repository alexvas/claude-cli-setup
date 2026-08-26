# Capability: update-check-reporting

## Purpose

TBD: Define human-readable update reports and interactive discovery progress.

## Requirements

### Requirement: Render a compact deterministic update report by default
The `check-updates` command SHALL render human-readable text by default using exactly the columns `TARGET`, `PROVIDER`, `CURR -> NEXT`, `STATUS`, and `PUBLISHED`, without selecting columns, arbitrarily truncating non-identifier values, or deriving layout from terminal width. The status cell SHALL retain the serialized update status. Current and candidate SHALL share the cell under the `CURR -> NEXT` heading and SHALL be rendered as `<current> -> <candidate>`; when candidate is absent or equal to current, the candidate portion SHALL be displayed as `-`. A valid authoritative UTC publication timestamp SHALL be shown as `YYYY-MM-DD`, and an absent or invalid timestamp as `-`.

#### Scenario: Rendering ordinary text results
- **WHEN** update discovery returns current, outdated, and unavailable results in text mode without `--details`
- **THEN** the command SHALL render each result in the fixed compact column set
- **AND** SHALL preserve deterministic result ordering
- **AND** SHALL render a valid publication timestamp as `YYYY-MM-DD`

#### Scenario: Rendering a build-stage target
- **WHEN** a compact report or progress message contains a path beginning with `build.stages.`
- **THEN** the displayed target SHALL omit exactly that leading prefix
- **AND** paths without that leading prefix SHALL remain unchanged

#### Scenario: Rendering current and candidate together
- **WHEN** a result has a distinct candidate
- **THEN** the `CURR -> NEXT` cell SHALL show `<current> -> <candidate>`
- **AND** a long hexadecimal identifier SHALL be abbreviated to its first five hexadecimal characters followed by `...`, retaining any `sha256:` prefix

#### Scenario: Rendering no distinct candidate
- **WHEN** a candidate is absent or equals current
- **THEN** the `CURR -> NEXT` cell SHALL show `<current> -> -`

#### Scenario: Rendering without terminal adaptation
- **WHEN** the same structured results are rendered under terminals of different widths or with redirected output
- **THEN** the final report content SHALL not change because of the detected terminal width

### Requirement: Separate reasons from the compact table
The default text report SHALL exclude reason text from table columns and SHALL preserve non-empty reasons in a separate `Details:` section associated with their compact target names.

#### Scenario: Reporting a provider failure
- **WHEN** a provider result is unavailable with an explanatory reason
- **THEN** its compact table row SHALL show the original unavailable status without embedding the reason
- **AND** the complete reason SHALL appear under `Details:` after the table

#### Scenario: Reporting results without reasons
- **WHEN** no result contains a non-empty reason
- **THEN** the command SHALL omit the `Details:` section

### Requirement: Provide an explicit detailed text report
The `check-updates --details` option SHALL render the established full diagnostic text columns: `PATH`, `PROVIDER`, `CURRENT`, `CANDIDATE`, `STATUS`, `KIND`, `APPLICABLE`, `PUBLISHED`, and `DETAIL`. It SHALL retain full target paths and render a valid authoritative UTC publication timestamp as `YYYY-MM-DD HH:MM:SS GMT`. The option SHALL affect presentation only.

#### Scenario: Requesting detailed text output
- **WHEN** a user runs `check-updates --details` in text mode
- **THEN** the report SHALL contain the full diagnostic column set and full target paths
- **AND** SHALL render a valid publication timestamp as `YYYY-MM-DD HH:MM:SS GMT` rather than shortening it to a date

#### Scenario: Combining details with suggestions
- **WHEN** a user runs `check-updates --details --suggest`
- **THEN** the command SHALL render the detailed report and the established review-only suggestions section
- **AND** SHALL not change candidate selection or applicability

### Requirement: Preserve the machine-readable contract
Compact and detailed text presentation SHALL NOT change the structured JSON result contract, suggestion values, update ordering, exit policies, or provider discovery behavior.

#### Scenario: Producing JSON output
- **WHEN** a user selects JSON output with or without `--details`
- **THEN** stdout SHALL contain the established complete structured result and suggestion fields
- **AND** the `--details` option SHALL introduce no JSON field or value changes

### Requirement: Show interactive sequential discovery progress
During sequential update discovery, the command SHALL show the selected target index, total selected targets after scope and `--only` filtering, compact target name, and provider on a transient stderr line only when output is text and stderr is a TTY. Progress SHALL be observational and SHALL NOT become part of structured result data.

#### Scenario: Checking updates interactively
- **WHEN** text output is selected, stderr is a TTY, and a selected target is about to be resolved
- **THEN** stderr SHALL display progress in the form `Checking updates [N/T] TARGET (PROVIDER)…`
- **AND** N SHALL be one-based and T SHALL be the total number of selected targets

#### Scenario: Completing interactive discovery
- **WHEN** interactive discovery finishes successfully or exits through a handled error or interruption
- **THEN** the transient progress line SHALL be cleared before final report or diagnostic output is emitted

#### Scenario: Running non-interactively
- **WHEN** stderr is not a TTY
- **THEN** the command SHALL emit no progress output

#### Scenario: Producing JSON interactively
- **WHEN** JSON output is selected even if stderr is a TTY
- **THEN** the command SHALL emit no progress output
- **AND** stdout SHALL remain valid standalone JSON

#### Scenario: Preserving sequential discovery
- **WHEN** progress reporting is enabled
- **THEN** provider discovery SHALL remain sequential and results SHALL retain selected-target order
- **AND** progress observation SHALL not alter provider errors or classifications
