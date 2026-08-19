# Capability: user-cache-storage

## Purpose
Define shared private storage, namespace, security, and migration behavior for persistent constructor caches.

## Requirements

### Requirement: Store persistent constructor caches under a private XDG root
The constructor SHALL use `${XDG_CACHE_HOME}/docker-constructor` as its default persistent cache root when `XDG_CACHE_HOME` is non-empty and absolute. When that explicit XDG directory is missing, the constructor SHALL first create it with owner-only `0700` permissions; when it already exists, it SHALL require it to be a writable directory without changing its permissions. It SHALL use `~/.cache/docker-constructor` only when `XDG_CACHE_HOME` is empty or non-absolute. An explicit absolute XDG path that is a non-directory or not writable SHALL fail with an actionable error and SHALL NOT silently fall back. The constructor SHALL store HTTP update-discovery data only in the `versioning` child and verified runtime artifacts only in the `runtime-artifacts/blobs` child. Runtime projections, evidence, Docker storage, and project files SHALL NOT be treated as persistent constructor caches.

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

#### Scenario: Keeping generated output in the checkout
- **WHEN** a run creates a runtime projection or an evidence command writes evidence
- **THEN** it SHALL retain the repository-local generated-output location
- **AND** it SHALL NOT create those outputs in the user cache root
### Requirement: Secure constructor-owned cache paths
The resolved dedicated constructor cache root and its constructor-created directory descendants SHALL use owner-only `0700` permissions; HTTP cache files SHALL use `0600`, and verified artifact blobs SHALL remain non-writable at `0444`. The constructor SHALL NOT chmod an existing parent of the resolved root, including an existing `XDG_CACHE_HOME`; an explicit missing `XDG_CACHE_HOME` is created as specified by the default-root requirement. Before cache mutation it SHALL reject a symlinked, non-directory, or existing root/descendant that the invoking user cannot secure, with actionable recovery guidance.

#### Scenario: Creating a missing cache subtree
- **WHEN** a required constructor cache root or subtree does not exist
- **THEN** the constructor SHALL create it with owner-only permissions
- **AND** SHALL not alter permissions of any pre-existing parent directory

#### Scenario: Using an existing dedicated local cache root
- **WHEN** `[cache].dir` identifies an existing directory owned by the invoking user
- **THEN** the constructor SHALL require or set its mode to `0700`
- **AND** SHALL NOT alter any parent directory

#### Scenario: Rejecting an unsecurable local cache root
- **WHEN** `[cache].dir` identifies an existing directory that the invoking user does not own or cannot secure
- **THEN** the operation SHALL fail before network, artifact publication, or Docker execution
- **AND** SHALL identify the configured path and instruct the user to choose or create a dedicated owned directory

#### Scenario: Encountering mapped or foreign cache ownership
- **WHEN** an existing constructor cache directory is accessible through group permissions but cannot be set to owner-only mode by the invoking user
- **THEN** the operation SHALL fail before network, artifact publication, or Docker execution
- **AND** the diagnostic SHALL name the offending path and instruct the user to restore ownership or remove that stale cache subtree
### Requirement: Do not implicitly migrate legacy caches
The constructor SHALL NOT read, import, chmod, copy, or delete `.docker-generated/runtime-artifacts` as part of using the new XDG runtime-artifact cache. It SHALL NOT implicitly import, mutate, or delete the legacy `${XDG_CACHE_HOME:-~/.cache}/pi-cli/versioning` HTTP cache when using the new constructor cache root.

#### Scenario: Migrating from the legacy checkout artifact cache
- **WHEN** runtime artifact materialization first uses the new XDG default root
- **THEN** it SHALL treat the new cache as initially empty and materialize selected artifacts normally
- **AND** it SHALL leave the legacy checkout-local artifact cache untouched

#### Scenario: Migrating from the legacy HTTP cache
- **WHEN** update discovery first uses the new constructor cache root
- **THEN** it SHALL use the `docker-constructor/versioning` subtree
- **AND** SHALL NOT implicitly import, mutate, or delete the legacy `pi-cli/versioning` cache
