## MODIFIED Requirements

### Requirement: Store persistent constructor caches under a private XDG root
The constructor SHALL use `${XDG_CACHE_HOME}/docker-constructor` as its default persistent cache root when `XDG_CACHE_HOME` is non-empty and absolute. When that explicit XDG directory is missing, the constructor SHALL first create it with owner-only `0700` permissions; when it already exists, it SHALL require it to be a writable directory without changing its permissions. It SHALL use `~/.cache/docker-constructor` only when `XDG_CACHE_HOME` is empty or non-absolute. An explicit absolute XDG path that is a non-directory or not writable SHALL fail with an actionable error and SHALL NOT silently fall back. The constructor SHALL store HTTP update-discovery data only in the `versioning` child and verified runtime artifacts only in the `runtime-artifacts/blobs` child. Runtime projections SHALL be stored beneath `.docker-generated/` in the selected constructor project and SHALL NOT be stored in the persistent user cache. Evidence SHALL be stored beneath the selected project's `.docker-generated/evidence/` directory by default but MAY be directed to any explicitly supplied `--output-dir`, regardless of that directory's location. Evidence SHALL NOT be treated as constructor-managed cache content, and the constructor SHALL NOT place it in the persistent user cache by default. Docker storage and project files SHALL NOT be treated as persistent constructor caches.

#### Scenario: Using a valid existing XDG cache home
- **WHEN** no local cache-root override is configured and `XDG_CACHE_HOME` is non-empty, absolute, and identifies a writable directory
- **THEN** update discovery SHALL use `${XDG_CACHE_HOME}/docker-constructor/versioning`
- **AND** runtime artifact materialization, dry-run inspection, and artifact mount planning SHALL use `${XDG_CACHE_HOME}/docker-constructor/runtime-artifacts/blobs`
- **AND** SHALL NOT change permissions on the existing `XDG_CACHE_HOME` directory

#### Scenario: Creating a missing explicit XDG cache home
- **WHEN** no local cache-root override is configured and `XDG_CACHE_HOME` is non-empty, absolute, and missing
- **THEN** the constructor SHALL create `XDG_CACHE_HOME` with owner-only `0700` permissions before creating its `docker-constructor` child
- **AND** SHALL use that child's `versioning` and `runtime-artifacts/blobs` paths

#### Scenario: Falling back from an absent or relative XDG cache home
- **WHEN** no local cache-root override is configured and `XDG_CACHE_HOME` is empty or non-absolute
- **THEN** update discovery SHALL use `~/.cache/docker-constructor/versioning`
- **AND** runtime artifact materialization, dry-run inspection, and artifact mount planning SHALL use `~/.cache/docker-constructor/runtime-artifacts/blobs`

#### Scenario: Rejecting an unusable explicit XDG cache home
- **WHEN** no local cache-root override is configured and absolute `XDG_CACHE_HOME` identifies a non-directory or is not writable
- **THEN** the operation SHALL fail before cache mutation, network, artifact publication, or Docker execution
- **AND** SHALL identify `XDG_CACHE_HOME` and SHALL NOT fall back to `~/.cache`

#### Scenario: Keeping runtime projections in the selected constructor project
- **WHEN** a run creates a runtime projection
- **THEN** it SHALL store the projection beneath `.docker-generated/` in the selected constructor project
- **AND** it SHALL NOT store the projection in the constructor installation checkout or the persistent user cache

#### Scenario: Keeping evidence in the selected constructor project by default
- **WHEN** an evidence command runs without `--output-dir`
- **THEN** it SHALL store evidence in `<project-directory>/.docker-generated/evidence/`
- **AND** it SHALL NOT store evidence in the constructor installation checkout or the persistent user cache

#### Scenario: Directing evidence to an explicit output directory
- **WHEN** an evidence command runs with `--output-dir DIR`
- **THEN** it SHALL store evidence in `DIR` regardless of whether `DIR` is beneath `XDG_CACHE_HOME`, another cache-like location, or any other valid location
- **AND** the explicit path SHALL NOT change the selected constructor project root or the location of any other project-owned file
- **AND** the evidence SHALL remain caller-directed output rather than constructor-managed cache content
