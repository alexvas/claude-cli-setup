## MODIFIED Requirements

### Requirement: Suggest reviewed updates without mutation
The version helper SHALL provide `check-updates --suggest` text output containing clearly labelled, complete, manually replaceable TOML fragments for applicable candidate updates and SHALL NOT modify repository files. Each fragment SHALL represent one schema-defined replaceable reviewed inventory block rather than one update target, SHALL include every reviewed leaf and nested table belonging to that block, and SHALL overlay every applicable candidate affecting that block before rendering. Full candidate versions, URLs, and digests SHALL remain unabridged. Text suggestions SHALL remain distinct from the existing structured JSON suggestion representation, whose fields and values SHALL remain unchanged.

#### Scenario: Printing an applicable complete replacement fragment
- **WHEN** a newer applicable release has a version, required artifact, and published digest
- **THEN** `--suggest` SHALL print the normal human-readable update report followed by a labelled complete replacement fragment for the owning reviewed inventory block
- **AND** the fragment SHALL retain unchanged source, update-policy, validation, override, and configured non-updated artifact-platform values from that block
- **AND** it SHALL state that the fragment is intended for manual replacement and is not applied automatically
- **AND** SHALL leave `docker-constructor.toml` and the working tree unchanged
- **AND** substituting the fragment for the complete corresponding block in a canonical inventory SHALL produce a configuration accepted by the ordinary inventory loader

#### Scenario: Combining updates within one replacement block
- **WHEN** two or more applicable update targets belong to the same replaceable reviewed inventory block
- **THEN** `--suggest` SHALL emit exactly one fragment for that block
- **AND** SHALL apply every applicable candidate value to that fragment
- **AND** SHALL NOT emit overlapping duplicate TOML table declarations

#### Scenario: Preserving unmodified platform artifacts
- **WHEN** an applicable candidate updates one platform artifact of a block that declares additional platforms
- **THEN** its replacement fragment SHALL include the updated candidate platform values
- **AND** SHALL retain every other configured platform artifact unchanged

#### Scenario: Displaying visual replacement boundaries
- **WHEN** `--suggest` renders a replacement fragment for canonical path `build.stages.X` or `runtime.X`
- **THEN** the fragment SHALL begin with the visual TOML comment `# --- X ---`
- **AND** every TOML table header in the fragment SHALL retain its complete canonical path
- **AND** the repository canonical inventory SHALL contain the matching visual comment immediately before the corresponding replaceable block
- **AND** missing, altered, or duplicate visual comments in another inventory SHALL NOT affect inventory parsing, validation, update discovery, target grouping, or suggestion construction

#### Scenario: Finding no applicable suggestion
- **WHEN** `--suggest` finds no applicable outdated release
- **THEN** it SHALL report that no reviewable replacement blocks are available
- **AND** it SHALL NOT emit an unlabeled or empty TOML fragment

#### Scenario: Encountering an incomplete release
- **WHEN** a newer release lacks a required artifact or checksum
- **THEN** the helper SHALL describe the missing data
- **AND** SHALL NOT present it as an immediately applicable update
