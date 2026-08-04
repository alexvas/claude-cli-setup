## 1. Align the Active Runtime Design

- [x] 1.1 Confirm the direct-Docker run orchestration, runtime projection lifecycle, and protected installer from `replace-compose-with-direct-docker` are complete or deliberately amend that change so this work replaces rather than duplicates container downloading.
- [x] 1.2 Add failing architecture tests requiring runtime URLs to remain host-only and forbidding container installer imports or production boundaries for download transport and download workspaces.
- [x] 1.3 Add failing end-to-end planning tests proving invalid inventory, override, artifact identity, cache root, or mount target fails before cache mutation, projection publication, gateway effects, or Docker execution.

## 2. Define Content-Addressed Cache Contracts

- [x] 2.1 Add failing tests for canonical integrity identities, filesystem-safe cache keys, fixed cache layout, root containment, no-symlink traversal, regular-file requirements, and private permissions.
- [x] 2.2 Add immutable typed host DTOs for selected artifact materialization inputs and verified cache results without importing facade, parser, presentation, Docker execution, or container installer modules.
- [x] 2.3 Add injected cache filesystem, streaming transport, per-identity coordination, and clock/temporary-state boundaries with structured miss, corruption, transport, integrity, publication, cancellation, and interruption failures.
- [x] 2.4 Implement deterministic cache path derivation solely from validated algorithm and digest; reject URL-, package-, version-, and caller-path-derived cache locations.

## 3. Materialize and Publish Host Artifacts

- [x] 3.1 Add failing tests for valid cache hits with zero network, cache misses, exact reviewed URL fetches, streaming SRI verification, empty or malformed content, and unsupported integrity algorithms.
- [x] 3.2 Add failing concurrency tests proving same-identity launches coordinate publication, recheck after lock acquisition, never expose partial files, and converge on one verified blob.
- [x] 3.3 Add failing corruption tests for symlinks, directories, special files, digest mismatch, truncated blobs, unsafe roots, and failed repair without Docker execution.
- [x] 3.4 Implement private same-filesystem temporary downloads, installer-owned host integrity verification, atomic publication, published-file permissions, revalidation, and unconditional temporary/lock cleanup on success, failure, cancellation, `KeyboardInterrupt`, and `SystemExit`.
- [x] 3.5 Add tests and implementation for deduplicating multiple selected entries with the same integrity identity while preserving each package's projected identity/version metadata.

## 4. Narrow the Runtime Projection

- [ ] 4.1 Add failing DTO tests replacing downloadable URL fields with canonical mounted-artifact identity while preserving package, exact version, integrity, and safe metadata validation.
- [ ] 4.2 Add failing closed-schema tests rejecting URL, host cache root/path, absolute or traversal artifact paths, source/update/override metadata, unselected artifacts, and build fields.
- [ ] 4.3 Update pure runtime resolution to return separate host materialization selections and container-safe projection entries from the same reviewed exact artifact selection.
- [ ] 4.4 Update atomic per-launch projection serialization/validation and compatibility tests for deterministic ordering, duplicate content identities, private lifecycle, and fixed mounted-artifact root semantics.

## 5. Render Individual Read-Only Artifact Mounts

- [ ] 5.1 Add failing pure-rendering tests for one deterministic read-only file mount per unique selected integrity, absolute validated host sources, fixed unique container targets, and no cache-root/unselected mounts.
- [ ] 5.2 Extend immutable run render inputs with verified artifact mount DTOs and render argument tuples without shell execution or display-string reuse.
- [ ] 5.3 Add collision and safety tests for duplicate targets, source/target aliasing, writable mounts, directory mounts, traversal, symlinks, missing blobs, and non-regular files before Docker execution.
- [ ] 5.4 Update command display tests so shell-escaped dry-run output includes projected artifact mounts without exposing reviewed URLs or unrelated cache contents.

## 6. Integrate Run Materialization Transaction

- [ ] 6.1 Add failing orchestration tests for the order: validate and plan → inspect/materialize all selected blobs → publish private projection → perform gateway operations → execute Docker → clean private projection.
- [ ] 6.2 Add failure-order tests proving materialization failure prevents projection publication, gateway persistence/repair, and Docker execution, and later failures do not delete shared verified blobs.
- [ ] 6.3 Implement host materialization and verified mount injection in the internal run transaction with structured results and no prompts or presentation imports.
- [ ] 6.4 Implement dry-run as read-only cache inspection and deterministic planning only: report hits/misses and complete mounts without download, lock/publication, projection creation, gateway mutation, package execution, or Docker.
- [ ] 6.5 Add cache-hit offline tests proving a launch performs no extension artifact network request, plus cache-miss transport failure tests proving actionable pre-Docker failure.

## 7. Simplify the Container Installer

- [ ] 7.1 Add failing installer tests for fixed-root mounted artifact lookup, read-only/regular/no-symlink validation, artifact identity/integrity agreement, exact-byte verification ordering, and missing/corrupt mount failures.
- [ ] 7.2 Remove `ArtifactDownloader`, download workspace, URL handling, mutable downloaded-path lifecycle, and container `curl` behavior from runtime installer contracts and production wiring.
- [ ] 7.3 Implement mounted-blob reading and defense-in-depth SRI verification before package execution while retaining idempotent metadata prechecks, post-install name/version validation, ownership checks, and failure cleanup.
- [ ] 7.4 Ensure the production package boundary consumes the exact verified bytes through an immutable inherited descriptor, sealed byte source, or equivalent mechanism and never reopens a mutable named temporary file.
- [ ] 7.5 Update entrypoint/module CLI tests to prove installation needs no artifact network, starts only after Pi-home ownership repair, runs as `dev`, and aborts before Pi launch on mounted-artifact or package validation failure.

## 8. Introspect Security and Scope

- [ ] 8.1 Review host/cache trust boundaries for symlink swaps, cache poisoning, partial publication, same-UID mutation, lock abandonment, mount-source replacement, and exact-byte package execution.
- [ ] 8.2 Confirm the container receives no reviewed inventory, effective build projection, downloadable URL, host cache path, update provider, override policy, unselected blob, or broad cache-directory mount.
- [ ] 8.3 Confirm runtime artifact changes do not invalidate Docker build layers and `build` does not become responsible for launch correctness or mandatory cache warming.
- [ ] 8.4 Run focused architecture/import checks proving facade concerns remain outside materialization, rendering, run orchestration, and installer internals.

## 9. Validate and Document

- [ ] 9.1 Update maintained README/runtime documentation to describe host materialization, first-launch network behavior, cache-hit offline launches, individual read-only mounts, and cache-miss failures without adding a public `prefetch` command.
- [ ] 9.2 Run cache, projection, rendering, run-orchestration, installer, entrypoint, ownership, concurrency, cancellation, and failure-recovery tests with fake filesystem/network/lock/package/Docker boundaries.
- [ ] 9.3 Run the full constructor and compatibility suites, Python compile/static checks, shell checks, and `git diff --check` without Docker or network.
- [ ] 9.4 Collect real-Docker acceptance evidence when available for first materialization, repeated cache-hit launch, runtime override selection, read-only individual mounts, no container artifact download, corrupt-cache recovery, and resulting package metadata/ownership.
- [ ] 9.5 Inspect and redact acceptance evidence, run `openspec validate materialize-runtime-artifacts-on-host --strict`, and reconcile all active change artifacts before marking the change complete.
