## Purpose

Provide one consumer-neutral, reproducible and host-evidenced boundary for assembling exact npm dependency closures from reviewed roots and standard lockfiles.

## ADDED Requirements

### Requirement: Accept only reviewed locked npm inputs
The assembler SHALL require exact root package versions and a matching `package-lock.json` with `lockfileVersion` 3. It SHALL accept only HTTPS registry package nodes with exact versions, resolved URLs, valid SRI integrity, safe deterministic installation paths, and supported dependency metadata. Every reviewed root package entry selected by the plural `RootSpec` inputs and every remaining transitive package entry SHALL use the appropriate separate closed accepted-field set. Each reviewed root SHALL resolve to one exact lock package path, and its functional metadata SHALL be keyed in the immutable DTO and evidence by both canonical root package identity and resolved lock path; metadata from one reviewed root SHALL NOT overwrite, alias, or stand in for another.

For every reviewed root package entry, `bin` and `engines.node` SHALL be validated functional metadata. Each root `bin` SHALL be a closed object whose keys and values are non-empty strings and whose values are unambiguous safe relative paths; the parser SHALL reject absolute paths, `..` components, empty path components or values, backslashes, and any other executable path that can escape or be interpreted inconsistently. Each root `engines` SHALL be a closed object; when `engines.node` is present it SHALL be a non-empty supported strict node-semver range. Validated executable declarations and validated `engines.node` SHALL be preserved separately for every reviewed root under its package identity/path key. Each root `license` SHALL be explicitly accepted-and-ignored and SHALL NOT affect semantic DTO inputs or assembly output.

For transitive package nodes, `bin` and `license` SHALL be explicitly accepted-and-ignored after shape validation. Transitive `bin` SHALL be an object with non-empty string keys and non-empty string values, and transitive `license` SHALL be a string; malformed values SHALL be rejected. Neither field SHALL be preserved in a DTO or influence semantic DTO inputs, dependency or placement validation, engine compatibility, assembler execution or npm flags, executable-link creation, tree evidence, or assembled output. Exact byte differences remain represented only by the lockfile digest required by environment identity. Transitive `bin` SHALL NOT create executable links.

Transitive `engines` SHALL be accepted-and-ignored metadata after validation. It SHALL be a closed object containing only optional `node`; when present, `engines.node` SHALL be a non-empty string whose syntax is valid under the supported strict npm/node-semver range implementation, including comparator conjunctions and `||` disjunctions exercised by the pinned published Pi fixture. It SHALL then be discarded and SHALL NOT be preserved in DTOs or evidence or influence compatibility decisions, semantic identity inputs, assembler execution, npm flags, executable links, tree evidence, or assembled output. Exact byte differences remain represented only by the lockfile digest required by environment identity. npm normally treats dependency engine mismatches as warnings unless `engine-strict` is enabled; Constructor SHALL NOT enable `engine-strict`, so a syntactically valid transitive range SHALL be accepted even when the reviewed Node version does not satisfy it. Constructor SHALL emit no custom transitive-engine compatibility diagnostic. Native output from the pinned npm execution, including any `EBADENGINE` warning npm independently emits, is not suppressed, deduplicated, or promoted into a Constructor diagnostic contract. Only `engines.node` declarations attached to reviewed roots SHALL be authoritative, and every declared reviewed-root range SHALL be enforced. Malformed ranges and unsupported engine keys SHALL be rejected before effects. Every unknown field on either root or transitive nodes remains rejected. The assembler SHALL reject root drift, missing closure nodes, traversal, `file:`, git, link, workspace, bundled, integrity-less nodes, unsafe root executable declarations, malformed accepted metadata, or unknown metadata before network or output mutation. Platform-inapplicable optional nodes MAY be omitted only when recorded explicitly.

#### Scenario: Validating a complete registry lock
- **WHEN** exact roots match a complete lockfile-v3 registry closure
- **THEN** assembly SHALL accept the inputs and derive a deterministic environment identity

#### Scenario: Rejecting an unsupported lock node
- **WHEN** any lock node uses an unsupported source, unsafe path, missing integrity, or does not satisfy its parent dependency range
- **THEN** assembly SHALL fail before network, Docker execution, cache mutation, or publication

#### Scenario: Preserving executable declarations for multiple reviewed roots
- **WHEN** two reviewed roots resolve to distinct lock package paths and each declares a safe `bin` map
- **THEN** validation SHALL preserve each declaration separately under that root's canonical package identity and resolved lock path
- **AND** metadata from one root SHALL NOT overwrite or alias metadata from the other
- **AND** validation SHALL NOT create an executable link or assign a consumer-specific installation path

#### Scenario: Rejecting an unsafe root executable declaration
- **WHEN** a root `bin` value is empty, absolute, contains `..`, an empty component or a backslash, or is otherwise ambiguous or escaping
- **THEN** validation SHALL fail before network, Docker execution, cache mutation, or publication

#### Scenario: Accepting published transitive metadata
- **WHEN** a published lockfile transitive node contains shape-valid `bin`, syntax-valid `engines.node`, or shape-valid `license` metadata
- **THEN** validation SHALL accept and discard all three fields
- **AND** SHALL preserve none of their values in the closed DTO or validation evidence

#### Scenario: Proving ignored transitive metadata is inert
- **WHEN** two otherwise identical accepted locks differ only in shape-valid transitive `bin` or `license` values or syntax-valid transitive `engines.node` ranges
- **THEN** their parsed DTO content, canonical roots and semantic assembly inputs SHALL be equal apart from the exact lock-byte digest
- **AND** the ignored values SHALL NOT change assembler identity, npm flags, executable links, tree evidence, or assembled output
- **AND** environment identity MAY differ only because its contract includes the exact lockfile bytes

#### Scenario: Accepting an incompatible transitive Node engine
- **WHEN** a transitive package declares a syntax-valid `engines.node` range, including a range with `||`, that the reviewed Node version does not satisfy
- **THEN** validation SHALL accept and discard that range because `engine-strict` is not enabled
- **AND** SHALL NOT change npm flags, compatibility decisions, or assembled output

#### Scenario: Rejecting malformed or unknown transitive metadata
- **WHEN** a transitive node contains an unknown field, malformed `bin`, `engines`, or `license`, an unsupported engine key, or a syntactically invalid engine range
- **THEN** validation SHALL fail before network, Docker execution, cache mutation, or publication

#### Scenario: Enforcing every reviewed-root Node engine before effects
- **WHEN** multiple reviewed roots declare `engines.node` and the caller-supplied reviewed exact Node version fails to satisfy any one root's range
- **THEN** validation SHALL identify the incompatible root package and lock path and fail before Docker execution, npm, network access, cache mutation, or publication
- **AND** SHALL require all other declared reviewed-root ranges to be satisfied as well
- **AND** SHALL preserve the reviewed Node version as caller-owned configuration rather than deriving a second expected version

#### Scenario: Accepting a pinned published Pi lockfile
- **WHEN** the repository-pinned compatibility fixture copied from the published lockfile v3 of the recorded Pi package version is validated for `linux-x64` using roots derived from exact versions of its top-level locked nodes
- **THEN** parsing SHALL accept the complete reachable closure and produce the expected canonical roots
- **AND** every optional omission SHALL be backed by locked platform metadata and have reason `platform-inapplicable`
- **AND** repeated parsing of the same bytes and repeated identity derivation with the same assembler identity SHALL produce equal models and identities
- **AND** fixture provenance SHALL record the immutable published source, Pi version, and SHA-256 of the checked-in `tests/data/` bytes without reading `/opt/pi` or any installed agent

### Requirement: Separate side-effect-free input preflight from assembly
The assembler SHALL expose a side-effect-free input-validation/preflight operation receiving the exact lockfile bytes, plural `RootSpec` values, target platform, and caller-owned reviewed exact Node and npm versions. It SHALL complete closed parsing, root and closure validation, transitive-metadata handling, extraction of every reviewed root's metadata keyed by canonical package identity and resolved lock path, and satisfaction of every declared reviewed-root `engines.node` range. It SHALL return an immutable validated assembly input binding the exact lockfile digest, canonical roots, platform, reviewed tool versions, validated closure, optional omissions, and keyed root metadata. It SHALL perform no Docker execution, network access, cache mutation, staging, identity locking, or publication and SHALL expose no assembled output path or output evidence.

The Docker-backed assembly operation SHALL accept only that validated input together with exact lock bytes and assembler identity inputs whose digest, roots, platform, and reviewed tool versions match its bindings. A mismatch or substitution SHALL fail before effects; assembly SHALL NOT silently reparse different bytes or replace the preflight result.

#### Scenario: Inspecting root metadata before assembly
- **WHEN** side-effect-free preflight succeeds for multiple reviewed roots
- **THEN** the caller SHALL receive all keyed root `bin` and `engines.node` metadata before Docker-backed assembly
- **AND** no Docker, npm, network, cache, staging, lock, publication, output path, or output evidence SHALL exist

#### Scenario: Rejecting substituted preflight input
- **WHEN** Docker-backed assembly receives lock bytes, roots, platform, or reviewed tool versions that differ from the validated input bindings
- **THEN** assembly SHALL fail before Docker or any other effect

### Requirement: Assemble with one pinned standalone npm boundary
The assembler SHALL consume caller-owned reviewed exact Node and npm versions through the validated assembly input. Side-effect-free preflight SHALL already have validated every preserved reviewed-root `engines.node` range against the reviewed Node version and identified any incompatible root by package identity and resolved lock path. After rechecking the validated-input bindings, it SHALL run a standalone container from the reviewed Node image digest, assert its actual Node and npm versions equal those reviewed values before `npm ci`, and execute `npm ci` in empty private staging with exactly the policy flags `--ignore-scripts`, `--no-bin-links`, `--no-audit`, and `--no-fund`. Install-script metadata MAY exist, but lifecycle scripts SHALL never execute. Reviewed-root `bin` metadata SHALL NOT cause the assembler or npm to create executable links; launcher construction belongs to a consumer. The container SHALL run as the invoking host UID/GID, receive only narrow read-only inputs, opaque cache access, controlled network policy, and one writable staging output.

#### Scenario: Assembling a cache miss
- **WHEN** no valid published environment exists for the derived identity
- **THEN** the standalone assembler SHALL install the locked graph in private staging with the fixed policy
- **AND** SHALL NOT build or mutate a consumer image

#### Scenario: Blocking script execution
- **WHEN** a locked package declares an install script
- **THEN** its package bytes MAY be installed
- **AND** no lifecycle script SHALL execute

### Requirement: Independently validate and publish assembled trees
After the container exits successfully, the Constructor SHALL independently compare the assembled installation paths, package names, versions, dependency closure, optional omissions, filesystem entry types, symlink containment, ownership, permissions, and absence of extras with the validated lock. For every preserved executable declaration of every reviewed root, resolution of its path through the assembled filesystem SHALL remain contained within the assembled environment; a dangling or escaping symlink target SHALL be rejected. This check SHALL validate metadata and installed bytes without creating a launcher or executable link. The Constructor SHALL create a canonical per-entry tree manifest with hashes, write host-owned evidence, remove write permissions, and atomically publish only a fully validated environment.

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
A successful result SHALL identify the environment root, identity, roots, validated executable declarations and `engines.node` metadata keyed by reviewed-root package identity and resolved lock path, complete package closure, assembler image digest, asserted tool versions, policy and script digests, platform, input hashes, fixed flags, optional omissions, and evidence path. It SHALL contain no generated executable link, consumer-specific Pi layout, extension settings, build-context, CLI-guard, or lock-refresh behavior.

#### Scenario: Consuming assembled evidence
- **WHEN** a consumer receives a successful assembly result
- **THEN** it SHALL have sufficient immutable paths and evidence to construct its own layout without inspecting npm cache internals
