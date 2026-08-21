## ADDED Requirements

### Requirement: Resolve an explicit physical parent-project chain
A schema-1 reviewed inventory MAY declare one top-level `parent-project` string. The constructor SHALL interpret an absolute value directly and a relative value from the directory containing the declaring inventory, without CWD, tilde, environment-variable, installation-root, or ancestor-discovery fallback. Every referenced physical directory SHALL contain the fixed regular file `docker-constructor.toml`. The complete chain SHALL contain no more than 32 project layers including the selected leaf.

#### Scenario: Resolve portable relative parents at each level
- **WHEN** a leaf and an intermediate project each declare a relative `parent-project`
- **THEN** each reference SHALL resolve relative to its own declaring project directory
- **AND** every resolved project directory SHALL be normalized to an absolute physical path before use

#### Scenario: Resolve an absolute parent
- **WHEN** `parent-project` contains an absolute directory path
- **THEN** the constructor SHALL physically normalize that directory and load its fixed `docker-constructor.toml`

#### Scenario: Reject unsupported reference forms
- **WHEN** a parent reference uses tilde or environment interpolation, resolves to a missing or non-directory entry, lacks the fixed inventory, or exceeds 32 layers
- **THEN** the command SHALL fail with a path-specific CONFIG diagnostic before project mutation, network access, artifact materialization, or Docker execution

### Requirement: Detect physical cycles and aliases
The constructor SHALL identify each parent inventory by its physical canonical path and, on POSIX systems, by the device and inode obtained from the same no-follow regular-file descriptor used to read it. A repeated identity SHALL be rejected as a cycle or physical alias, including references expressed through different lexical paths or hard links. Symlinked path components MAY be physically normalized, but the inventory leaf SHALL be a regular file rather than a symlink.

#### Scenario: Reject a lexical parent cycle
- **WHEN** following parent references reaches an inventory canonical path already present in the current chain
- **THEN** the constructor SHALL reject the chain and report the cycle in traversal order

#### Scenario: Reject a hard-linked inventory alias on POSIX
- **WHEN** two different canonical inventory paths in one chain identify the same POSIX device and inode
- **THEN** the constructor SHALL reject the second path as a physical alias
- **AND** SHALL identify both paths in the diagnostic

#### Scenario: Normalize a symlinked project path
- **WHEN** a parent reference traverses a symlinked directory to a regular inventory
- **THEN** the constructor SHALL use the resolved physical project and inventory identities for subsequent chain, asset, and Dockerfile processing

### Requirement: Merge globally disjoint reviewed settings
The constructor SHALL merge raw TOML from terminal base to leaf with one owner for every non-metadata leaf path. Tables SHALL be structural, arrays SHALL be atomic leaf values, and `schema` plus `parent-project` SHALL be merge metadata. Repeating any other leaf path at different levels SHALL fail even when both values are equal. The terminal base and every accumulated effective prefix SHALL pass the closed typed inventory schema before the next layer is accepted.

#### Scenario: Merge distinct settings across shared tables
- **WHEN** different project layers declare different leaf paths beneath a shared TOML table
- **THEN** the merged inventory SHALL contain every distinct value
- **AND** each value SHALL retain one source owner for diagnostics

#### Scenario: Reject a repeated leaf setting
- **WHEN** a child declares a scalar or array leaf path already declared by any ancestor
- **THEN** composition SHALL fail with both owning inventory paths
- **AND** identical values SHALL NOT suppress the conflict

#### Scenario: Reject an invalid effective prefix
- **WHEN** the base is valid but adding an intermediate or leaf fragment violates the typed schema or semantic constraints
- **THEN** the command SHALL identify the layer whose effective prefix first becomes invalid

### Requirement: Materialize the merged reviewed inventory before overrides
After successful composition, the constructor SHALL deterministically serialize the validated merged raw mapping as `docker-constructor.toml` in the private build context. The serialized mapping SHALL contain schema metadata once, SHALL omit every `parent-project` reference, and SHALL contain no value introduced only by CLI overrides. The serialized file SHALL pass the ordinary inventory loader. Existing effective projection and Docker build-argument paths SHALL continue to carry validated CLI overrides.

#### Scenario: Materialize a complete merged inventory
- **WHEN** a valid parent chain is prepared for build
- **THEN** the context `docker-constructor.toml` SHALL contain the explicitly reviewed settings from every layer
- **AND** SHALL contain no `parent-project` key
- **AND** reloading that file SHALL produce a valid inventory

#### Scenario: Keep overrides outside the merged reviewed inventory
- **WHEN** otherwise identical builds use different valid CLI overrides
- **THEN** their materialized merged `docker-constructor.toml` content SHALL remain identical
- **AND** their effective projections and Docker arguments SHALL reflect their respective overrides

### Requirement: Compose only explicit reviewed and leaf-local asset namespaces
For each project layer, only the optional regular directory `docker-assets/` SHALL contribute inherited reviewed build inputs. The composed context SHALL merge its regular files and directories at the same relative paths. Only the selected leaf's optional `.docker-assets-local/` SHALL contribute machine-local build inputs, and the context SHALL contain that directory even when no source directory exists. Parent local companions, parent local assets, `.env`, generated outputs, and arbitrary project-root files SHALL NOT be inherited or copied.

#### Scenario: Compose disjoint reviewed assets
- **WHEN** multiple layers contain distinct regular files under `docker-assets/`
- **THEN** the private context SHALL contain their union under `docker-assets/`
- **AND** SHALL preserve empty directories and file permission bits

#### Scenario: Keep local assets leaf-only
- **WHEN** parent and leaf projects contain `.docker-assets-local/`
- **THEN** only the leaf directory contents SHALL enter the context
- **AND** parent local contents SHALL not be inspected as inherited assets

#### Scenario: Materialize an absent local asset directory
- **WHEN** the leaf has no `.docker-assets-local/`
- **THEN** the composed context SHALL contain an empty owner-private `.docker-assets-local/` directory

#### Scenario: Reject unsupported asset entries
- **WHEN** an inherited or leaf-local asset root is a symlink or contains a symlink, socket, FIFO, device, or other non-regular entry
- **THEN** validation and build SHALL fail before Docker execution

### Requirement: Reject cross-layer asset ambiguity
Asset manifests SHALL be validated before application of `.dockerignore`. Equal relative file paths, file/directory type conflicts, and POSIX physical file aliases across different layers SHALL fail. Shared directories SHALL be permitted only when their `0o777` permission bits agree. Hard links within one layer MAY represent distinct logical paths but SHALL be copied as independent files. Path identity SHALL be exact and case-sensitive.

#### Scenario: Reject a duplicate asset path
- **WHEN** two project layers contain a regular file at the same path relative to `docker-assets/`
- **THEN** validation SHALL fail with the relative path and both physical owners regardless of file contents

#### Scenario: Reject conflicting asset types or directory modes
- **WHEN** one layer declares a file where another requires a directory, or shared directories have different permission bits
- **THEN** validation SHALL fail with the conflicting path, types or modes, and owners

#### Scenario: Reject a cross-layer hard-link alias on POSIX
- **WHEN** distinct asset paths owned by different layers identify the same POSIX device and inode
- **THEN** validation SHALL reject the physical alias

#### Scenario: Preserve an intra-layer hard-link layout logically
- **WHEN** two paths in one asset layer are hard links to one regular file
- **THEN** both logical paths SHALL be accepted
- **AND** the context SHALL contain independent regular-file snapshots at both paths

### Requirement: Select nearest child Docker controls
Build SHALL select the first existing `Dockerfile` while traversing leaf to base. An existing non-regular candidate SHALL fail rather than fall back, and absence across all layers SHALL fail build. The sole `.dockerignore` SHALL come from the selected Dockerfile's project when present; it SHALL NOT be inherited independently, merged, or rewritten. Other Dockerfiles and ignore files SHALL not be assets.

#### Scenario: Inherit the nearest available Dockerfile
- **WHEN** the leaf lacks a Dockerfile and more than one ancestor supplies one
- **THEN** build SHALL use the Dockerfile from the nearest supplying ancestor
- **AND** SHALL use only that ancestor's `.dockerignore` when it exists

#### Scenario: Prefer a child Dockerfile
- **WHEN** both child and parent supply regular Dockerfiles
- **THEN** build SHALL use the child Dockerfile and ignore the parent's Dockerfile and `.dockerignore`

#### Scenario: Reject an invalid Docker control
- **WHEN** the nearest existing Dockerfile or its same-layer `.dockerignore` is not a regular file
- **THEN** validation and build SHALL fail without falling back to another layer

#### Scenario: Preserve project-owned ignore semantics
- **WHEN** the selected `.dockerignore` excludes a generated or composed context path
- **THEN** the constructor SHALL NOT add an implicit negation or otherwise rewrite that ignore policy

### Requirement: Validate and snapshot a private composed context safely
`validate` SHALL resolve and validate the chain, every effective prefix, Docker controls, and complete asset manifests without creating a context, accessing the network, or invoking Docker. An executed non-dry build SHALL repeat those checks and snapshot the allowlisted inputs under the leaf `.docker-generated/build-contexts/` from no-follow descriptors, rejecting source mutation during copying. `build --dry-run` SHALL perform the same read-only chain, control, local-policy, and manifest validation and SHALL plan the private context path in memory without materializing it. Snapshot files SHALL preserve `0o777` permission bits but not source ownership, ACLs, xattrs, timestamps, special mode bits, or hard-link topology.

#### Scenario: Validate a composed project without effects
- **WHEN** `validate` runs for a parented constructor project
- **THEN** it SHALL report configuration, control-file, asset-type, path, mode, and identity errors without creating generated output or invoking Docker

#### Scenario: Reject an asset changed during snapshot
- **WHEN** an asset's verified identity or relevant metadata changes while its content is copied
- **THEN** build SHALL fail with a path-specific mutation diagnostic
- **AND** SHALL not execute Docker with a mixed snapshot

#### Scenario: Restrict the context allowlist
- **WHEN** an executed build materializes a valid chain
- **THEN** the private context SHALL contain only the selected Docker controls, merged inventory, composed `docker-assets/`, and leaf `.docker-assets-local/`
- **AND** SHALL not contain source inventories, local companions, parent local assets, or unrelated project-root files

#### Scenario: Plan a composed dry run without effects
- **WHEN** `build --dry-run` targets a valid standalone or parented project
- **THEN** it SHALL resolve and validate the chain, effective prefixes, Docker controls, local policy, and complete asset manifests
- **AND** SHALL plan the private context path in memory for the rendered Docker vector
- **AND** SHALL NOT create a context, acquire a build lock, perform stale cleanup, create or publish generated files, invoke Docker, or mutate project or filesystem state

### Requirement: Serialize per-leaf executed-build publication and context lifecycle
Only one executed non-dry build SHALL hold the exclusive lock for a leaf project at a time. The lock SHALL be acquired before effective build-projection publication or any other executed-build write to a fixed path beneath leaf `.docker-generated/`, and SHALL remain held through safe stale-context cleanup, context materialization, Docker execution, and deletion of the current context. A waiting build SHALL NOT overwrite the effective projection or another fixed generated output belonging to the build currently executing. Caller-directed outputs outside the fixed leaf-generated layout SHALL retain their explicit destinations. Dry runs SHALL not acquire the lock, publish a projection, or enter cleanup. Cleanup SHALL remain beneath the fixed leaf context root, accept only constructor-owned names and regular directories, and SHALL not follow symlinks. Different leaf projects SHALL remain independently buildable.

#### Scenario: Serialize executed builds of one leaf
- **WHEN** two non-dry builds target the same leaf project concurrently
- **THEN** only one SHALL publish fixed generated outputs or enter the context and Docker lifecycle at a time

#### Scenario: Preserve the executing build projection
- **WHEN** one leaf build has published its effective projection and is still executing Docker while a second build with different overrides waits
- **THEN** the first build's projection SHALL remain unchanged until its Docker execution and context cleanup complete
- **AND** the waiting build SHALL publish its projection only after acquiring the released leaf lock

#### Scenario: Keep different leaves independent
- **WHEN** non-dry builds target different leaf projects
- **THEN** their project locks SHALL not serialize one another

#### Scenario: Clean a failed or interrupted build context
- **WHEN** materialization or Docker execution fails or the process receives a handled interruption
- **THEN** the constructor SHALL make a best-effort deletion of its own private context before releasing the lock

#### Scenario: Reject unsafe stale cleanup entries
- **WHEN** stale cleanup encounters a symlink, special entry, unexpected name, or path outside the fixed context root
- **THEN** it SHALL refuse to follow or recursively delete that entry
- **AND** SHALL fail with an actionable path-specific diagnostic

### Requirement: Keep non-build consumers scoped to their needs
Commands that consume reviewed configuration SHALL resolve and validate the merged chain. Commands other than `validate` and `build` SHALL not require Dockerfile selection or asset scanning solely because a parent exists. `show` SHALL retain its public merged-data shape without embedding provenance, while conflict diagnostics SHALL identify source owners. `run` SHALL consume merged runtime policy and leaf-only machine-local state without asserting that an existing image matches current parent build settings.

#### Scenario: Run with inherited runtime policy
- **WHEN** runtime settings are inherited from one or more parents
- **THEN** run SHALL use the merged runtime policy
- **AND** SHALL resolve local companion state only from the selected leaf

#### Scenario: Use a configuration-only command without assets
- **WHEN** a non-build, non-validate command selects a valid chain whose layers do not supply a Dockerfile or asset root
- **THEN** the command SHALL not fail solely because those build inputs are absent

#### Scenario: Diagnose ownership without changing show output
- **WHEN** composition finds a repeated setting or asset
- **THEN** the diagnostic SHALL identify both owners
- **AND** successful `show` output SHALL not add provenance fields to its existing data shape
