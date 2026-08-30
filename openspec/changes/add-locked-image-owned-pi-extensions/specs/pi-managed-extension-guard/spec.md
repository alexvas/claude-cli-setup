## Purpose

Protect image-owned managed Pi extensions from mutation while preserving ordinary Pi command behavior.

## ADDED Requirements

### Requirement: Guard managed extension mutation through the Pi command
The image SHALL expose `/usr/local/bin/pi` as a wrapper that classifies only the documented command forms in this requirement. It SHALL recognize `list`; `install <source>` where source is canonical `npm:`, `git:`, raw URL, absolute path, or relative path; `remove npm:<package>`; bare `update`; `update --all`; `update --extensions`; `update --models`; `update --self`; `update --self --force`; `update npm:<package>`; and `update --extension npm:<package>`. It SHALL NOT apply mutation-like heuristics, infer aliases, or fail closed merely because another command or argv form is unknown; every unlisted form SHALL be forwarded unchanged to Pi.

The wrapper SHALL reject bare `update`, `update --self`, and `update --self --force` because they mutate the Pi agent. It SHALL reject `update --all` and `update --extensions` because they can mutate managed extensions. For recognized `install`, `remove`, `update <npm-source>`, and `update --extension <npm-source>` forms, it SHALL reject only when the normalized npm identity is a managed root. It SHALL forward recognized unmanaged npm sources, recognized `git:`/URL/path installs, `list`, and `update --models`. Every rejection SHALL avoid invoking Pi and explain roots → `sync-lock` → review → rebuild. Every forwarded command SHALL retain its original argv, signals, and exit status.

#### Scenario: Blocking Pi agent updates
- **WHEN** a user invokes `pi update`, `pi update --self`, or `pi update --self --force`
- **THEN** the wrapper SHALL reject it without invoking Pi
- **AND** SHALL print the reviewed-root, `sync-lock`, review, and rebuild guidance

#### Scenario: Blocking broad extension updates
- **WHEN** a user invokes `pi update --all` or `pi update --extensions`
- **THEN** the wrapper SHALL reject it without invoking Pi
- **AND** SHALL print the reviewed-root, `sync-lock`, review, and rebuild guidance

#### Scenario: Allowing non-mutating documented commands
- **WHEN** a user invokes `pi list` or `pi update --models`
- **THEN** the wrapper SHALL execute Pi with the original unchanged argv
- **AND** SHALL preserve its signals and exit status

#### Scenario: Blocking a managed-source update
- **WHEN** `pi update npm:<package>` or `pi update --extension npm:<package>` names a normalized npm identity in the managed-root manifest
- **THEN** the wrapper SHALL reject it without invoking Pi
- **AND** SHALL print the reviewed-root, `sync-lock`, review, and rebuild guidance

#### Scenario: Blocking managed-source installation and removal
- **WHEN** `pi install npm:<package>` or `pi remove npm:<package>` names a normalized npm identity in the managed-root manifest
- **THEN** the wrapper SHALL reject it without invoking Pi
- **AND** SHALL print the reviewed-root, `sync-lock`, review, and rebuild guidance

#### Scenario: Forwarding an unmanaged npm source operation
- **WHEN** a recognized install, remove, or update form names a canonical npm identity outside the managed-root manifest
- **THEN** the wrapper SHALL execute Pi with unchanged argv
- **AND** SHALL preserve its signals and exit status

#### Scenario: Forwarding a non-npm installation source
- **WHEN** `pi install` names a canonical `git:` source, raw URL, absolute path, or relative path
- **THEN** the wrapper SHALL execute Pi with unchanged argv
- **AND** SHALL preserve its signals and exit status

#### Scenario: Forwarding an unlisted command form
- **WHEN** an invocation does not exactly match a documented form classified by this requirement
- **THEN** the wrapper SHALL execute Pi with unchanged argv without applying mutation-like heuristics
- **AND** SHALL preserve its signals and exit status

### Requirement: Match managed npm sources without settings access
The wrapper SHALL obtain managed package identities only from an immutable read-only manifest generated from reviewed roots at image-build time. A comparable source SHALL have canonical form `npm:<name>` or `npm:<name>@<version>`. For a scoped source, the wrapper SHALL parse `npm:@<scope>/<name>` and remove only an optional trailing version for identity comparison. It SHALL validate canonical npm package syntax, SHALL NOT percent-decode or interpret a source as a URL, and SHALL compare the exact package identity with the build-time manifest. Only canonical npm sources in the explicitly recognized source slots SHALL be compared with the manifest; malformed, ambiguous, aliased, or otherwise unlisted forms SHALL remain outside wrapper classification and be forwarded unchanged to Pi.

#### Scenario: Matching an unscoped managed source
- **WHEN** a mutation operand is `npm:<name>` or `npm:<name>@<version>` and `<name>` appears in the managed-root manifest
- **THEN** the wrapper SHALL classify the operand as managed independently of its optional version

#### Scenario: Matching a scoped managed source
- **WHEN** a mutation operand is `npm:@<scope>/<name>` or `npm:@<scope>/<name>@<version>` and `@<scope>/<name>` appears in the managed-root manifest
- **THEN** the wrapper SHALL classify the operand as managed independently of its optional version

#### Scenario: Forwarding unclassified npm source syntax
- **WHEN** an argv form contains percent-encoded package structure, URL-like npm syntax, invalid npm package syntax, or an ambiguous version boundary and therefore does not exactly match a documented canonical npm source slot
- **THEN** the wrapper SHALL forward the invocation unchanged to Pi
- **AND** SHALL NOT decode or reinterpret the operand

#### Scenario: Leaving duplicate reconciliation to settings
- **WHEN** the wrapper classifies an invocation or Pi settings contain a duplicate managed-root user entry
- **THEN** the wrapper SHALL not read, write, suppress, restore, or diagnose settings or sidecar state
- **AND** SHALL use only the immutable build-time managed-root manifest
- **AND** duplicate suppression, restoration, and diagnostics SHALL be performed only by settings reconciliation
