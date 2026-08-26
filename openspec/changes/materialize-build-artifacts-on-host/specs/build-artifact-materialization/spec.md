## Purpose

Define secure host-side acquisition, transactional BuildKit delivery, and bounded checkout-local retention of reviewed artifacts used to construct Docker images.

## ADDED Requirements

### Requirement: Materialize reviewed build artifacts on the host
Before Docker execution, the constructor SHALL materialize every selected `linux-amd64` rustup, uv, rtk, and fd artifact from its exact reviewed URL, verify its reviewed SHA-256 digest while streaming, and atomically publish valid bytes into a private checkout-local content-addressed cache. A missing, unavailable, malformed, or mismatched artifact SHALL prevent Docker execution, and partial or corrupt downloads SHALL be removed immediately.

#### Scenario: Reusing a verified selected blob
- **WHEN** the selected digest already exists as a safe regular non-writable cache blob and revalidation matches the reviewed digest
- **THEN** the constructor SHALL reuse it without downloading the artifact

#### Scenario: Materializing a cache miss
- **WHEN** a selected digest is absent
- **THEN** the constructor SHALL stream the exact reviewed URL into temporary checkout-local storage
- **AND** SHALL atomically publish it only after the SHA-256 digest matches

#### Scenario: Rejecting an integrity failure
- **WHEN** downloaded bytes do not match the reviewed SHA-256 digest
- **THEN** the build SHALL fail before Docker execution
- **AND** neither the invalid bytes nor a committed cache reference SHALL remain

### Requirement: Deliver only selected artifacts through a named build context
Each non-dry-run build SHALL create an owner-private immutable per-transaction snapshot containing only the selected verified artifacts and a deterministic manifest, then finalize every snapshot file as `0444` and remove every write bit from snapshot directories before named-context import. The invoking host user's Docker client SHALL read that snapshot and pass it as a dedicated BuildKit named context without relaxing checkout or ancestor permissions. Dockerfile stages SHALL obtain imported artifact copies from the named context rather than host cache paths or network URLs, SHALL make those in-build copies readable by the stage user, and SHALL verify each reviewed digest again before installation.

#### Scenario: Rendering a selected build snapshot
- **WHEN** all selected artifacts have been materialized
- **THEN** the build vector SHALL identify the finalized transaction snapshot as the dedicated named context
- **AND** the snapshot SHALL expose stable logical filenames only for selected artifacts
- **AND** its files and directories SHALL have no write bit for owner, group, or other

#### Scenario: Consuming an imported snapshot with a remapped user
- **WHEN** the invoking host user has imported the snapshot into BuildKit and a build stage runs as `dev` under a different numeric UID
- **THEN** `dev` SHALL read the selected copies inside the BuildKit filesystem
- **AND** SHALL not receive a bind mount or direct path to the host snapshot or private cache-control state

#### Scenario: Preserving private host ancestors
- **WHEN** the host owner imports a snapshot located beneath a `0700` checkout or parent directory owned by that host user
- **THEN** named-context import SHALL rely on the host owner's existing access
- **AND** the constructor SHALL NOT broaden permissions on the checkout, its parents, the home directory, or cache roots

#### Scenario: Rendering a dry-run prospective context
- **WHEN** a dry-run renders the planned Docker build
- **THEN** its structured context SHALL be `{ "name": "constructor-artifacts", "state": "prospective", "path": null }`
- **AND** text output SHALL display `--build-context constructor-artifacts=<prospective:not-materialized>` beneath an explicit `Planned build (not executable)` label
- **AND** the value SHALL be presentation metadata rather than a filesystem path or executable argument
- **AND** dry-run SHALL perform no lock acquisition, directory creation, artifact inspection, download, snapshot publication, cache mutation, or Docker capability probe

#### Scenario: Rejecting an unresolved context in execution
- **WHEN** executable argument rendering receives a build plan with any prospective context
- **THEN** it SHALL reject the plan before producing executable argv or invoking Docker
- **AND** SHALL require every named context to be materialized with a real platform-native path

#### Scenario: Rendering prospective context across host platforms
- **WHEN** the same dry-run is rendered under POSIX and Windows host path semantics
- **THEN** its prospective structured context and display token SHALL be byte-identical
- **AND** neither renderer SHALL interpret the display token as a host path

#### Scenario: Lacking named-context support
- **WHEN** Docker does not support BuildKit named contexts
- **THEN** the constructor SHALL fail with actionable prerequisite guidance before artifact download or Docker build execution

#### Scenario: Detecting a boundary integrity failure
- **WHEN** bytes received by a Dockerfile stage do not match the supplied reviewed digest
- **THEN** that stage SHALL fail
- **AND** the artifact SHALL NOT enter the final image

### Requirement: Serialize checkout build transactions
The constructor SHALL permit at most one active image build transaction per checkout. A competing build SHALL fail or wait under a deterministic bounded locking policy without materializing, committing, or garbage-collecting artifacts concurrently.

#### Scenario: Starting a competing build
- **WHEN** another build transaction holds the checkout build lock
- **THEN** the new build SHALL NOT mutate the artifact cache, snapshot state, or committed live set
- **AND** SHALL report that the checkout already has an active build

#### Scenario: Recovering an abandoned transaction
- **WHEN** a later build finds a snapshot whose owning transaction no longer holds a live lock
- **THEN** it SHALL remove the abandoned snapshot before creating its own
- **AND** SHALL leave verified blobs available as uncommitted cache entries

### Requirement: Retain one committed build live set
After and only after a successful Docker build, the constructor SHALL atomically replace the checkout-local committed build manifest with the complete selected build-input digest set. It SHALL then immediately delete every blob removed from the previous committed build set. Shared XDG runtime artifacts SHALL have separate ownership and SHALL NOT be consulted, protected, or deleted by build-cache retention. Existing Docker images SHALL remain independent of source artifact retention, and no image label or historical build generation SHALL be required.

#### Scenario: Committing a successful changed build
- **WHEN** Docker successfully builds an image with a new selected artifact set
- **THEN** the constructor SHALL atomically commit that set
- **AND** SHALL delete every blob superseded from the prior committed build set

#### Scenario: Preserving the prior set after failure
- **WHEN** Docker build fails or is interrupted
- **THEN** the prior committed build manifest and its blobs SHALL remain intact
- **AND** newly verified blobs SHALL remain uncommitted

### Requirement: Expire only abandoned verified artifacts by fixed policy
A verified checkout-local build blob that is not referenced by the committed build set and was never superseded through a successful build commit SHALL be retained as uncommitted for a fixed 30 days (2,592,000 seconds) from its verified publication. Expired uncommitted build blobs and markers SHALL be removed during later build-cache maintenance. The TTL SHALL NOT be configurable through reviewed inventory, local configuration, or command options, and SHALL NOT govern shared XDG runtime artifacts.

#### Scenario: Retrying within the retention period
- **WHEN** a failed build is retried before its verified uncommitted blob is 30 days old
- **THEN** the constructor SHALL reuse the valid blob without downloading it again

#### Scenario: Collecting an expired uncommitted blob
- **WHEN** an unreferenced verified uncommitted blob is older than 2,592,000 seconds
- **THEN** later cache maintenance SHALL remove the blob and its marker

#### Scenario: Protecting a committed build blob from TTL
- **WHEN** a checkout-local blob appears in the committed build set
- **THEN** uncommitted TTL SHALL NOT remove it regardless of file age

#### Scenario: Leaving runtime artifact retention independent
- **WHEN** build-cache commit or GC runs
- **THEN** it SHALL NOT inspect, protect, modify, or delete any shared XDG runtime artifact or infer cross-cache identity
