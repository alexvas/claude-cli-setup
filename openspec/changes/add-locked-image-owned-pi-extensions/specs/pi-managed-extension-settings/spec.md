## Purpose

Define crash-safe reconciliation of image-owned managed roots with user-owned Pi package settings.

## ADDED Requirements

### Requirement: Reconcile managed roots through one recoverable settings transaction
The settings reconciler SHALL be the sole owner of managed-root registration and duplicate handling. It SHALL reconcile active `~/.pi/agent/settings.json` and constructor-owned `~/.pi/agent/docker-constructor-managed-extensions.json` sidecar as one logical transaction. The sidecar SHALL contain a schema version, ownership marker, a `managedEntries` collection identifying each active constructor-owned root and exact local source, a distinct `suppressedBaselines` collection containing exact suppressed user entries with their placement anchors and fallback index, and transaction state with operation, phase, and expected pre/post settings fingerprints. A baseline entry SHALL retain its complete JSON value, including object-form filters and additional fields; it SHALL not be reduced to package name or version. Active settings SHALL remain the source of truth for new user changes. Each file replacement SHALL be durable and atomic. Immediately before replacing active settings, the reconciler SHALL use a settings lock or compare-and-swap revalidation against the read settings identity; on conflict it SHALL not replace settings and SHALL retry from current settings or report a recoverable conflict. The reconciler SHALL preserve every unrelated settings entry and its relative order.

#### Scenario: Preserving non-duplicate user entries
- **WHEN** Pi settings contain user npm, git, or local entries alongside managed entries
- **THEN** reconciliation SHALL leave every non-duplicate entry and its relative ordering unchanged
- **AND** SHALL modify only constructor-owned entries and qualifying duplicate npm entries

#### Scenario: Retaining a complete baseline entry
- **WHEN** a qualifying npm entry uses the object form with filters or additional fields
- **THEN** the sidecar SHALL retain its complete JSON value and placement anchors
- **AND** restoration SHALL recreate that value without reducing it to a source string

#### Scenario: Detecting a concurrent settings change
- **WHEN** a user or Pi process changes active settings after reconciliation reads them and before replacement
- **THEN** the reconciler SHALL not overwrite that change
- **AND** SHALL retry from current settings or report a recoverable conflict

#### Scenario: Publishing duplicate suppression
- **WHEN** a qualifying duplicate user npm entry is found
- **THEN** the reconciler SHALL durably publish a prepared sidecar transaction containing its exact baseline form before replacing active settings
- **AND** SHALL atomically replace active settings without that entry
- **AND** SHALL durably finalize the sidecar as suppressed only after the active-settings replacement succeeds

### Requirement: Register constructor-owned managed roots as exact local packages
For every reviewed managed root, the reconciler SHALL place exactly one string entry in `settings.json.packages`. An unscoped root `<name>` SHALL use `/opt/pi-extensions/node_modules/<name>` and a scoped root `@<scope>/<name>` SHALL use `/opt/pi-extensions/node_modules/@<scope>/<name>`. The reconciler SHALL NOT register `/opt/pi-extensions/node_modules` itself or any transitive package path. Each constructor-owned entry SHALL have a corresponding sidecar `managedEntries` record containing the exact reviewed root identity and canonical local path. These records SHALL remain distinct from `suppressedBaselines`, which contain user-owned entries and restoration metadata.

Reconciliation SHALL compute the desired managed root set and idempotently add missing entries, retain exactly one matching owned entry, replace stale owned paths, and remove owned entries for removed roots. A local-path entry SHALL NOT be treated as constructor-owned solely because its path resembles a managed path; ownership SHALL require the matching sidecar record. After reconciliation, acceptance SHALL require Pi package discovery to load every managed root's declared resources and resolve its transitive imports from the image-owned `/opt/pi-extensions/node_modules` closure.

#### Scenario: Registering an unscoped managed root
- **WHEN** reviewed roots contain unscoped package `example`
- **THEN** `settings.json.packages` SHALL contain exactly one constructor-owned string `/opt/pi-extensions/node_modules/example`
- **AND** `managedEntries` SHALL map root `example` to that exact path

#### Scenario: Registering a scoped managed root
- **WHEN** reviewed roots contain scoped package `@scope/example`
- **THEN** `settings.json.packages` SHALL contain exactly one constructor-owned string `/opt/pi-extensions/node_modules/@scope/example`
- **AND** `managedEntries` SHALL map root `@scope/example` to that exact path

#### Scenario: Registering only reviewed roots
- **WHEN** the image-owned closure contains reviewed roots and transitive packages
- **THEN** reconciliation SHALL register one path per reviewed root
- **AND** SHALL NOT register the common `node_modules` directory or any transitive package path

#### Scenario: Repeating reconciliation idempotently
- **WHEN** active settings and sidecar already contain the exact desired managed entries
- **THEN** reconciliation SHALL leave their values and order unchanged
- **AND** SHALL NOT add a duplicate entry

#### Scenario: Updating the managed root set
- **WHEN** a reviewed root is added or an owned canonical path becomes stale
- **THEN** reconciliation SHALL atomically add the missing entry or replace the stale owned entry
- **AND** SHALL update `managedEntries` in the same logical transaction

#### Scenario: Removing a managed root registration
- **WHEN** a root is removed from the reviewed set
- **THEN** reconciliation SHALL atomically remove its constructor-owned local-path entry and `managedEntries` record
- **AND** SHALL perform any user-baseline restoration independently through `suppressedBaselines`

#### Scenario: Preserving a user-owned local path
- **WHEN** active settings contain a path resembling a managed package path without a matching `managedEntries` ownership record
- **THEN** reconciliation SHALL treat it as user-owned
- **AND** SHALL NOT remove or rewrite it as stale constructor state

#### Scenario: Separating active ownership from suppressed baselines
- **WHEN** a managed root suppresses one or more duplicate user npm entries
- **THEN** `managedEntries` SHALL contain only the root identity and active canonical local path
- **AND** `suppressedBaselines` SHALL separately retain each complete user JSON value and restoration placement metadata

#### Scenario: Loading registered managed extensions after reconciliation
- **WHEN** reconciliation registers a valid managed root and Pi performs package discovery
- **THEN** Pi SHALL load that root's declared extension resources from its canonical local path
- **AND** the extension SHALL resolve its transitive imports from the shared image-owned closure
- **AND** successful settings mutation without successful Pi loading SHALL fail acceptance

### Requirement: Define qualifying duplicate npm entries precisely
A qualifying duplicate SHALL be a user `npm:` source whose normalized npm package name equals a managed root package name; version text SHALL not affect equivalence. Multiple qualifying entries for the same name SHALL each be preserved exactly in their original relative order in the sidecar and suppressed from effective settings. Git and local sources SHALL not be automatically suppressed, because their Pi source identities are distinct; they MAY be diagnosed only.

#### Scenario: Suppressing versions of one managed npm root
- **WHEN** active settings contain one or more `npm:` entries for a managed package name at different versions
- **THEN** the reconciler SHALL preserve every exact entry in the sidecar and suppress every such entry from active settings
- **AND** Pi SHALL receive only the managed local-path root for that package

#### Scenario: Retaining a git or local entry
- **WHEN** a git or local entry resembles a managed package
- **THEN** the reconciler SHALL not suppress it by package-name inference
- **AND** MAY emit a diagnostic identifying the separate source identity

### Requirement: Recover interruption without losing user settings
The sidecar transaction state SHALL record the expected pre- and post-replacement identities for active settings and the exact baseline entries. On startup, the reconciler SHALL deterministically finalize a prepared transaction when active settings match its expected post-state, safely discard it when active settings match its pre-state, and preserve active settings without overwrite when they match neither state. In the latter case it SHALL retain recoverable baseline data, report a recovery conflict, and recompute reconciliation from the current active settings.

#### Scenario: Failing before sidecar publication
- **WHEN** suppression fails before the prepared sidecar replacement is published
- **THEN** active settings SHALL remain unchanged
- **AND** no suppression transaction SHALL be active

#### Scenario: Failing after sidecar preparation and before settings replacement
- **WHEN** interruption occurs after prepared sidecar publication but before active settings replacement
- **THEN** the next reconciliation SHALL recognize the expected pre-state and safely discard the stale prepared transaction without data loss
- **AND** SHALL rerun normal reconciliation and create a fresh suppression transaction when the managed root and qualifying duplicate still exist

#### Scenario: Recovering after settings replacement
- **WHEN** interruption occurs after active settings replacement but before sidecar finalization
- **THEN** the next reconciliation SHALL recognize the expected post-state and finalize the suppression record deterministically

#### Scenario: Preserving a manual settings change during recovery
- **WHEN** active settings differ from both transaction states because a user edited settings between runs
- **THEN** recovery SHALL not overwrite active settings
- **AND** SHALL retain the baseline record and report the conflict before reconciling current settings

#### Scenario: Rejecting an unsafe sidecar
- **WHEN** the sidecar is malformed, stale for the active settings identity, or not owned by the expected constructor state
- **THEN** reconciliation SHALL fail without replacing active settings
- **AND** SHALL preserve recoverable user baseline data for operator recovery

### Requirement: Restore suppressed baselines without overwriting user changes
When a managed root is removed, the reconciler SHALL restore its exact suppressed baseline entries only if no equivalent active user npm entry exists. Restoration SHALL use the same prepared-sidecar, atomic-settings-replacement, and recovery protocol as suppression. If an equivalent entry is already active, the reconciler SHALL retain that active user entry, remove the obsolete suppression record only after durable reconciliation, and SHALL not restore over it.

#### Scenario: Restoring after managed root removal
- **WHEN** a managed root no longer exists and no equivalent user npm entry is active
- **THEN** reconciliation SHALL atomically restore the exact preserved baseline entries using surviving placement anchors and their fallback index when anchors are absent
- **AND** SHALL preserve the relative order among restored entries
- **AND** SHALL remove their finalized suppression record

#### Scenario: Respecting a manually restored or changed user entry
- **WHEN** a user has restored or changed an equivalent npm entry while its managed root was active
- **THEN** reconciliation SHALL preserve the active user entry
- **AND** SHALL not overwrite it with the sidecar baseline

### Requirement: Keep image-owned and user-writable package stores physically separate
The managed closure at `/opt/pi-extensions/node_modules` SHALL be image-owned and non-writable at runtime. User npm packages SHALL remain only in the writable Pi user package store at `~/.pi/agent/npm`; the reconciler SHALL NOT mount, copy, link, or reconcile either store into the other.

#### Scenario: Loading managed and user packages together
- **WHEN** Pi loads a managed root with transitive imports and a user-installed npm package
- **THEN** the managed root and its transitive imports SHALL resolve from `/opt/pi-extensions/node_modules`
- **AND** the user package SHALL resolve from `~/.pi/agent/npm`
- **AND** neither package store SHALL satisfy or mutate the other store's packages
