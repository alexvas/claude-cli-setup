## Context

The HTTP update-discovery cache currently defaults to `${XDG_CACHE_HOME:-~/.cache}/pi-cli/versioning`, while the verified runtime-artifact cache defaults to a mutable path inside the repository checkout. Rootless Docker may leave that repository path owned by a mapped `docker-dev` identity. The host constructor can traverse it through group permissions but cannot enforce the owner-only mode required for cache publication, producing `EPERM` before launch.

Runtime projections and evidence are per-checkout generated output, not reusable cache entries. They remain under `.docker-generated/`.

## Goals / Non-Goals

**Goals:**
- Use one user-scoped XDG root for every persistent constructor cache.
- Preserve isolated subtrees for HTTP responses and verified artifact blobs.
- Enforce owner-only permissions without changing permissions on `XDG_CACHE_HOME` or unrelated parents.
- Preserve local machine-specific cache-root configuration and all existing container mount/security boundaries.

**Non-Goals:**
- Moving runtime projections, evidence, Docker image/build caches, Pi home, or project files out of their current locations.
- Automatically importing, trusting, deleting, or chmodding checkout-local artifact caches.
- Documenting legacy cache paths in maintained README guidance.
- Sharing a cache between Unix users or weakening verification/atomic publication.
- Adding a new reviewed inventory field or exposing cache paths to containers.

## Decisions

### Use an XDG project root with named subtrees

The new default root is `${XDG_CACHE_HOME}/docker-constructor` when `XDG_CACHE_HOME` is non-empty and absolute: a missing explicit XDG directory is created with `0700`, while an existing one must be writable without having its mode changed. When XDG is empty or non-absolute the root is `~/.cache/docker-constructor`; an explicit absolute non-directory or unwritable XDG path is an error rather than a fallback. HTTP response entries move from the legacy `${XDG_CACHE_HOME:-~/.cache}/pi-cli/versioning` path to the new root's `versioning/` child; verified runtime artifacts move from the legacy checkout-local `.docker-generated/runtime-artifacts/blobs` path to the new root's `runtime-artifacts/blobs/` child, with sibling private lock and temporary state.

A local `[cache].dir` selects the root instead of a single consumer's leaf directory. Consumers derive their own named child paths. This avoids mixing response JSON, locks, and blobs and makes one local override cover all persistent caches.

### Retire the HTTP-only `--cache-dir` option

`check-updates --cache-dir` is removed because it can only redirect HTTP cache data and would create a second, ambiguous cache-location model. A user who needs a non-default location configures the dedicated root in the resolved local companion; both cache consumers derive their named children from it. Parser rejection treats the retired option as unsupported and performs no fallback.

### Use reviewed inventory as the only TTL source

The constructor SHALL remove the command-local `check-updates --cache-ttl` option. HTTP cache TTL SHALL be configured only through reviewed `[cache].ttl` in `docker-constructor.toml`.

TTL is portable update-discovery policy rather than machine-local storage state. Allowing a command-line TTL override bypasses the reviewed policy and creates two sources of truth. Callers that need to bypass cache behavior for one invocation SHALL continue to use `--no-cache`.

Removing `--cache-ttl` is an explicit CLI compatibility break independent of cache-path relocation. Parser rejection treats the retired option as unsupported, does not override TTL, and performs no fallback.

### Require a dedicated local cache root

A local `[cache].dir` is an explicitly dedicated constructor-owned directory, not a general cache parent. Its configured value must already be absolute; `~` expansion is not accepted for local configuration. Pure path resolution lexically normalizes it and rejects values equal to `XDG_CACHE_HOME`, the invoking user's home directory, or the filesystem root, and values that are ancestors of `XDG_CACHE_HOME`. The filesystem layer separately validates the selected existing root. This permits the constructor to secure the selected root and its descendants while never changing its parents; a dedicated child such as `${XDG_CACHE_HOME}/docker-constructor-custom` is valid.

### Isolate shared cache infrastructure in one module

`docker/versioning/cache_storage.py` SHALL own the shared cache-path and directory-security infrastructure used by persistent cache consumers.

The module SHALL provide two separate layers:

1. Pure path resolution that:
   - returns a local root only when its configured value is absolute, and lexically normalizes it without `~` expansion;
   - returns an explicit `XDG_CACHE_HOME` candidate only when the environment value is non-empty and absolute, otherwise the `~/.cache` fallback candidate;
   - rejects lexically unsafe local roots such as the filesystem root, the user's home directory, `XDG_CACHE_HOME`, or an ancestor of `XDG_CACHE_HOME`;
   - derives the `versioning` and `runtime-artifacts/blobs` child paths;
   - performs no filesystem reads or mutations.

2. Filesystem validation and hardening that:
   - inspects an existing selected root and constructor-owned descendants with no-follow operations;
   - rejects symlinks, non-directories, foreign ownership, and paths that cannot be secured;
   - creates missing constructor-owned directories with mode `0700`;
   - secures existing invoking-user-owned directories to mode `0700`;
   - never changes permissions on the resolved root's parents.

The filesystem layer creates a missing explicit XDG candidate with `0700`, accepts an existing writable directory without changing its mode, and rejects an existing non-directory or unwritable XDG candidate without fallback. This keeps XDG filesystem eligibility outside pure resolution.

The filesystem layer MAY perform `lstat`-, descriptor-, and ownership/mode inspection required to validate and secure cache paths. It SHALL keep inspection separate from pure path resolution and SHALL not read cache-entry contents as part of root validation.

The module SHALL NOT import CLI, launcher, transport, HTTP response-cache, or artifact-verification modules. `cache.py` remains responsible for HTTP cache entry format and TTL behavior; `artifact_cache.py` remains responsible for content addressing, blob verification, locks, and atomic publication. Both SHALL consume `cache_storage.py` rather than duplicate root resolution or directory-security behavior.

### Treat only constructor-owned descendants as private

The cache root and all cache children created or used by the constructor must be directories owned and securable by the invoking user with mode `0700`; HTTP cache files are `0600`, and verified blobs remain non-writable (`0444`). The implementation must use no-follow/descriptor-relative operations for the artifact subtree and fail before network or Docker activity if it cannot secure an existing constructor-owned directory.

Existing `XDG_CACHE_HOME` and its ancestors are not chmodded, because they may legitimately be shared by other applications; only a missing explicit XDG directory may be created with `0700`. Group access to a constructor cache is insufficient: only the owner can satisfy the hardening contract.

### Do not migrate legacy cache data automatically

A new default starts empty. Neither legacy cache is copied, read, or trusted automatically: the checkout-local artifact cache may be group-writable, mapped-owned, or tampered with, and the legacy HTTP cache belongs to the old `pi-cli` namespace. The first runtime launch materializes selected artifacts at the new root and the first update request populates the new HTTP cache. Both legacy directories remain unchanged until the user chooses to remove them manually. This prevents a permission repair or namespace move from becoming an implicit trust transfer.

## Risks / Trade-offs

- **First use rebuilds entries formerly held by legacy caches** → Materialize verified blobs and populate HTTP responses at the new root; preserve both legacy caches until the user chooses cleanup.
- **Existing local `cache.dir` users see namespaced children** → Document the layout and test the migration; it remains local-only.
- **An unsecurable stale XDG subtree blocks launch** → Emit the exact path and an owner/cleanup recovery action; do not silently relax permissions.
- **Changing global XDG cache permissions can affect other software** → Never chmod the XDG parent, only the `docker-constructor` descendant.

## Migration Plan

1. Resolve the effective cache root from local `[cache].dir` or the XDG default; reject normalized shared/dangerous roots without filesystem I/O.
2. Before use, validate the selected root and private named cache subtrees with the filesystem layer without chmodding any parent.
3. Use the new HTTP root for update discovery and the new runtime-artifact root for dry-run inspection, materialization, mount planning, locks, scripts, and documentation.
4. On the first update request, populate the new `docker-constructor/versioning` cache; do not read, copy, mutate, or delete the legacy `pi-cli/versioning` cache.
5. Leave `.docker-generated/runtime-artifacts` and `${XDG_CACHE_HOME:-~/.cache}/pi-cli/versioning` untouched. Keep their migration behavior in this change's contract and implementation tests; maintained README guidance describes only the active cache layout.
6. Roll back by restoring the prior binary; retained legacy cache data remains available to that binary.
