# Implementation Contract

Every checkbox below is required for completion. A phase is complete only when every RED → GREEN → INTROSPECT → VALIDATE step in that phase passes and its deliverables exist. GREEN work SHALL be limited to making that phase's RED tests pass. Newly discovered scope SHALL be added to this contract before implementation.

Phase dependency DAG:

```text
Phase 1 ──> Phase 2 ──┬──> Phase 3 ──┐
                      ├──> Phase 4 ──┼──> Phase 6 ──> Phase 7
                      └──> Phase 5 ──┘
```

A phase MAY depend only on earlier phases named in its `Depends on` line. Phases 3, 4, and 5 are independent after Phase 2; Phase 6 begins only after all three complete.

## 1. Dedicated Cache-Root Resolution

**Depends on:** none

**Deliverables:** an acyclic `docker/versioning/cache_storage.py` module with a pure path-resolution layer for root validation and namespaced child derivation; filesystem inspection and mutation remain outside Phase 1. No cache-format, transport, artifact-verification, or filesystem-hardening behavior.

- [x] 1.1 **RED:** Add failing module-boundary tests proving `cache_storage.py` imports no CLI, launcher, transport, HTTP response-cache, or artifact-verification module.
- [x] 1.2 **RED:** Add failing pure-resolution tests producing an explicit XDG candidate only for a non-empty absolute `XDG_CACHE_HOME`, otherwise a `~/.cache` fallback candidate, without filesystem I/O.
- [x] 1.3 **RED:** Add failing resolver tests rejecting an empty, relative, or `~`-prefixed local `[cache].dir`, and rejecting an absolute local root equal to `XDG_CACHE_HOME`, `$HOME`, `/`, an ancestor of `XDG_CACHE_HOME`, and lexical equivalents of each.
- [x] 1.4 **RED:** Add resolver tests accepting an absolute dedicated child of `XDG_CACHE_HOME` and rejecting lexical equivalents of unsafe roots without reading or mutating the filesystem.
- [x] 1.5 **GREEN:** Create `cache_storage.py` and implement pure cache-root resolution, lexical unsafe-root validation, and named child derivation without filesystem inspection or mutation.
- [x] 1.6 **INTROSPECT:** Review the module dependency boundary, normalization, home/XDG derivation, and ancestor comparison for cycles, path-string shortcuts, implicit CWD dependence, or unsafe resolution.
- [x] 1.7 **VALIDATE:** Run focused module-boundary, root-resolution, and local-config tests; confirm path resolution performs no filesystem I/O and rejected roots perform no cache, network, or Docker effects.

## 2. Private Cache-Path Security

**Depends on:** Phase 1

**Deliverables:** `cache_storage.py` owns owner-only hardening for the resolved dedicated root and constructor-created descendants; parent directories remain untouched; actionable unsecurable-root diagnostics.

- [x] 2.1 **RED:** Add failing filesystem tests requiring `0700` on a new dedicated root and its constructor-created `versioning`, `runtime-artifacts`, blob, lock, and temporary directories, including creation of a missing explicit absolute `XDG_CACHE_HOME` with `0700`.
- [x] 2.2 **RED:** Add failing tests requiring `0600` HTTP entries, `0444` verified blobs, no mode change to an existing `XDG_CACHE_HOME`, and no permission changes to any other resolved-root parent.
- [x] 2.3 **RED:** Add failing filesystem tests accepting an existing writable XDG directory, rejecting an explicit absolute XDG non-directory or unwritable path without fallback, and using the `~/.cache` fallback only for empty or non-absolute XDG; require existing invoking-user-owned roots to be secured to `0700`, and symlinked selected roots, non-directory entries, foreign-owned directories, and unsecurable paths to be rejected through no-follow inspection before mutation.
- [x] 2.4 **GREEN:** Implement the filesystem-validation and hardening layer in `cache_storage.py` using no-follow and descriptor-relative operations where filesystem access occurs; do not chmod any parent directory.
- [x] 2.5 **GREEN:** Make HTTP cache writes consume `cache_storage.py` and fail with the same path-specific recovery behavior when their resolved root or entry cannot be secured.
- [x] 2.6 **INTROSPECT:** Review HTTP-cache ownership checks, descriptor lifetime, entry-mode enforcement, exception mapping, and parent boundaries; remove duplicated HTTP root and directory-security logic. Artifact-cache directory-security removal and handoff are deferred to Phase 5.
- [x] 2.7 **VALIDATE:** Run focused HTTP-cache, artifact-cache, permission, symlink, and containment tests; confirm failures happen before network, artifact publication, and Docker execution.

## 3. HTTP Cache Namespace and `--cache-dir` Removal

**Depends on:** Phase 2

**Deliverables:** update discovery reads and writes only the resolved `versioning/` child; the retired HTTP-only `check-updates --cache-dir` option is rejected as unsupported without fallback; no automatic interaction with the legacy `${XDG_CACHE_HOME:-~/.cache}/pi-cli/versioning` cache.

- [x] 3.1 **RED:** Add failing transport/cache tests requiring HTTP paths under `${XDG_CACHE_HOME}/docker-constructor/versioning` for valid XDG, under `~/.cache/docker-constructor/versioning` for empty/non-absolute XDG, and under an absolute local override's `versioning/` child.
- [x] 3.2 **RED:** Add failing CLI parser/help tests requiring `check-updates --cache-dir` to be rejected as unsupported without guidance or fallback.
- [x] 3.3 **RED:** Add failing migration tests proving the legacy `pi-cli/versioning` cache is neither read, copied, chmodded, mutated, nor deleted when the new root is used.
- [x] 3.4 **GREEN:** Remove `--cache-dir` from the parser, command request/argument propagation, help, and command-specific documentation; reject its use without selecting a cache path, fallback, or migrating cache data.
- [x] 3.5 **GREEN:** Remove the HTTP directory override from `readonly_service.py` and `build_transports()`; route HTTP cache construction through `cache_storage.py`'s resolved `versioning/` child without changing reviewed TTL, request, or token-isolation behavior.
- [x] 3.6 **INTROSPECT:** Review every HTTP cache construction path, including suggest/no-cache modes, so no legacy default, HTTP-only location override, or unnamespaced local directory remains reachable.
- [x] 3.7 **VALIDATE:** Run parser/help, update-discovery cache, local-config, JSON, suggest, no-cache, and reviewed-TTL regression suites; confirm a first request populates only the new HTTP cache.

## 4. Reviewed TTL CLI Contract

**Depends on:** Phase 2

**Deliverables:** reviewed `[cache].ttl` is the only HTTP TTL source; `check-updates --cache-ttl` is rejected as unsupported; `--no-cache` remains a one-invocation cache bypass.

- [x] 4.1 **RED:** Add parser/help tests proving `check-updates --cache-ttl` is no longer accepted or advertised and is rejected before network or cache mutation.
- [x] 4.2 **RED:** Add compatibility tests proving reviewed `[cache].ttl` remains effective with and without a local companion, absent reviewed TTL preserves current defaults, and `--no-cache` bypasses HTTP cache reads/writes without modifying TTL.
- [x] 4.3 **RED:** Add update-discovery compatibility tests for reviewed TTL and `--no-cache` under suggest mode, JSON output, and policy exit handling.
- [x] 4.4 **GREEN:** Remove `--cache-ttl` from the parser, command request, readonly service, and transport override parameters.
- [x] 4.5 **GREEN:** Make HTTP transport construction obtain TTL only from reviewed `[cache].ttl` while preserving `--no-cache` and suggest-mode behavior.
- [x] 4.6 **INTROSPECT:** Verify no command argument, DTO field, service parameter, documentation, or test still treats TTL as a CLI override.
- [x] 4.7 **VALIDATE:** Run parser/help, reviewed-TTL, no-cache, update-discovery, JSON, suggest, policy-exit, and cache regression suites.

## 5. Runtime-Artifact Cache Namespace Migration

**Depends on:** Phase 2

**Deliverables:** materialization, inspection, locks, dry-run planning, and artifact mount planning use only the resolved `runtime-artifacts/blobs` child; legacy checkout cache remains untouched.

- [x] 5.1 **RED:** Add failing launcher and artifact-cache tests requiring default and local-override runtime paths to resolve under `runtime-artifacts/blobs`.
- [x] 5.2 **RED:** Add failing dry-run and rendering tests requiring planned artifact mount sources to use the new root while retaining existing container targets.
- [x] 5.3 **RED:** Add failing migration tests proving `.docker-generated/runtime-artifacts` is neither read, copied, chmodded, mutated, nor deleted.
- [x] 5.4 **GREEN:** Route materialization, read-only inspection, locks, temporary state, dry-run planning, and mount planning through `cache_storage.py`'s resolved runtime-artifact cache child; remove artifact-cache root and directory-security logic superseded by cache-storage preparation.
- [x] 5.5 **GREEN:** Update cache-root containment and symlink checks for the resolved root without weakening atomic publication, verification, content identity, or individual read-only mounts; retain artifact-cache ownership of content addressing, locks, verification, and atomic publication.
- [x] 5.6 **INTROSPECT:** Trace every runtime-artifact path producer and consumer; remove checkout-local cache assumptions and duplicated artifact directory-security logic while preserving `.docker-generated/runtime/` projections and evidence output.
- [x] 5.7 **VALIDATE:** Run artifact materialization, launcher, dry-run, rendering, runtime projection, and container-mount regression suites; confirm Docker starts only after new-root blobs are verified.

## 6. Cross-Consumer Integration

**Depends on:** Phases 3, 4, and 5

**Deliverables:** one consistent resolved root across all persistent cache consumers; reviewed TTL is the sole TTL policy; legacy caches remain untouched; generated output remains checkout-local.

- [ ] 6.1 **RED:** Add failing end-to-end tests covering a default XDG root and a dedicated local root across both HTTP update discovery and runtime artifact materialization.
- [ ] 6.2 **RED:** Add failing integration tests proving both legacy caches remain unchanged while runtime projections and evidence remain under `.docker-generated/`.
- [ ] 6.3 **GREEN:** Resolve only integration defects exposed by tasks 6.1–6.2 without changing reviewed cache TTL, artifact identity, network policy, container mount targets, or local-companion ownership.
- [ ] 6.4 **INTROSPECT:** Trace each cache path and TTL source from configuration through `cache_storage.py`, consumer, security hardening, and cleanup; remove conflicting root constants, duplicated directory hardening, or TTL/cache-location documentation in code.
- [ ] 6.5 **VALIDATE:** Run focused cross-consumer, launch, update, projection, reviewed-TTL, and local-config suites; confirm no test requires a checkout-local persistent cache or CLI TTL override.

## 7. Documentation and Release Validation

**Depends on:** Phase 6

**Deliverables:** maintained documentation and scripts describe only the active cache layout, dedicated local roots, reviewed TTL policy, and permission recovery; README guidance contains no legacy cache paths; repository quality gates pass.

- [ ] 7.1 **RED:** Add failing documentation/source consistency tests for the new default root, local-root restrictions, reviewed `[cache].ttl`, parent-permission boundary, and the absence of legacy cache paths from maintained README files.
- [ ] 7.2 **GREEN:** Update README translations, local companion examples, maintenance guidance, evidence/acceptance scripts, and user-facing diagnostics with the active cache layout, reviewed TTL policy, and permission recovery; remove `--cache-dir` and `--cache-ttl` references while retaining `--no-cache`; do not add `${XDG_CACHE_HOME:-~/.cache}/pi-cli/versioning` or `.docker-generated/runtime-artifacts` as legacy-cache guidance.
- [ ] 7.3 **INTROSPECT:** Verify maintained documentation describes only the new constructor cache root, reviewed TTL policy, and checkout-local generated output; keep legacy HTTP/artifact-cache migration details in the change contract and tests rather than README guidance.
- [ ] 7.4 **VALIDATE:** Run strict OpenSpec validation, typecheck, lint, focused cache/launcher/update suites, complete tests, and package/build checks; confirm the final diff contains only contract-required files.
