## Purpose

Provide one consumer-neutral, reproducible and host-evidenced boundary for assembling exact npm dependency closures from reviewed roots and standard lockfiles.

## ADDED Requirements

### Requirement: Accept only reviewed locked npm inputs
The assembler SHALL require exact root package versions and a matching `package-lock.json` with `lockfileVersion` 3. It SHALL accept only HTTPS registry package nodes with exact versions, resolved URLs, valid SRI integrity, safe deterministic installation paths, and supported dependency metadata. It SHALL reject root drift, missing closure nodes, traversal, `file:`, git, link, workspace, bundled, or integrity-less nodes before network or output mutation. Platform-inapplicable optional nodes MAY be omitted only when recorded explicitly.

#### Scenario: Validating a complete registry lock
- **WHEN** exact roots match a complete lockfile-v3 registry closure
- **THEN** assembly SHALL accept the inputs and derive a deterministic environment identity

#### Scenario: Rejecting an unsupported lock node
- **WHEN** any lock node uses an unsupported source, unsafe path, missing integrity, or does not satisfy its parent dependency range
- **THEN** assembly SHALL fail before network, Docker execution, cache mutation, or publication

### Requirement: Assemble with one pinned standalone npm boundary
The assembler SHALL run a standalone container from the reviewed Node image digest, assert its expected Node and npm versions, and execute `npm ci` in empty private staging with exactly the policy flags `--ignore-scripts`, `--no-bin-links`, `--no-audit`, and `--no-fund`. Install-script metadata MAY exist, but lifecycle scripts SHALL never execute. The container SHALL run as the invoking host UID/GID, receive only narrow read-only inputs, opaque cache access, controlled network policy, and one writable staging output.

#### Scenario: Assembling a cache miss
- **WHEN** no valid published environment exists for the derived identity
- **THEN** the standalone assembler SHALL install the locked graph in private staging with the fixed policy
- **AND** SHALL NOT build or mutate a consumer image

#### Scenario: Blocking script execution
- **WHEN** a locked package declares an install script
- **THEN** its package bytes MAY be installed
- **AND** no lifecycle script SHALL execute

### Requirement: Independently validate and publish assembled trees
After the container exits successfully, the Constructor SHALL independently compare the assembled installation paths, package names, versions, dependency closure, optional omissions, filesystem entry types, symlink containment, ownership, permissions, and absence of extras with the validated lock. It SHALL create a canonical per-entry tree manifest with hashes, write host-owned evidence, remove write permissions, and atomically publish only a fully validated environment.

#### Scenario: Publishing a valid tree
- **WHEN** assembled output exactly matches the validated lock and filesystem policy
- **THEN** the Constructor SHALL atomically publish it under its environment identity with canonical evidence

#### Scenario: Rejecting unexpected output
- **WHEN** output contains an extra package, wrong version, unsafe symlink, special file, ownership mismatch, or changed bytes
- **THEN** publication SHALL fail and committed environments SHALL remain unchanged

### Requirement: Revalidate and coordinate environment reuse
A published environment SHALL be reusable only after no-follow inspection and complete canonical tree-manifest verification. Concurrent assembly of one identity SHALL coordinate through a private identity lock; cancellation, interruption, or failure SHALL clean mutable staging, preserve prior committed environments, and report structured failure without persisting local network configuration.

#### Scenario: Reusing a valid environment
- **WHEN** a published identity exists and every tree entry still matches evidence
- **THEN** assembly SHALL return the existing immutable environment without npm or network execution

#### Scenario: Detecting cache corruption
- **WHEN** any published entry differs from its manifest
- **THEN** the environment SHALL not be reused
- **AND** recovery SHALL occur only through locked replacement assembly

### Requirement: Emit a consumer-neutral assembly result
A successful result SHALL identify the environment root, identity, roots, complete package closure, assembler image digest, asserted tool versions, policy and script digests, platform, input hashes, fixed flags, optional omissions, and evidence path. It SHALL contain no consumer-specific Pi layout, extension settings, build-context, CLI-guard, or lock-refresh behavior.

#### Scenario: Consuming assembled evidence
- **WHEN** a consumer receives a successful assembly result
- **THEN** it SHALL have sufficient immutable paths and evidence to construct its own layout without inspecting npm cache internals
