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

Run the repository-owned assembler script in the reviewed Node image digest rather than building a custom helper image. Assert Node/npm versions and include image, tool, script, policy and platform identities in cache keys and evidence. This avoids a bootstrap build and lets dependent changes share exactly one implementation.

### Validate lockfile v3 into a closed internal model

Keep standard `package-lock.json` as persisted resolution truth, but parse only registry nodes, safe `node_modules` placement, exact identities, SRI and supported dependency metadata into immutable DTOs. Reject unsupported npm source/layout features before effects. This avoids inventing a lock format without exposing materializers to npm's full schema.

### Delegate placement to npm, not trust decisions

Execute `npm ci --ignore-scripts --no-bin-links --no-audit --no-fund` in empty staging. npm owns graph placement and SRI download verification; Constructor owns input policy, network scope, post-install closure/filesystem validation and publication. `hasInstallScript` is permitted because scripts remain disabled and consumer acceptance validates usable roots.

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
- [Consumer requirements leak into the shared layer] → Keep result DTO and tests neutral; dependent changes own layout and UX.

## Migration Plan

1. Introduce pure lock, identity, manifest and evidence contracts.
2. Add secure cache/staging and standalone Docker execution boundaries.
3. Add output validation, locking, atomic publication and revalidation.
4. Prove two synthetic consumers can share downloads while retaining independent outputs.
5. Dependent changes adopt the capability separately; rollback leaves unused cache entries inert.
