## ADDED Requirements

### Requirement: Keep build artifact state inside its checkout
Persistent build artifact blobs, committed build manifests, locks, and uncommitted markers SHALL reside beneath a constructor-owned checkout-local cache directory. Per-build snapshots SHALL reside beneath checkout-local generated state and SHALL be removed after success, failure, or later abandoned-transaction recovery. Build artifact state SHALL NOT use the shared XDG constructor cache or a configurable cache root.

#### Scenario: Preparing checkout-local build state
- **WHEN** a build requires host-materialized artifacts
- **THEN** the constructor SHALL create or validate private persistent and generated subtrees under the resolved checkout
- **AND** SHALL not place build blobs in the shared `runtime-artifacts` or `versioning` namespaces

#### Scenario: Rejecting unsafe checkout cache paths
- **WHEN** a required cache or generated-state path is symlinked, escapes the checkout, has an unsafe type, or cannot be secured for the invoking user
- **THEN** the build SHALL fail before network access, cache mutation, or Docker execution

### Requirement: Keep host cache state private across the BuildKit boundary
Constructor-created control directories, locks, committed manifests, uncommitted markers, temporary downloads, verified blobs, and transaction snapshots SHALL remain accessible to the invoking host owner without granting host-path traversal to the container `dev` UID. Verified blobs and finalized snapshot payloads SHALL be regular non-symlink files with all owner, group, and other write bits removed after atomic publication or finalization; verified blob and finalized snapshot files SHALL use mode `0444`, while finalized snapshot directories SHALL contain no write bits and SHALL retain only the traversal/read permissions required by the invoking host owner for named-context import. The invoking host user's Docker client SHALL import the selected snapshot as a named context; only after that import SHALL Dockerfile stages expose selected files read-only inside the BuildKit filesystem to a `dev` user whose numeric UID differs from the host owner. Publication and manifest replacement SHALL be atomic, and cache inspection SHALL revalidate digest, containment, type, and permissions before reuse. The constructor SHALL NOT chmod, chown, or otherwise relax the checkout root, any ancestor directory, the user's home directory, or unrelated cache paths.

#### Scenario: Reusing a checkout blob safely
- **WHEN** a selected blob exists in the checkout cache
- **THEN** the constructor SHALL verify containment, regular-file identity, safe permissions, and digest before exposing it to a transaction snapshot

#### Scenario: Finalizing immutable payload permissions
- **WHEN** a verified blob is published or a transaction snapshot is finalized
- **THEN** every payload file SHALL have mode `0444`
- **AND** every finalized snapshot directory SHALL have all write bits removed
- **AND** an ordinary write attempt by the host owner SHALL fail unless the owner explicitly changes permissions outside constructor operation

#### Scenario: Importing beneath a private checkout ancestor
- **WHEN** the checkout or one of its ancestors has mode `0700` and is owned by the invoking host user
- **THEN** that host user's Docker client SHALL import the selected snapshot into the named BuildKit context
- **AND** the constructor SHALL leave every checkout and ancestor mode unchanged

#### Scenario: Reading only after BuildKit import
- **WHEN** the named context has been imported and a build stage runs as `dev` with a numeric UID different from the host owner
- **THEN** `dev` SHALL read the selected artifact copies inside the BuildKit filesystem
- **AND** SHALL have no direct host path to any blob, snapshot, marker, manifest, lock, or cache-control state

#### Scenario: Rejecting an inaccessible host path without permission repair
- **WHEN** the invoking host user cannot traverse the checkout or snapshot path
- **THEN** the build SHALL fail before Docker execution with the inaccessible path identified
- **AND** SHALL NOT change permissions or ownership on that path or any ancestor

#### Scenario: Publishing committed state
- **WHEN** a build succeeds
- **THEN** the new owner-only committed manifest SHALL become durable atomically before superseded blobs are deleted
