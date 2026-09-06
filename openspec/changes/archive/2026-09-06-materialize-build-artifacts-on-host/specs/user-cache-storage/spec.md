## REMOVED Requirements

### Requirement: Store persistent constructor caches under a private XDG root
**Reason**: Checkout-local generated output is replaced by external state keyed to the canonical constructor-project path.

**Migration**: Use the replacement private-cache and external constructor-project-state requirement.

## ADDED Requirements

### Requirement: Store persistent constructor caches and external constructor-project state under private roots
The constructor SHALL use `${XDG_CACHE_HOME}/docker-constructor` as its default persistent cache root when `XDG_CACHE_HOME` is non-empty and absolute. When that explicit XDG directory is missing, the constructor SHALL first create it with owner-only `0700` permissions; when it already exists, it SHALL require it to be a writable directory without changing its permissions. It SHALL use `~/.cache/docker-constructor` only when `XDG_CACHE_HOME` is empty or non-absolute. An explicit absolute XDG path that is a non-directory or not writable SHALL fail with an actionable error and SHALL NOT silently fall back. The constructor SHALL store HTTP update-discovery data only in the `versioning` child and verified runtime artifacts only in the `runtime-artifacts/blobs` child. For operations with a selected constructor project, the constructor SHALL place implicit generated build projections, runtime projections, default evidence output, persistent build artifact blobs, committed build manifests, locks, uncommitted markers, temporary downloads, and per-build snapshots beneath one private namespace rooted at `<resolved-cache-root>/projects/<safe-constructor-project-basename>-<canonical-constructor-project-path-hash-prefix>/`. The namespace identity SHALL be the canonical absolute path of the selected constructor project; primary and extra workspaces are mounted workspaces and SHALL NOT receive separate runtime-projection namespaces during that launch. The safe basename SHALL be a deterministic filesystem-safe rendering used only for discovery, while the complete SHA-256 digest of the canonical constructor-project path SHALL be authoritative identity. Owner-private versioned `project.json` metadata SHALL record that canonical path and complete identity and SHALL be verified before any namespace child is read, created, recovered, or mutated. A short-name collision or mismatched, malformed, unsafe, or missing metadata for an existing namespace SHALL fail without adopting, replacing, or deleting that namespace. Generated files, build-artifact state, and ephemeral transactions SHALL use distinct children, and build-artifact retention SHALL neither inspect nor mutate another constructor-project namespace or the global `runtime-artifacts` and `versioning` namespaces. Per-build snapshots SHALL be removed after success, failure, or later abandoned-transaction recovery. Normal build, run, verification, and default evidence operations SHALL NOT create `.docker-cache`, `.docker-generated`, or another constructor-generated directory beneath the selected constructor project or any primary or extra workspace; an explicit user-selected output destination remains a user-directed output.

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

#### Scenario: Keeping generated output outside the constructor project
- **WHEN** a launch with one selected constructor project and one primary workspace and zero or more extra workspaces creates a runtime projection or an evidence command writes to its default destination
- **THEN** it SHALL use only the external namespace identified by the canonical path of the selected constructor project
- **AND** it SHALL NOT create a separate runtime-projection namespace or generated entry for a workspace merely because it participates in the launch
- **AND** it SHALL NOT mutate the constructor project, primary workspace, or any extra workspace

#### Scenario: Preparing external constructor-project state
- **WHEN** an operation requires generated project state or host-materialized build artifacts
- **THEN** the constructor SHALL resolve and validate the invoking user's configured or default constructor cache root using the existing cache-storage policy
- **AND** SHALL derive one project namespace from the canonical absolute path of the selected constructor project, its safe basename, and its complete path digest
- **AND** SHALL verify or atomically create owner-private identity metadata before creating distinct generated, build-artifact, or transaction children
- **AND** SHALL leave the selected constructor project, primary workspace, and every extra workspace unchanged

#### Scenario: Finding constructor-project state during diagnosis
- **WHEN** an operator inspects `<resolved-cache-root>/projects`
- **THEN** each namespace name SHALL expose the safe basename of its constructor project and a collision-resistant canonical-path-hash prefix
- **AND** its owner-private `project.json` SHALL expose the complete canonical constructor-project path, complete digest identity, and metadata schema version

#### Scenario: Rejecting unsafe or mismatched project state
- **WHEN** a required cache or generated-state path is symlinked, escapes the resolved cache root or selected constructor-project namespace, has an unsafe type or ownership, cannot be secured for the invoking user, or has identity metadata inconsistent with the canonical constructor-project path
- **THEN** the operation SHALL fail before network access, state mutation, publication, container execution, or Docker execution
- **AND** SHALL identify the selected constructor project and namespace without mutating the conflicting entry, constructor project, primary workspace, or any extra workspace

#### Scenario: Isolating workspaces during launch
- **WHEN** one constructor project, one primary workspace, and one or more extra workspaces participate in a launch
- **THEN** runtime projection and launcher-generated control state SHALL exist only beneath the external namespace identified by the canonical path of the selected constructor project
- **AND** no namespace or generated entry SHALL be created for a workspace solely because it was mounted for the launch
- **AND** the constructor project and the primary-workspace directory and all extra-workspace directories SHALL remain unmodified

## ADDED Requirements

### Requirement: Keep host cache state private across the BuildKit boundary
Constructor-created control directories, locks, committed manifests, uncommitted markers, temporary downloads, verified blobs, and transaction snapshots SHALL remain accessible to the invoking host owner without granting host-path traversal to the container `dev` UID. Verified blobs and finalized selected prebuilt-artifact snapshot payloads SHALL be regular non-symlink files with all owner, group, and other write bits removed after atomic publication or finalization. Derived-environment snapshot entries MAY include symlinks only when their assembler canonical evidence identifies them and no-follow validation proves their resolved targets remain contained within that same derived environment; consumer-created derived-environment files MAY be admitted only when their consumer evidence records their exact contents, non-writable mode, target, and containment; all other derived-environment payload files SHALL have all owner, group, and other write bits removed. Verified blobs and finalized selected prebuilt-artifact snapshot files SHALL use mode `0444`, while finalized derived-environment snapshot files SHALL preserve the executable bits validated by their assembler canonical or consumer evidence, and finalized snapshot directories SHALL contain no write bits and SHALL retain only the traversal/read permissions required by the invoking host owner for named-context import. The invoking host user's Docker client SHALL import the selected snapshot as a named context; only after that import SHALL Dockerfile stages expose selected files read-only inside the BuildKit filesystem to a `dev` user whose numeric UID differs from the host owner. Publication and manifest replacement SHALL be atomic, and cache inspection SHALL revalidate digest, containment, type, and permissions before reuse. The constructor SHALL NOT chmod, chown, or otherwise relax the selected constructor project, any primary or extra workspace, their ancestor directories, the user's home directory, or unrelated cache paths.

#### Scenario: Reusing a constructor-project-scoped blob safely
- **WHEN** a selected blob exists in the external namespace identified by the canonical path of the selected constructor project
- **THEN** the constructor SHALL verify containment, regular-file identity, safe permissions, and digest before exposing it to a transaction snapshot

#### Scenario: Finalizing immutable payload permissions
- **WHEN** a verified blob is published or a transaction snapshot is finalized
- **THEN** every verified blob and selected prebuilt-artifact snapshot file SHALL have mode `0444`
- **AND** every derived-environment snapshot regular file SHALL retain the executable bits validated by its assembler canonical or consumer evidence and have all write bits removed
- **AND** a derived-environment snapshot symlink SHALL be admitted only after no-follow validation against its canonical-evidence target and containment within that environment
- **AND** every finalized snapshot directory SHALL have all write bits removed
- **AND** an ordinary write attempt by the host owner SHALL fail unless the owner explicitly changes permissions outside constructor operation

#### Scenario: Rejecting an unsafe derived-environment symlink
- **WHEN** a derived-environment snapshot entry is dangling, escapes its environment, has an unrecorded or evidence-mismatched target, or cannot be no-follow validated
- **THEN** the constructor SHALL reject the snapshot before BuildKit import
- **AND** the symlink target and its payload SHALL NOT enter the final image

#### Scenario: Importing independently of constructor-project ownership
- **WHEN** the invoking user can read and traverse the selected constructor project but does not own its directory or one of its entries
- **THEN** that user's Docker client SHALL import the owner-private snapshot from the constructor project's external namespace into the named BuildKit context
- **AND** the constructor SHALL require ownership of neither the constructor project, primary workspace, nor any extra workspace and SHALL not change any such directory or ancestor ownership or mode

#### Scenario: Reading only after BuildKit import
- **WHEN** the named context has been imported and a build stage runs as `dev` with a numeric UID different from the host owner
- **THEN** `dev` SHALL read the selected artifact copies inside the BuildKit filesystem
- **AND** SHALL have no direct host path to any blob, snapshot, marker, manifest, lock, or cache-control state

#### Scenario: Rejecting an inaccessible host path without permission repair
- **WHEN** the invoking host user cannot traverse or read a required constructor-project, primary-workspace, or extra-workspace input or cannot traverse the external snapshot path
- **THEN** the build SHALL fail before Docker execution with the inaccessible path identified
- **AND** SHALL NOT change permissions or ownership on that path or any ancestor

#### Scenario: Publishing committed state
- **WHEN** a build succeeds
- **THEN** the new owner-only committed manifest SHALL become durable atomically before superseded blobs are deleted
