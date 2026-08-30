## Context

Runtime direct extraction assumes independently reviewed self-contained tarballs, while Pi's planned BuildKit installation uses a separate npm path. General npm graphs require lock placement semantics, but both consumers need the same script-free trust boundary and host evidence.

## Goals / Non-Goals

**Goals:**
- One standalone, pinned and consumer-neutral npm assembly implementation.
- Standard lockfile-v3 resolution input with a strict safe subset.
- Independent host verification, deterministic identity, evidence, and atomic reuse.
- Shared downloads without merged Pi/runtime locks or lifecycle coupling.

**Non-Goals:**
- Resolving or refreshing lockfiles, selecting consumer roots, Pi layout, extension settings, image construction, runtime mounting, CLI guards, vulnerability or license auditing.
- Treating npm cache internals as a public Constructor format.

## Decisions

### Use the inventory-pinned Node image directly

Run the repository-owned assembler script in the reviewed Node image digest rather than building a custom helper image. Receive exact reviewed Node/npm versions from the caller, first reject a reviewed Node version that does not satisfy every preserved `engines.node` constraint declared by any reviewed root before Docker, then assert the container's actual Node/npm versions before npm execution. Include image, tool, script, policy and platform identities in cache keys and evidence. This avoids a bootstrap build and lets dependent changes share exactly one implementation.

### Validate lockfile v3 into a closed internal model

Keep standard `package-lock.json` as persisted resolution truth, but parse only registry nodes, safe `node_modules` placement, exact identities, SRI and supported dependency metadata into immutable DTOs. Apply separate closed field contracts to every reviewed root package entry selected by the plural `RootSpec` inputs and to all remaining transitive package entries. Resolve each reviewed root to its exact lock package path and identify preserved metadata by `(root package identity, lock package path)` so multiple roots cannot overwrite or alias one another.

For every reviewed root, `bin` and `engines.node` are functional metadata, not accepted-and-ignored metadata. Parse each root's `bin` string keys and values, require non-empty unambiguous relative paths, reject absolute paths, `..`, empty components and backslashes, and preserve validated declarations keyed by that root identity and path. Parse each root's `engines` as a closed object, validate `engines.node` as a supported strict node-semver range, and preserve it under the same root key. Explicitly accept-and-ignore each root's `license`. All declared reviewed-root engine ranges must be satisfied by the one reviewed exact Node version before effects.

Published Pi locks contain transitive `bin`, `engines`, and `license`, so transitive nodes explicitly accept those fields under separate policies. Transitive `bin` must be an object of non-empty string keys and values and `license` must be a string; both are discarded after shape validation and cannot affect DTO or environment identity, dependency/placement validation, assembler behavior or npm flags, executable-link creation, tree evidence, or assembled output. Transitive `bin` cannot create links under the fixed `--no-bin-links` policy.

Transitive `engines` is accepted-and-ignored metadata, not an authoritative compatibility constraint. Parse it as a closed object containing only optional `node`; require `engines.node`, when present, to be a non-empty string and validate its syntax with the same strict npm/node-semver range implementation used for dependency ranges, including comparator conjunctions and `||` disjunctions exercised by the published Pi fixture. Discard it after validation and do not preserve it in DTOs or evidence. npm normally treats dependency engine mismatches as warnings unless `engine-strict` is enabled. Constructor does not enable `engine-strict`, so a syntactically valid transitive range is accepted even when the reviewed Node version does not satisfy it and Constructor emits no custom compatibility diagnostic for it. npm's own pinned execution may produce native `EBADENGINE` output; this change neither suppresses nor strengthens that output into a Constructor contract. Only `engines.node` declarations belonging to reviewed roots are authoritative; every such declaration is preserved with its root identity/path, checked before effects, and recorded with the reviewed version in validation evidence. Reject malformed metadata or unsupported engine keys/ranges, every unknown root or transitive field, and unsupported npm source/layout features before effects. This avoids inventing a lock format without exposing materializers to npm's full schema.

### Separate pure input preflight from effectful assembly

Expose a side-effect-free assembler input-validation/preflight call that receives exact lock bytes, plural `RootSpec` inputs, platform, and caller-owned reviewed Node/npm versions. It performs closed parsing, root/closure validation, keyed root-metadata extraction, transitive-metadata handling, and every reviewed-root engine check, then returns an immutable `ValidatedAssemblyInput`. That value binds the exact lockfile digest, canonical roots, platform, reviewed tool versions, complete validated closure, and root metadata keyed by package identity/path. Preflight performs no Docker, network, cache, staging, lock, or publication operation.

The Docker-backed assembly call accepts only this validated value plus matching exact lock bytes and assembler identity inputs. It rechecks the digest/tool/platform bindings before effects and rejects substitution instead of reparsing a different input. Consumers may inspect keyed root metadata after pure preflight, but successful preflight is not an assembled environment and carries no output path or output evidence.

### Keep a published Pi compatibility fixture

Check in an immutable copy of a published, pinned Pi lockfile under `tests/data/` together with provenance identifying its published source, Pi version and exact SHA-256. Tests derive roots from exact versions of top-level locked nodes rather than manifest ranges, parse the complete closure for `linux-x64`, permit only evidence-backed `platform-inapplicable` omissions, and prove repeated model and identity derivation is deterministic. Tests never read `/opt/pi` or the currently installed agent. This compatibility fixture supplements rather than replaces focused synthetic rejection and security fixtures.

### Delegate placement to npm, not trust decisions

Execute `npm ci --ignore-scripts --no-bin-links --no-audit --no-fund` in empty staging. npm owns graph placement and SRI download verification; Constructor owns input policy, network scope, post-install closure/filesystem validation and publication. `hasInstallScript` is permitted because scripts remain disabled and consumer acceptance validates usable roots. The assembler preserves validated executable metadata separately for every reviewed root and verifies that each installed path, including symlink resolution, remains contained in the assembled environment, but deliberately creates no executable link. Consumers alone choose launcher location, contents and policy.

### Publish a canonical hashed tree

Hash every regular file and describe directories and contained symlinks in deterministic path order. Environment identity is computed from canonical roots/package input, lock bytes, assembler image and asserted tools, script/policy versions and platform. Cache hits repeat no-follow tree verification; performance is secondary to host evidence.

### Separate opaque downloads from immutable outputs

Use one assembler-identity npm cache for download reuse, but publish each environment independently. Consumers select retention and placement after receiving a neutral result. npm cache corruption can only cause verified reuse, refetch, or failure; it cannot change locked identity.

### Run as the invoking host identity

Create owner-private staging and run the container as host UID/GID with a private HOME, narrow read-only inputs, opaque cache and one writable output. This prevents root-owned output while keeping Docker daemon and container filesystem boundaries explicit.

### Apply one network and cancellation boundary

Render resolved credential-free proxy and CA inputs through structured Docker arguments with redaction and fixed trust mounts. Hold an identity lock across cache check, assembly, validation and publication; cancel the container and clean staging on every BaseException while preserving committed trees.

## Risks / Trade-offs

- [npm versions change lock behavior] → Pin image digest, assert tool versions and include them in identity/evidence.
- [Full tree verification is expensive] → Accept the cost; avoid weaker metadata-only cache hits.
- [Install scripts are required for a consumer] → Keep scripts disabled and fail consumer acceptance rather than silently executing code.
- [Optional dependencies vary by platform] → Support only declared platform and record validated omissions explicitly.
- [Host UID lacks an image passwd entry] → Use numeric UID/GID, private HOME and paths requiring no account lookup.
- [Consumer requirements leak into the shared layer] → Preserve neutral validated root executable declarations but never derive a consumer launcher; dependent changes own launcher location, contents, evidence, layout and UX.

## Migration Plan

1. Introduce pure lock, identity, manifest and evidence contracts.
2. Add secure cache/staging and standalone Docker execution boundaries.
3. Add output validation, locking, atomic publication and revalidation.
4. Prove two synthetic consumers can share downloads while retaining independent outputs.
5. Dependent changes adopt the capability separately; rollback leaves unused cache entries inert.
