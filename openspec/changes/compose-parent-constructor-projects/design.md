## Context

`decouple-constructor-project-root` establishes a selected constructor project with fixed project-owned inventory, Dockerfile, local inputs, and generated outputs. Its self-contained build-context rule is the prerequisite and the contract replaced here: concrete projects need to inherit reviewed configuration and build support from explicit parent constructor projects without introducing override precedence or implicit ancestor discovery.

The current repository also mixes host implementation under `docker/` with files copied by the Dockerfile, while `.docker-local/` contains a machine-local build input. Composition needs explicit reviewed and local asset namespaces rather than a broad copy of each project root.

Implementation is blocked until `decouple-constructor-project-root` is implemented, synchronized, and archived.

## Goals / Non-Goals

**Goals:**

- Resolve a portable, explicit, multi-level parent-project chain with physical cycle and hard-link alias detection.
- Preserve one owner for every reviewed setting and inherited asset; never resolve collisions by precedence.
- Produce a deterministic merged reviewed inventory before CLI overrides.
- Compose a private Docker context from narrowly allowed control files, inherited reviewed assets, and leaf-only local assets.
- Preserve executable modes, snapshot consistency, machine-local isolation, and safe cleanup.
- Validate the complete project graph without Docker or network access.

**Non-Goals:**

- Multiple parents, mixins, optional parents, implicit ancestor search, remote parents, or environment-variable/tilde expansion.
- Setting or asset overrides, array concatenation, symlink assets, special files, or inherited local state.
- Preserving comments, source TOML formatting, ownership, ACLs, xattrs, timestamps, or hard-link topology in the composed context.
- Applying CLI overrides to the materialized merged `docker-constructor.toml`.
- Compatibility aliases for old build-asset paths after repository migration.

## Decisions

### Treat `parent-project` as project metadata

Schema 1 accepts an optional top-level `parent-project` string naming an absolute directory or a directory relative to the declaring project. Relative references resolve from that declaring project, never CWD or the leaf. `~` and environment interpolation are unsupported. The physical directory must contain the fixed `docker-constructor.toml`.

A directory reference is preferred over a file reference because inventory, assets, and possible Docker controls are inherited from one constructor-project layer.

### Resolve a physical linear chain with a 32-layer limit

Resolution walks leaf to base, physically resolves each project directory, and opens each fixed inventory as a regular file. It tracks canonical paths and, on POSIX, `(st_dev, st_ino)` from the same descriptor used to read TOML. Repeated paths or identities are cycles/physical aliases. Symlinked path components are accepted and normalized; symlink assets and a symlink inventory leaf are not.

The chain includes at most 32 projects including the leaf. This supports intentional layering while bounding malformed inputs.

### Merge globally disjoint raw TOML leaves

Composition proceeds base to leaf. Tables are structural, arrays are atomic leaf values, and `schema` plus `parent-project` are metadata. Any other leaf path declared by more than one layer is an error even when values are equal. Provenance maps each leaf to its source for diagnostics.

The terminal base must validate independently, then every base-to-current effective prefix validates through the existing typed schema. The final validated raw mapping—not a model populated with defaults—is deterministically serialized without `parent-project`. This preserves explicitly reviewed values and is the `docker-constructor.toml` placed in the build context.

CLI overrides apply afterward through existing effective-resolution paths and continue to reach Docker through projections and build arguments.

### Use narrow reviewed and local asset namespaces

Only `docker-assets/` participates in inherited asset composition. It is optional per layer; if present it must be a regular directory containing only regular files and directories. This allowlist avoids copying source-control state, documentation, local companions, generated outputs, or host implementation accidentally.

`.docker-assets-local/` replaces `.docker-local/`, is read only from the leaf, and is always represented as a directory in the composed context. Parent local companions, `.env`, local assets, and generated outputs are ignored. Corporate trust resolves only the leaf `.docker-assets-local/corporate-ca-bundle.crt`.

Repository implementation migrates Dockerfile-consumed inputs out of the host-side `docker/` tree into `docker-assets/`; no old-path fallback remains.

### Reject every cross-layer asset ambiguity

Asset manifests are built before Docker applies `.dockerignore`. Equal relative file paths, file/directory conflicts, and POSIX inode aliases across layers fail. Shared structural directories are allowed only with equal permission bits; the `docker-assets/` root is materialized as `0755`. Hard links within one layer are accepted but copied as independent regular files. Logical paths are exact and case-sensitive; destination filesystem failures remain path-specific materialization errors.

Files and uniquely owned directories preserve `0o777` permission bits. Ownership, special mode bits, ACLs, xattrs, timestamps, and hard-link topology are not preserved. Empty directories are preserved.

### Select Docker controls nearest-child-first

Build walks leaf to base for the first existing `Dockerfile`. Absence continues the search; an existing non-regular entry fails rather than falling back. Build fails if no layer supplies one. `.dockerignore` is used only from that same layer; if absent, none is synthesized or inherited separately. A non-regular same-layer `.dockerignore` fails. Other Dockerfiles and ignore files are controls, not assets.

The constructor does not rewrite `.dockerignore`. Excluding the merged inventory or local assets therefore retains normal Docker missing-source behavior.

### Materialize a descriptor-checked private snapshot

An executed non-dry build creates a unique private context under leaf `.docker-generated/build-contexts/`. The allowlist is the selected Dockerfile and paired ignore file, generated merged inventory, composed `docker-assets/`, and leaf `.docker-assets-local/`. Source files are opened no-follow, verified with `fstat`, copied from that descriptor, and checked for mutation during copying. A changed source fails rather than producing a mixed snapshot.

`build --dry-run` resolves and validates the chain, effective prefixes, Docker controls, local policy, and complete asset manifests, then plans the private context path entirely in memory and renders the complete Docker vector against that planned path. It SHALL NOT create or clean a context, create generated directories or files, acquire the build lock, perform stale cleanup, publish a projection, invoke Docker, or otherwise mutate filesystem or project state. Planning a path rather than materializing it preserves the existing complete-vector dry-run contract without weakening composed-context validation.

A per-leaf exclusive build lock covers every executed-build write to fixed paths beneath leaf `.docker-generated/`, including effective build-projection publication, stale cleanup, context materialization, Docker execution, and own-context deletion. No effective projection or other fixed generated build output may be published before lock acquisition. This ensures a waiting build with different overrides cannot overwrite the projection that belongs to the build currently executing Docker. Caller-directed outputs outside the fixed leaf-generated layout retain their explicit destination and do not broaden the lock's ownership boundary. Cleanup only handles constructor-named entries beneath the fixed context root without following symlinks. Success, failure, and interruption receive best-effort own-context cleanup; a later locked build removes stale safe entries.

### Separate validation depth by command

`validate` performs read-only chain resolution, prefix validation, Docker control selection, and complete asset-manifest validation without context creation, Docker, or network. `build` repeats those checks against the files it snapshots. Commands that only consume configuration resolve and validate the chain but do not require a Dockerfile or scan assets.

`show` exposes merged configuration without changing its public data shape; provenance appears in path-specific conflict, cycle, and prefix diagnostics. `run` uses merged runtime policy while retaining leaf-only local state and does not infer whether an existing image matches changed build settings.

Effective projections, locks, private contexts, and default evidence output remain beneath leaf `.docker-generated/`. An explicit evidence `--output-dir` remains caller-directed even outside the leaf and redirects only evidence; it does not re-root parent resolution, projections, locks, contexts, local companions, or local assets.

## Risks / Trade-offs

- **[Parent edits affect many children]** → Explicit reviewed references, prefix validation, deterministic merged output, and normal rebuild requirements make the dependency visible.
- **[Strict disjointness rejects benign duplicates]** → Preserve one-owner semantics and provide both physical owners in diagnostics instead of introducing precedence.
- **[Context copying adds build latency and disk use]** → Restrict scanning to `docker-assets/`, use private temporary contexts, and clean under the build lock.
- **[A crash leaves sensitive local assets]** → Use owner-private permissions and locked stale cleanup beneath a fixed generated root.
- **[Concurrent builds of one leaf are serialized]** → Acquire the leaf lock before projection publication or any other fixed generated write and hold it through Docker and context cleanup; different leaf projects remain concurrent.
- **[Migration touches many Dockerfile paths]** → Inventory every repository-owned `COPY` input and migrate code, tests, docs, and specs atomically.
- **[Parent specs depend on an active predecessor]** → Do not implement until `decouple-constructor-project-root` is archived and synchronize these deltas against its resulting main specifications before apply.

## Migration Plan

1. Complete, synchronize, and archive `decouple-constructor-project-root`.
2. Add parent-chain and disjoint raw-inventory resolution while preserving standalone schema-1 behavior.
3. Introduce manifest validation, Docker control selection, locking, and private context materialization.
4. Move repository-owned Docker build inputs from `docker/` to `docker-assets/` and `.docker-local/` to `.docker-assets-local/`; update all Dockerfile paths in the same phase.
5. Route build, validate, read-only, runtime, and corporate-trust consumers through the resolved chain and leaf-local boundaries.
6. Update tests, maintained documentation, examples, ignore rules, and semantic scans; remove all old build-asset path references.
7. Rollback requires reverting project layouts, Dockerfile paths, resolver behavior, and documentation together because no compatibility fallback is retained.

## Open Questions

None. Parent syntax, path identity, depth, merge rules, validation scope, asset namespaces, collision policy, Docker control selection, executed and dry-run context lifecycles, local-state ownership, override boundary, and predecessor sequencing are fixed.
