## Purpose

Provide one consumer-neutral, deterministic-input and host-evidenced boundary for assembling exact npm dependency closures from reviewed roots and standard lockfiles.

## ADDED Requirements

### Requirement: Accept only reviewed locked npm inputs
The assembler SHALL require exact root package versions and a matching `package-lock.json` with `lockfileVersion` 3. It SHALL accept only HTTPS registry package nodes with exact versions, resolved URLs, optional valid SRI integrity, safe deterministic installation paths, and supported dependency metadata. The lock project manifest node at `packages[""]`, every reviewed root package entry selected by the plural `RootSpec` inputs, and every remaining transitive package entry SHALL use separate closed accepted-field sets. Each reviewed root SHALL resolve to one exact lock package path, and its functional metadata SHALL be keyed in the immutable DTO and evidence by both canonical root package identity and resolved lock path; metadata from one reviewed root SHALL NOT overwrite, alias, or stand in for another.

The project manifest node SHALL accept only its enumerated project identity and dependency-declaration fields plus `engines`, `license`, `funding`, and `deprecated`. Manifest `engines` SHALL be a closed object containing only optional `node`; when present, `engines.node` SHALL be a non-empty syntax-valid supported strict npm/node-semver range and SHALL then be discarded as non-authoritative. Manifest `license`, `funding`, and `deprecated` SHALL be shape-validated and discarded. Manifest metadata SHALL NOT be substituted for metadata of any reviewed root.

For every reviewed root package entry, `bin` and `engines.node` SHALL be validated functional metadata. Each root `bin` SHALL be a closed object whose keys and values are non-empty strings and whose values are unambiguous safe relative paths; the parser SHALL reject absolute paths, `..` components, empty path components or values, backslashes, and any other executable path that can escape or be interpreted inconsistently. Each root `engines` SHALL be a closed object; when `engines.node` is present it SHALL be a non-empty supported strict node-semver range. Validated executable declarations and validated `engines.node` SHALL be preserved separately for every reviewed root under its package identity/path key. Each root `license`, `funding`, and `deprecated` SHALL be explicitly accepted-and-ignored after shape validation and SHALL NOT affect semantic DTO inputs or assembly output.

For transitive package nodes, `bin`, `license`, `funding`, and `deprecated` SHALL be explicitly accepted-and-ignored after shape validation. Transitive `bin` SHALL be an object with non-empty string keys and non-empty string values. `license` and `deprecated` SHALL each be strings. `funding` SHALL be either a non-empty string, a closed object with required non-empty string `url` and optional non-empty string `type`, or a non-empty array whose entries each use one of those string/object forms. The same `license`, `funding`, and `deprecated` shapes SHALL apply when those ignored fields occur on the project manifest or a reviewed root. Malformed values SHALL be rejected. None of these ignored values SHALL be preserved in a DTO or influence semantic DTO inputs, dependency or placement validation, engine compatibility, assembler execution or npm flags, executable-link creation, tree evidence, or assembled output. Exact byte differences remain represented only by the lockfile digest required by assembler input identity. Ignored `bin` SHALL NOT create executable links.

Transitive `engines` SHALL be accepted-and-ignored metadata after validation. It SHALL be a closed object containing only optional `node`; when present, `engines.node` SHALL be a non-empty string whose syntax is valid under the supported strict npm/node-semver range implementation, including comparator conjunctions and `||` disjunctions exercised by the pinned published Pi fixture. It SHALL then be discarded and SHALL NOT be preserved in DTOs or evidence or influence compatibility decisions, semantic identity inputs, assembler execution, npm flags, executable links, tree evidence, or assembled output. Exact byte differences remain represented only by the lockfile digest required by assembler input identity. npm normally treats dependency engine mismatches as warnings unless `engine-strict` is enabled; Constructor SHALL NOT enable `engine-strict`, so a syntactically valid transitive range SHALL be accepted even when the reviewed Node version does not satisfy it. Constructor SHALL emit no custom transitive-engine compatibility diagnostic. Native output from the pinned npm execution, including any `EBADENGINE` warning npm independently emits, is not suppressed, deduplicated, or promoted into a Constructor diagnostic contract. Only `engines.node` declarations attached to reviewed roots SHALL be authoritative, and every declared reviewed-root range SHALL be enforced. Malformed ranges and unsupported engine keys SHALL be rejected before effects. Every unknown field on the manifest, reviewed-root, or transitive role remains rejected. A non-manifest registry package MAY omit `integrity` only when it has an exact version and a validated credential-free HTTPS registry `resolved` URL. If `integrity` is present it SHALL be valid SRI and remain authoritative for package bytes; if absent, the immutable DTO and validated input SHALL explicitly mark that package as integrity-less by package identity, lock path, exact version, and resolved URL. Missing integrity SHALL NOT be accepted for a node lacking a valid registry URL or exact version. Constructor SHALL NOT claim that an integrity-less lock entry cryptographically pins registry-served package bytes or guarantees byte-identical cold reconstruction; pinned npm's native registry integrity behavior applies, and post-install canonical tree hashes SHALL record the bytes actually published. The assembler SHALL reject root drift, missing closure nodes, traversal, `file:`, git, link, workspace, bundled, unsafe root executable declarations, malformed accepted metadata, or unknown metadata before network or output mutation. Platform-inapplicable optional nodes MAY be omitted only when recorded explicitly.

#### Scenario: Validating a complete registry lock
- **WHEN** exact roots match a complete lockfile-v3 registry closure
- **THEN** preflight SHALL accept the inputs and derive a deterministic assembler input identity

#### Scenario: Rejecting an unsupported lock node
- **WHEN** any lock node uses an unsupported source, unsafe path, malformed SRI, lacks integrity without an exact version and valid HTTPS registry URL, or does not satisfy its parent dependency range
- **THEN** assembly SHALL fail before network, Docker execution, cache mutation, or publication

#### Scenario: Accepting an integrity-less official registry node
- **WHEN** a reviewed-root or transitive package has an exact version and valid credential-free HTTPS registry `resolved` URL but omits `integrity`
- **THEN** preflight SHALL accept it and record its package identity, lock path, version, and resolved URL as integrity-less
- **AND** output evidence SHALL preserve that omission and the canonical hashes of bytes actually assembled
- **AND** SHALL NOT claim the lock cryptographically pins those package bytes

#### Scenario: Preserving executable declarations for multiple reviewed roots
- **WHEN** two reviewed roots resolve to distinct lock package paths and each declares a safe `bin` map
- **THEN** validation SHALL preserve each declaration separately under that root's canonical package identity and resolved lock path
- **AND** metadata from one root SHALL NOT overwrite or alias metadata from the other
- **AND** validation SHALL NOT create an executable link or assign a consumer-specific installation path

#### Scenario: Rejecting an unsafe root executable declaration
- **WHEN** a root `bin` value is empty, absolute, contains `..`, an empty component or a backslash, or is otherwise ambiguous or escaping
- **THEN** validation SHALL fail before network, Docker execution, cache mutation, or publication

#### Scenario: Accepting published transitive metadata
- **WHEN** a published lockfile transitive node contains shape-valid `bin`, syntax-valid `engines.node`, `license`, `funding`, or `deprecated` metadata
- **THEN** validation SHALL accept and discard all five fields
- **AND** SHALL preserve none of their values in the closed DTO or validation evidence

#### Scenario: Proving ignored transitive metadata is inert
- **WHEN** two otherwise identical accepted locks differ only in shape-valid ignored `bin`, `license`, `funding`, or `deprecated` values or syntax-valid ignored `engines.node` ranges
- **THEN** their parsed DTO content, canonical roots and semantic assembly inputs SHALL be equal apart from the exact lock-byte digest
- **AND** the ignored values SHALL NOT change assembler identity, npm flags, executable links, tree evidence, or assembled output
- **AND** assembler input identity MAY differ only because its contract includes the exact lockfile bytes

#### Scenario: Accepting an incompatible transitive Node engine
- **WHEN** a transitive package declares a syntax-valid `engines.node` range, including a range with `||`, that the reviewed Node version does not satisfy
- **THEN** validation SHALL accept and discard that range because `engine-strict` is not enabled
- **AND** SHALL NOT change npm flags, compatibility decisions, or assembled output

#### Scenario: Validating and discarding manifest engines
- **WHEN** the project manifest node declares syntax-valid `engines.node`
- **THEN** validation SHALL discard it without constraining the reviewed Node version or replacing any reviewed root's engine metadata

#### Scenario: Rejecting malformed or unknown role metadata
- **WHEN** a manifest, reviewed-root, or transitive node contains an unknown field, malformed `bin`, `engines`, `license`, `funding`, or `deprecated`, an unsupported engine key, or a syntactically invalid engine range
- **THEN** validation SHALL fail before network, Docker execution, cache mutation, or publication

#### Scenario: Enforcing every reviewed-root Node engine before effects
- **WHEN** multiple reviewed roots declare `engines.node` and the caller-supplied reviewed exact Node version fails to satisfy any one root's range
- **THEN** validation SHALL identify the incompatible root package and lock path and fail before Docker execution, npm, network access, cache mutation, or publication
- **AND** SHALL require all other declared reviewed-root ranges to be satisfied as well
- **AND** SHALL preserve the reviewed Node version as caller-owned configuration rather than deriving a second expected version

#### Scenario: Accepting a pinned published Pi lockfile
- **WHEN** the byte-exact `tests/data/` fixture copied from its recorded immutable published Pi install-lock source is validated for `linux-x64` using roots derived from exact versions of its top-level locked nodes
- **THEN** parsing SHALL accept the complete reachable closure and produce the expected canonical roots
- **AND** every optional omission SHALL be backed by locked platform metadata and have reason `platform-inapplicable`
- **AND** repeated parsing of the same bytes and repeated identity derivation with the same assembler identity SHALL produce equal models and identities
- **AND** the test SHALL read and assert the Pi version from the fixture's own root package metadata
- **AND** fixture provenance SHALL record the exact published source corresponding to that embedded version and SHA-256 of the checked-in `tests/data/` bytes
- **AND** this specification SHALL NOT pin a particular fixture version without reading `/opt/pi` or any installed agent

### Requirement: Separate side-effect-free input preflight from assembly
The assembler SHALL expose a side-effect-free input-validation/preflight operation receiving the exact lockfile bytes, plural `RootSpec` values, target platform, and caller-owned reviewed exact Node and npm versions. It SHALL complete closed parsing, root and closure validation, transitive-metadata handling, extraction of every reviewed root's metadata keyed by canonical package identity and resolved lock path, and satisfaction of every declared reviewed-root `engines.node` range. It SHALL return an immutable validated assembly input binding the exact lockfile digest, canonical roots, platform, reviewed tool versions, validated closure, optional omissions, integrity-less registry-node records, and keyed root metadata. It SHALL perform no Docker execution, network access, cache mutation, staging, identity locking, or publication and SHALL expose no assembled output path or output evidence.

The Docker-backed assembly operation SHALL accept only that validated input together with exact lock bytes and assembler identity inputs whose digest, roots, platform, and reviewed tool versions match its bindings. A mismatch or substitution SHALL fail before effects; assembly SHALL NOT silently reparse different bytes or replace the preflight result.

#### Scenario: Inspecting root metadata before assembly
- **WHEN** side-effect-free preflight succeeds for multiple reviewed roots
- **THEN** the caller SHALL receive all keyed root `bin` and `engines.node` metadata before Docker-backed assembly
- **AND** no Docker, npm, network, cache, staging, lock, publication, output path, or output evidence SHALL exist

#### Scenario: Rejecting substituted preflight input
- **WHEN** Docker-backed assembly receives lock bytes, roots, platform, or reviewed tool versions that differ from the validated input bindings
- **THEN** assembly SHALL fail before Docker or any other effect

### Requirement: Distinguish assembler input identity from assembled output identity
Preflight SHALL derive a stable `AssemblerInputIdentity` only from canonical roots, exact lockfile bytes, assembler identity, platform, and policy/tool inputs. This identity SHALL identify inputs only and SHALL NOT be described or used as a content address for assembled bytes.

After complete tree and evidence validation, assembly SHALL derive a canonical output-tree digest and a canonical assembler-evidence-body digest. The evidence body used for its digest SHALL exclude the enclosing assembled-output-identity field. It SHALL derive `AssembledOutputIdentity` canonically from `(assemblerInputIdentity, canonicalTreeDigest, assemblerEvidenceDigest)`. Different canonical trees or evidence bodies SHALL produce different output identities even when assembler input identity is identical. The immutable evidence envelope and successful result SHALL bind the input identity, tree digest, evidence digest, and assembled output identity.

#### Scenario: Distinguishing reconstructions with identical inputs
- **WHEN** identical validated inputs produce different assembled bytes or different canonical evidence bodies
- **THEN** both reconstructions SHALL retain the same assembler input identity
- **AND** SHALL receive different assembled output identities
- **AND** SHALL NOT overwrite, alias, or validate as one another

### Requirement: Assemble with one pinned standalone npm boundary
The assembler SHALL consume caller-owned reviewed exact Node and npm versions through the validated assembly input. Side-effect-free preflight SHALL already have validated every preserved reviewed-root `engines.node` range against the reviewed Node version and identified any incompatible root by package identity and resolved lock path. After rechecking the validated-input bindings, it SHALL run a standalone container from the reviewed Node image digest, assert its actual Node and npm versions equal those reviewed values before `npm ci`, and execute `npm ci` in empty private staging with exactly the policy flags `--ignore-scripts`, `--no-bin-links`, `--no-audit`, and `--no-fund`. Install-script metadata MAY exist, but lifecycle scripts SHALL never execute. Reviewed-root `bin` metadata SHALL NOT cause the assembler or npm to create executable links; launcher construction belongs to a consumer. The container SHALL run as the invoking host UID/GID, receive only narrow read-only inputs, opaque cache access, controlled network policy, and one writable staging output.

#### Scenario: Assembling a cache miss
- **WHEN** no fully verified assembled output is selected through the non-authoritative input-identity index
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
- **THEN** the Constructor SHALL atomically publish it under its assembled output identity with canonical evidence
- **AND** SHALL NOT publish or overwrite immutable output storage solely under assembler input identity

#### Scenario: Rejecting unexpected output
- **WHEN** output contains an extra package, wrong version, unsafe symlink, special file, ownership mismatch, or changed bytes
- **THEN** publication SHALL fail and committed environments SHALL remain unchanged

### Requirement: Revalidate and coordinate environment reuse
A published environment SHALL be reusable only after no-follow inspection, complete canonical tree-manifest verification, recomputation of canonical tree and evidence digests, and verification that they and assembler input identity derive the selected assembled output identity. An assembler-input-identity lookup index MAY reference zero, one, or multiple assembled output identities but SHALL be non-authoritative; index membership alone SHALL NOT establish reuse. Concurrent assembly of one input identity SHALL coordinate through a private input-identity lock; cancellation, interruption, or failure SHALL clean mutable staging, preserve prior committed environments, and report structured failure without persisting local network configuration.

#### Scenario: Reusing a valid environment
- **WHEN** an input-index candidate names a published output whose tree digest, evidence digest, input identity, and assembled output identity all recompute and match
- **THEN** assembly SHALL return that existing immutable output without npm or network execution

#### Scenario: Detecting cache corruption
- **WHEN** any published entry differs from its manifest
- **THEN** the environment SHALL not be reused
- **AND** recovery SHALL occur only through locked replacement assembly

### Requirement: Emit a consumer-neutral assembly result
A successful result SHALL identify the environment root, assembler input identity, assembled output identity, canonical output-tree digest, canonical assembler-evidence digest, roots, validated executable declarations and `engines.node` metadata keyed by reviewed-root package identity and resolved lock path, complete package closure, assembler image digest, asserted tool versions, policy and script digests, platform, input hashes, fixed flags, optional omissions, integrity-less registry-node records, canonical output-tree hashes, and evidence path. It SHALL contain no generated executable link, consumer-specific Pi layout, extension settings, build-context, CLI-guard, or lock-refresh behavior.

#### Scenario: Consuming assembled evidence
- **WHEN** a consumer receives a successful assembly result
- **THEN** it SHALL have sufficient immutable paths and evidence to construct its own layout without inspecting npm cache internals
