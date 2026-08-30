## Purpose

Define reproducible image-owned Pi extension closures from reviewed roots and a checked-in npm lockfile.

## ADDED Requirements

### Requirement: Define reviewed managed extension roots and one authoritative lockfile
The reviewed inventory SHALL declare managed Pi extension root packages as exact package/version pairs. A checked-in `package-lock.json` v3 SHALL be the sole dependency-closure authority for those roots. Ordinary inventory validation and build planning SHALL require the checked-in lockfile root package identities and exact versions to match the reviewed managed roots, SHALL reject missing, extra, or mismatched roots, and SHALL NOT expose transitive lock packages as user-selectable Pi package sources. Starting from those roots, validation SHALL traverse every lockfile dependency edge, require every reachable package entry to exist, reject dangling references and incomplete reachable closure data, and require registry packages to carry the resolved source and SRI integrity data needed by assembly.

#### Scenario: Validating a complete matching closure
- **WHEN** reviewed managed roots and the checked-in lockfile declare the same exact roots and every dependency edge reaches a complete package entry with required registry metadata
- **THEN** validation SHALL accept the managed extension input
- **AND** transitive packages SHALL remain closure members rather than managed roots

#### Scenario: Rejecting an incomplete closure
- **WHEN** a root or transitive dependency edge references an absent package entry or a reachable registry package lacks required resolved source or SRI integrity data
- **THEN** validation SHALL fail before assembly or Docker build
- **AND** SHALL identify the incomplete or dangling closure member

#### Scenario: Rejecting root-lock drift
- **WHEN** a root is missing, extra, or version-mismatched between TOML and the checked-in lockfile during ordinary `validate` or `build`
- **THEN** that command SHALL fail before assembly, resolver, or Docker build execution
- **AND** SHALL distinguish root-set drift from an incomplete transitive closure
- **AND** SHALL NOT apply the lock-owner synchronization recovery preflight

### Requirement: Separate ordinary dependency checks from managed lock synchronization
Ordinary `check-deps` SHALL reconcile managed Pi extension exact root versions through a dedicated root-version provider whose sole authority is `https://registry.npmjs.org/`. It SHALL request unscoped metadata from `https://registry.npmjs.org/<name>` and scoped metadata from `https://registry.npmjs.org/@<scope>%2F<name>`, compare each reviewed exact root with the latest eligible stable version, and emit at most a root-version-only suggestion. It SHALL use the protected Constructor metadata transport with a closed explicit-input boundary that receives no npm environment/configuration state, ambient HTTP authentication, `.netrc`, or cookie jar; request headers SHALL exclude authorization and cookies, while optional proxy/CA inputs SHALL come only from their separately validated credential-free policy. It SHALL use exact normalized allowed origin `https://registry.npmjs.org:443`, automatic redirects disabled, and bounded validation of every HTTPS same-origin redirect before follow. It SHALL reject HTTP downgrade, userinfo, malformed or unsupported URLs, cross-origin redirects, and hop-limit exhaustion before the next request and SHALL NOT cache a rejected redirect as successful metadata. Failure to establish authority SHALL produce `unavailable` without custom-registry or runtime-artifact fallback. It SHALL NOT resolve or read the transitive closure, invoke the artifact-backed npm metadata provider, fetch exact-version tarball metadata, inspect or correct removed runtime npm artifact URLs or reviewed runtime SRI fields, access runtime catalogs or blob caches, or mutate the lockfile. The managed-extension owner under `sync-lock` SHALL be the only operation that resolves the managed npm closure, solely from the reviewed exact roots, and its only candidate output SHALL be a validated `package-lock.json`; it SHALL NOT produce a TOML suggestion containing tarball URL or integrity fields or change reviewed exact roots. The ordinary npm-provider custom-registry derivation and metadata-redirect policy SHALL NOT apply to this owner: the owner SHALL configure exactly `https://registry.npmjs.org/` rather than derive authority from a removed runtime artifact URL, and SHALL enforce its separately defined post-generation lockfile URL validation.

#### Scenario: Checking managed roots without synchronizing locks
- **WHEN** ordinary `check-deps` processes managed Pi extension roots
- **THEN** its dedicated root-version provider SHALL query only the fixed public-registry unscoped or scoped metadata endpoint through the credential-free protected Constructor metadata transport and compare each reviewed exact root with the latest eligible stable version
- **AND** every redirect SHALL be validated against `https://registry.npmjs.org:443` before follow, with unsafe targets rejected before another request and without successful cache publication
- **AND** a newer eligible version SHALL produce only an exact-root-version suggestion, while an authority failure SHALL produce `unavailable` without fallback
- **AND** it SHALL NOT invoke the artifact-backed npm metadata provider, fetch tarball metadata, resolve or read closure packages, require or correct a managed runtime artifact URL or SRI entry, access a catalog, projection, or blob cache, or mutate the checked-in lockfile

#### Scenario: Synchronizing through a separate resolver boundary
- **WHEN** `sync-lock` invokes the managed-extension lock owner
- **THEN** it SHALL resolve a candidate closure from the reviewed exact roots using exactly `https://registry.npmjs.org/` as its configured initial registry
- **AND** SHALL NOT derive a custom registry from a removed reviewed artifact URL or apply the ordinary npm-provider metadata-redirect contract
- **AND** SHALL validate candidate lockfile resolved URLs before publication
- **AND** SHALL publish only the candidate `package-lock.json`, without a TOML URL/integrity suggestion or modification of reviewed roots

### Requirement: Synchronize Constructor-managed lockfiles all-or-nothing
`sync-lock` SHALL be a distinct top-level mutation-capable orchestration operation and SHALL NOT perform ordinary provider reconciliation or invoke ordinary-provider metadata HTTP requests. It SHALL discover all registered Constructor-managed lock owners in deterministic order. Every owner SHALL complete preflight, candidate generation, and candidate validation before any checked-in lockfile is published. Publication SHALL use one durable logical transaction with prior-byte backups and recovery state so that success exposes the complete synchronized set and any failure or interruption leaves or restores the complete prior set; a final partially synchronized set SHALL be forbidden. Its pre-resolution validation SHALL parse the closed inventory schema, validate exact root declarations and reviewed Node/npm pins, and determine a safe checked-in lockfile path, but SHALL NOT compare those roots with the existing lockfile or validate that lock's closure. It SHALL execute in this order: apply that owner-specific preflight; create private temporary staging; start the inventory-pinned Node image identified by its reviewed digest; run `node --version` and compare the result only with `[build.stages.base.node].node_version`; after Node succeeds, run `npm --version` and compare the result only with `[build.stages.base.node].npm_version`; only after both checks succeed, render the temporary resolver inputs and invoke npm resolution; then validate the staged candidate; and only after complete validation mark that owner candidate ready for the shared publication transaction. Its only manifest input SHALL be a temporary `package.json` containing the reviewed exact roots. It SHALL invoke exactly `npm install --package-lock-only --ignore-scripts --no-bin-links --no-audit --no-fund --registry=https://registry.npmjs.org/`; lifecycle scripts SHALL never execute. No ordinary-provider request or resolver network access SHALL occur before both toolchain assertions succeed. The owner's only candidate output SHALL be the staged `package-lock.json`; it SHALL become publishable only as part of the complete validated owner set.

The managed-extension owner SHALL configure exactly `https://registry.npmjs.org/` as npm's initial registry and SHALL receive only the resolved credential-free proxy and enabled corporate CA policy used by the standalone npm boundary. This SHALL define a configuration and candidate-acceptance boundary, not a network sandbox: Constructor SHALL NOT guarantee the origin of every request made internally by npm, absence of transient cross-origin redirect traffic, or per-hop redirect authorization without a separate egress-control mechanism. It SHALL use an isolated temporary npm user config and empty global config; SHALL NOT read, scan, or mount project, user, or host-global `.npmrc`; and SHALL remove `NPM_CONFIG_REGISTRY`, `NPM_CONFIG_USERCONFIG`, scope-registry mappings, and analogous npm configuration variables before resolver execution without reading their values. It MAY test only whether known ambient npm files or npm configuration variable names are present. When any are present, the owner SHALL emit a prominent warning that they are ignored; when none are present, it SHALL emit no ambient-configuration warning. Custom and scope-specific registries SHALL NOT be supported. Credentials SHALL be rejected only in inputs Constructor actually projects into the resolver, including the fixed registry URL and credential-free proxy/CA policy; the owner SHALL NOT claim to discover credentials in ignored files or discarded environment values. No credential, proxy endpoint, or machine-local CA path SHALL be persisted in the candidate or diagnostics. Redirect handling SHALL remain internal to the pinned npm client; Constructor SHALL NOT claim to inspect or authorize each target before npm follows it.

Before transaction readiness, the managed-extension owner SHALL validate candidate lockfile v3, exact root correspondence, the complete reachable closure, registry metadata, and SRI integrity. Every reachable registry package SHALL have a credential-free HTTPS `resolved` URL whose normalized origin is `https://registry.npmjs.org:443`; custom origins, userinfo, and HTTP URLs SHALL be rejected. Only complete success of every registered owner SHALL allow the orchestrator to publish the transaction. Owner failure before commit SHALL preserve every prior lockfile byte-for-byte and remove temporary manifest, candidate, and staging files; transaction interruption SHALL recover the complete prior or complete candidate set; separately owned persistent download caches SHALL remain governed by their cache policy. The managed-extension owner SHALL own dependency resolution and lock generation. `locked-npm-environment-assembly` SHALL consume only an already reviewed lockfile, install it with its fixed `npm ci` contract, and SHALL neither resolve nor update that lockfile.

#### Scenario: Executing synchronization in the required order
- **WHEN** `sync-lock` runs
- **THEN** it SHALL validate closed inventory schema, exact roots, reviewed toolchain pins, and safe lockfile location without comparing roots to the existing lock; create private staging; start the reviewed digest-pinned image; verify Node; verify npm; run npm resolution; fully validate the candidate including exact root correspondence; and atomically publish it in exactly that order
- **AND** SHALL NOT run ordinary provider reconciliation or any provider metadata request
- **AND** SHALL permit resolver network access only after both toolchain assertions succeed

#### Scenario: Publishing all registered locks all-or-nothing
- **WHEN** every registered owner has generated and validated its candidate
- **THEN** `sync-lock` SHALL durably record the complete prior and candidate sets before publishing any target
- **AND** SHALL publish the complete candidate set as one logical transaction
- **AND** successful completion SHALL expose no mixture of prior and candidate lockfiles

#### Scenario: Rejecting one owner before publication
- **WHEN** any registered owner fails preflight, generation, or candidate validation
- **THEN** `sync-lock` SHALL publish no owner candidate
- **AND** every checked-in lockfile SHALL remain byte-for-byte unchanged

#### Scenario: Recovering an interrupted multi-lock publication
- **WHEN** synchronization is interrupted after publication begins
- **THEN** durable recovery SHALL complete the entire validated candidate set or restore the entire prior set
- **AND** SHALL never accept a partially synchronized final state

#### Scenario: Synchronizing a valid lockfile
- **WHEN** the managed-extension owner successfully generates and validates a candidate matching reviewed roots and containing a complete closure
- **THEN** it SHALL atomically replace the checked-in lockfile
- **AND** SHALL report that review and rebuild are required before the new closure is used

#### Scenario: Repairing root-lock drift through synchronization
- **WHEN** reviewed TOML roots have been changed while the checked-in lockfile still contains the prior roots
- **THEN** the managed-extension owner preflight SHALL accept the valid inventory, exact roots, reviewed toolchain pins, and safe lockfile location without applying root correspondence to the existing lock
- **AND** after successful toolchain assertions SHALL permit resolver execution
- **AND** the generated candidate SHALL match the current TOML roots exactly and pass complete closure validation before publication
- **AND** only a fully valid candidate SHALL atomically replace the prior lock

#### Scenario: Preserving a drifting prior lock after candidate failure
- **WHEN** synchronization starts from root-lock drift but resolution fails or the generated candidate fails root correspondence, closure, SRI, or resolved-origin validation
- **THEN** `sync-lock` SHALL reject the candidate and fail
- **AND** SHALL preserve the prior mismatched checked-in lock byte-for-byte and remove temporary candidate and staging files

#### Scenario: Rejecting a mismatched Node version
- **WHEN** `node --version` in the reviewed digest-pinned image differs from `[build.stages.base.node].node_version`
- **THEN** the managed-extension owner SHALL fail before invoking `npm --version`, npm resolution, or resolver network access
- **AND** SHALL preserve the checked-in lockfile byte-for-byte

#### Scenario: Rejecting a mismatched npm version
- **WHEN** Node verification succeeds but `npm --version` differs from `[build.stages.base.node].npm_version`
- **THEN** the managed-extension owner SHALL fail before invoking `npm install` or permitting resolver network access
- **AND** SHALL preserve the checked-in lockfile byte-for-byte

#### Scenario: Using the pinned resolver toolchain
- **WHEN** the observed Node and npm versions exactly match their reviewed fields
- **THEN** the managed-extension owner SHALL run the exact fixed npm command in the reviewed digest-pinned Node image
- **AND** SHALL execute no lifecycle script

#### Scenario: Applying credential-free network policy
- **WHEN** valid corporate proxy or CA inputs are enabled for managed-extension lock synchronization
- **THEN** the resolver SHALL receive only those resolved credential-free inputs for its network operation
- **AND** SHALL not persist their endpoint or machine-local path in the candidate or diagnostics

#### Scenario: Ignoring present ambient npm configuration
- **WHEN** a known project, user, or global `.npmrc` exists or an npm configuration variable name is present
- **THEN** the managed-extension owner SHALL warn prominently that the detected ambient inputs are ignored
- **AND** SHALL neither read nor apply file contents or environment values
- **AND** SHALL use `https://registry.npmjs.org/` through its isolated temporary configuration

#### Scenario: Omitting an unnecessary ambient-configuration warning
- **WHEN** no known ambient `.npmrc` exists and no npm configuration variable name is present
- **THEN** the managed-extension owner SHALL emit no ambient-configuration warning

#### Scenario: Accepting a complete closure under the public-registry boundary
- **WHEN** the managed-extension owner starts with the fixed isolated `https://registry.npmjs.org/` configuration and generates a complete candidate
- **THEN** every reachable registry package in the accepted candidate SHALL have an HTTPS `resolved` origin of `registry.npmjs.org`
- **AND** acceptance SHALL NOT assert that npm made no transient request to another origin

#### Scenario: Rejecting a foreign lockfile registry origin
- **WHEN** any reachable registry package in a generated candidate has a `resolved` URL with another origin, userinfo, or a non-HTTPS scheme
- **THEN** the managed-extension owner SHALL reject the candidate before transaction readiness
- **AND** SHALL preserve the checked-in lockfile byte-for-byte

#### Scenario: Treating npm redirects as an opaque resolver behavior
- **WHEN** pinned npm follows a registry redirect while generating the candidate
- **THEN** Constructor SHALL NOT claim that it inspected the target before npm sent the redirected request
- **AND** SHALL still reject the generated candidate if any reachable package records a foreign or non-HTTPS `resolved` URL
- **AND** acceptance of public-registry `resolved` URLs SHALL NOT be reported as proof that no transient redirect traffic occurred

#### Scenario: Rejecting a scoped custom registry
- **WHEN** ambient npm configuration maps a managed package scope to a custom registry
- **THEN** the managed-extension owner SHALL ignore the mapping and use only `https://registry.npmjs.org/`
- **AND** SHALL fail normally if the scoped package is unavailable from the public registry

#### Scenario: Rejecting credentials in projected resolver inputs
- **WHEN** the fixed registry input or a proxy/CA input Constructor would project into the resolver contains unsupported credentials
- **THEN** the managed-extension owner SHALL fail before starting the resolver
- **AND** SHALL make no npm registry request

#### Scenario: Not scanning ignored configuration for credentials
- **WHEN** an ignored ambient `.npmrc` or discarded npm configuration variable is present
- **THEN** the managed-extension owner SHALL warn that the input is ignored without reading it to search for credentials
- **AND** SHALL apply only its isolated configuration and validated projected inputs

#### Scenario: Isolating synchronization inputs and outputs
- **WHEN** the managed-extension owner invokes npm
- **THEN** its private staging SHALL contain a generated `package.json` representing only the reviewed exact roots
- **AND** only the resulting candidate `package-lock.json` SHALL be eligible for publication
- **AND** no staging file SHALL become an assembly input or reviewed source

#### Scenario: Preserving the prior lock set on synchronization failure or cancellation
- **WHEN** owner preflight, toolchain assertion, metadata retrieval, candidate validation, generation, transaction commit, or cancellation interrupts `sync-lock`
- **THEN** the complete prior checked-in lockfile set SHALL remain byte-for-byte unchanged
- **AND** temporary manifest, candidate, and staging files SHALL be removed
- **AND** separately owned persistent download caches SHALL not be removed as synchronization candidates

#### Scenario: Separating synchronization from locked assembly
- **WHEN** a reviewed lockfile is passed to `locked-npm-environment-assembly`
- **THEN** assembly SHALL install exactly that lockfile under its fixed `npm ci` contract
- **AND** SHALL NOT invoke a Constructor metadata provider, resolve dependency updates, generate a replacement lockfile, or publish synchronized roots

### Requirement: Assemble and deliver the locked extension closure before Docker build
Before Docker build, the constructor SHALL invoke `locked-npm-environment-assembly` for the reviewed roots and checked-in lockfile, validate the returned tree and evidence, and include only the complete validated extension tree and evidence in the immutable named build context. It SHALL pass `[build.stages.base.node].node_version` and `[build.stages.base.node].npm_version` to the assembler only as verification inputs associated with the same reviewed inventory; the assembler SHALL NOT derive, persist, or define a second expected-version source. BuildKit SHALL copy the closure into `/opt/pi-extensions` without npm networking or npm installation.

#### Scenario: Building a locked extension image
- **WHEN** the reviewed roots and lockfile assemble successfully
- **THEN** Docker SHALL receive the validated extension tree and evidence through the dedicated named context
- **AND** the final image SHALL contain the closure at `/opt/pi-extensions`
- **AND** BuildKit SHALL perform no extension npm network or installation operation

#### Scenario: Rejecting invalid assembled extension evidence
- **WHEN** the assembled tree or evidence is invalid, incomplete, or mismatched
- **THEN** Docker build SHALL fail before the closure enters the final image

#### Scenario: Resolving a real Pi managed root and custom package
- **WHEN** Pi loads a managed root with transitive imports and a user-installed npm package
- **THEN** the managed root and transitive imports SHALL resolve only from the image-owned `/opt/pi-extensions/node_modules` closure
- **AND** the user package SHALL resolve only from the writable `~/.pi/agent/npm` store
- **AND** neither store SHALL be used to mutate or satisfy the other’s packages
- **AND** any duplicate resource entry SHALL be preserved as a suppressed baseline entry outside effective Pi settings while the managed root is active, without changing package/module resolution

### Requirement: Remove managed-extension runtime selection and installation
Managed extensions SHALL be selected only by reviewed roots and the checked-in lockfile at image-build time. The constructor SHALL NOT accept managed-extension runtime overrides, materialize managed extension artifacts for `run`, mount per-package extension blobs, perform managed extension npm installation at container startup, or perform managed extension network access at runtime.

#### Scenario: Running an image with managed extensions
- **WHEN** a container starts from an image built with a valid locked extension closure
- **THEN** managed extensions SHALL be available from the image-owned closure
- **AND** container startup SHALL not perform managed extension artifact materialization, mounting, npm installation, or network access

#### Scenario: Requesting a removed managed-extension override
- **WHEN** a user supplies a managed-extension runtime override
- **THEN** the constructor SHALL reject it with guidance to edit reviewed roots, run `sync-lock`, review, and rebuild
