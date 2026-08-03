## Context

`replace-compose-with-direct-docker` establishes a host resolver that selects one reviewed artifact per runtime extension and mounts a narrow per-launch projection into the container. Its Stage 10 installer still downloads each selected URL inside the container, verifies SRI, and installs into mounted `/home/dev/.pi`. This duplicates selection knowledge across the host/container boundary, requires runtime network access and temporary downloader state, and complicates the guarantee that package execution consumes the verified bytes.

The host already has the exact selected URL and integrity before rendering `docker run`. Runtime overrides mean the selected version is known at launch planning time, not necessarily at image build time. Therefore this change materializes only the effective selections during host launch preparation rather than baking defaults or the complete reviewed catalog into the image.

This change depends on the direct-run projection, rendering, and installer APIs from `replace-compose-with-direct-docker` and supersedes their container-download flow.

## Goals / Non-Goals

**Goals:**

- Download each selected runtime artifact at most once per integrity identity and reuse it across launches.
- Verify bytes on the host before atomic cache publication and before any Docker execution.
- Mount only selected blobs as individual read-only file mounts.
- Keep URLs, cache roots, host paths, unselected artifacts, and policy out of the container projection.
- Re-verify mounted bytes inside the container and install the exact verified bytes without reopening mutable named temporary files.
- Support concurrent launches, cache corruption recovery, interruption cleanup, dry-run, and cache-hit launch without extension-download network access.

**Non-Goals:**

- Baking runtime artifacts into the Docker image or making runtime selections image build inputs.
- Downloading the entire reviewed artifact catalog.
- Adding a public `prefetch` command or expanding the seven-command facade.
- Replacing the reviewed artifact catalog, runtime override policy, or update discovery.
- Treating the cache as an authoritative source; reviewed URL and integrity remain authoritative.

## Decisions

### Materialize during run preparation, not Docker build

`run` resolves the effective runtime selection and ensures each selected blob exists before projection publication and Docker execution. A build cannot know later runtime overrides; embedding all catalog entries would enlarge the image, expose unselected artifacts, and make runtime catalog edits invalidate build layers. Build-time warming is intentionally excluded from the initial change so launch correctness has one owner.

### Use integrity as content identity

The cache key is a canonical validated algorithm plus digest, encoded as filesystem-safe fixed components beneath a constructor-owned root such as `.docker-generated/runtime-artifacts/blobs/<algorithm>/<digest>.tgz`. Package names, versions, URLs, redirects, and caller-provided paths do not participate in path construction. Different selections with identical integrity share one blob.

All cache paths pass no-symlink and containment checks. The constructor-owned `blobs` and `locks` roots, per-algorithm directories, and temporary download directories are private to the invoking user. Their shared repository parents, `.docker-generated` and `.docker-generated/runtime-artifacts`, may retain group read/write permissions required by the rootless-Docker source workflow and are not made private by artifact materialization. Published blobs are regular files without group/other write access; restrictive permissions apply only to constructor-owned cache copies, never to repository source files.

### Publish verified blobs atomically under per-identity coordination

A cache miss acquires a per-integrity lock, rechecks the cache, downloads to a unique owner-only temporary file in the cache filesystem, streams the declared digest, and publishes only matching bytes through a no-partial atomic operation. Failure, cancellation, and interruption remove private temporary state and release the lock. Concurrent contenders either reuse the winner or publish the same verified identity; they never expose partial bytes.

Every cache hit is revalidated before launch. A missing, malformed, symlinked, non-regular, or digest-mismatched entry is not used; under the lock it is removed or quarantined and rematerialized. If rematerialization cannot succeed, launch fails before Docker.

### Separate host artifact references from the runtime DTO

Host launch planning retains URL, integrity, resolved absolute cache source, and deterministic container target. The mounted projection contains package, version, validation metadata, integrity, and a canonical artifact identifier sufficient to derive a path beneath the fixed container root `/run/pi-cli/runtime-artifacts`. It contains neither downloadable URL nor host cache path.

The container target is derived only from validated canonical identity. The installer rejects absolute paths, traversal, alternative roots, unknown artifact fields, and mismatch between artifact identifier and integrity.

### Mount selected blobs individually and read-only

The Docker vector adds one deterministic `type=bind` file mount per unique selected integrity. It never mounts the cache root or unrelated blobs. Source paths are absolute validated regular files; targets are unique fixed-root paths; mounts are read-only. Duplicate identities produce one mount while multiple projection entries may reference it.

Projection and artifact mounts are planned before effects and rendered deterministically. Docker execution begins only after every required source blob has been materialized and revalidated.

### Keep defense-in-depth verification and exact-byte package execution

The container has no artifact downloader. It opens each fixed mounted blob without following symlinks, validates type and containment, reads and verifies SRI, and gives the exact verified bytes to the package-execution boundary. The production boundary uses an immutable inherited descriptor or equivalent sealed byte source; it does not write the bytes to a mutable named file that `pi install` later reopens.

Post-install package name/version metadata and ownership remain authoritative. Matching installed packages skip artifact reads and package execution after ownership validation.

### Dry-run is effect-free

Dry-run may perform read-only cache inspection and report hits/misses, projected artifact identities, and complete planned mount vectors. It does not download, lock for publication, create cache/projection files, execute package tooling, or run Docker. A cache miss is reported as planned materialization rather than treated as successful cached availability.

## Risks / Trade-offs

- [Cache grows without bound] → Keep eviction/GC out of launch correctness and plan a separate policy; content identity prevents duplicate bytes.
- [Concurrent launch observes partial content] → Use same-filesystem private temporary files, per-identity coordination, integrity verification, and atomic publication.
- [Host cache entry is modified after verification] → Publish non-writable regular files, mount the selected inode read-only, verify again in-container, and install from exact verified bytes.
- [A redirect changes download origin] → The reviewed URL remains the only requested identity and SRI remains byte authority; transport redirect policy stays explicit and tested.
- [Cache root is moved or symlinked] → Resolve trusted roots, reject symlinks and escapes at every lifecycle boundary, and never accept cache paths from the runtime projection.
- [Host materialization adds latency to first launch] → Reuse verified content-addressed hits; subsequent launches and offline cache-hit launches avoid network.
- [Two active changes edit Stage 10 contracts] → Complete or deliberately amend `replace-compose-with-direct-docker` first, then implement this change as the single replacement flow.

## Migration Plan

1. Add host cache/materialization contracts and run planning without changing container downloading.
2. Extend the runtime projection and Docker renderer to mount selected blobs individually.
3. Switch the container installer to mounted artifacts and remove downloader/workspace production behavior.
4. Remove transitional URL fields from the runtime DTO once all launch paths provide mounted identities.
5. Validate cache miss/hit, corruption, concurrency, offline hit, override selection, and container installation before deleting obsolete tests and boundaries.

Rollback restores container-side downloading and URL-bearing runtime projections; cache files are non-authoritative and may be safely left unused or removed.

## Open Questions

- Cache eviction and size reporting are intentionally deferred; a later change may integrate them with `doctor` or an existing cache policy.
- Whether a future `build` opportunistically warms default runtime artifacts remains separate from required run preparation.
