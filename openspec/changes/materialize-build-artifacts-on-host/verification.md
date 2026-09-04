# Phase 1 Validation Record

## Run

Date: 2026-09-03T16:02:31Z

Commands:

```text
npx pi-green-loop check --feedback
python -m unittest -v \
  tests.test_constructor_build_digest_identity \
  tests.test_constructor_project_state_phase1 \
  tests.test_constructor_build_cache_paths \
  tests.test_constructor_build_cache_permissions \
  tests.test_constructor_build_output_acceptance \
  tests.test_constructor_launcher \
  tests.test_constructor_host_access_launch_red \
  tests.test_constructor_host_access_verify_red \
  tests.test_constructor_cross_consumer_cache \
  tests.test_constructor_evidence_collector \
  tests.test_constructor_acceptance
```

## Results

- Configured typecheck and complete test discovery: passed (`pi-green-loop: all checks passing`).
- Focused Phase 1 validation: 445 tests passed, with one skipped ownership-transfer scenario.
- Two same-basename constructor projects remained isolated.
- Malformed and mismatched project metadata was denied without adoption.
- Runtime projection publication used only the selected constructor project's namespace; primary and extra workspaces received no namespace.
- Constructor project, workspace, home, cache-root parent, unrelated paths, and legacy `.docker-cache`/`.docker-generated` trees were not repaired, adopted, modified, or deleted.
- Simulated foreign-owned readable project coverage passed and external state remained invoking-user-owned and private.

## Host ownership-transfer validation

The required host scenario was subsequently run as invoking user UID/GID `1000:1000` with:

- constructor project `/home/aavasiljev/work/home/docker-constructor.git`;
- primary workspace `/home/aavasiljev/work/saa/astro`;
- extra workspace `/home/aavasiljev/work/saa/astro-issue-14957`;
- external namespace `/home/aavasiljev/.cache/docker-constructor/projects/docker-constructor.git-a65ee5d7729e0445`.

Evidence was collected before maintenance, after independent recursive ownership/permission maintenance and before launch, and after launch. The constructor project, primary workspace, and extra workspace were owned by `docker-dev:docker-dev` (`100999:100999`) with mode `0775`, while the invoking user retained read/traverse access. Comparing the pre-launch and post-launch evidence showed identical ownership and modes for all entries in the constructor project (2,872 entries), primary workspace (9,096 entries), extra workspace, and all recorded ancestors. No workspace namespace was created. The external namespace remained invoking-user-owned with mode `0700`; its complete recorded tree was byte-for-byte metadata-identical before and after launch. All four selected build blobs remained invoking-user-owned, mode `0444`, and SHA-256-valid.

The evidence files were:

```text
d451ff58c1277ad6b7b046a1a98696715552908785d937a297aeb4d9759ba078  01-before-maintenance.json
7642eeef312f7e18473e3e81164e3311226c7f90a7186bf66f6494e67893cb62  02-after-maintenance-before-launch.json
dfa7772bc7a5fc89b2791802d87d4dbff1d6132a3833368ed8276e79d70186a4  03-after-launch.json
```

A subsequent build also completed successfully using the retained external cache after snapshot cleanup and ownership maintenance. Together with the passing automated suites above, this completes task 1.12.

# Phase 2 Validation Record

## Run

Date: 2026-09-04T04:54:58Z

Command:

```text
python3 -m unittest -v \
  tests.test_constructor_build_transactions \
  tests.test_constructor_build_persistence \
  tests.test_constructor_build_cache_permissions
```

## Results

- 87 tests passed; one ownership-transfer scenario was skipped because the host lacked the required `docker-dev` account for the recursive `chown`/`chmod` scenario.
- Canonical project lock identity across symlink aliases and relative/absolute paths, independent same-basename namespaces, cross-project isolation, abandoned-snapshot recovery, atomic manifest publication, commit-before-delete ordering, fixed-TTL retention, and legacy checkout-state neutrality passed.
- Failed and interrupted transactions preserve the prior committed live set; uncommitted verified blobs retain their marker until maintenance or expiry.
- Retention boundary verified with fake clocks: an uncommitted blob survives at exactly 2,592,000 seconds since `verified_at` and is removed only when it is older than 2,592,000 seconds (maintenance at `verified_at + UNCOMMITTED_TTL_SECONDS + 1`).

# Phase 3 Validation Record

## Run

Date: 2026-09-04T05:24:33Z

Command:

```text
python3 -m unittest -v \
  tests.test_constructor_build_materialization \
  tests.test_constructor_build_orchestration \
  tests.test_constructor_corporate_network_build_red \
  tests.test_constructor_build_snapshot \
  tests.test_constructor_build_vector
```

## Results

- 200 tests passed; two ownership-transfer scenarios were skipped because the host lacks the required `docker-dev` account.
- Exact `linux-amd64` rustup, uv, rtk, and fd URL/digest selection and explicit rejection of unsupported platforms passed.
- Streaming materialization passed: external-namespace verified hit reuse with zero downloads, streamed cache miss, digest mismatch, transport interruption, atomic publication, immediate temporary-file cleanup, and zero project-directory mutation (no `.docker-cache`/`.docker-generated`, blob confined to the canonical external namespace).
- Orchestration end-to-end integrity failure passed: with a digest-mismatching transport driving the real streaming materialization path, the build returns OPERATIONAL, Docker and projection publication are never invoked, no invalid blob, materialization temporary file, or committed reference remains, and full-tree snapshots prove the entire cache outside the selected project's canonical namespace and the complete constructor project (including file contents and modes) are unchanged. A separate injected-materializer-failure test additionally proves the orchestration boundary returns OPERATIONAL with no Docker, no publication, and no committed reference.
- Corporate-network transport passed: enabled credential-free proxy, enabled replacement CA, disabled-policy neutrality, invalid-policy early failure, and secret/URL redaction.

## INTROSPECT (3.7)

Reviewed the Phase 3 diff for checkout-path leakage, full-buffer downloads, duplicate HTTP policy, unredacted diagnostics, network-after-integrity-failure, cross-project interaction, TOCTOU windows, and CLI/rendering coupling. Findings: no code changes required.

- Materialization and snapshot staging write only beneath the canonical external namespace; the checkout is only read/traversed.
- Downloads and digest verification stream in 1 MiB chunks; no response is ever fully buffered.
- `UrllibStreamingTransport` is the sole owner of host HTTP policy (proxy/CA applied once); Docker build-arg networking is a distinct boundary and not duplicated.
- Transport errors carry only the exception type name; integrity errors carry only the artifact name; CA-bundle and proxy failures are redacted.
- Digest mismatch raises before atomic publication with no retry; the temporary file is removed in the `finally` path.
- `build_materialization` imports only cache/identity/state/model modules — no CLI or rendering coupling.
- The benign `destination.exists()` corrupt-cache check races with a concurrent publisher, but per-project serialization (Phase 7 lock wiring) closes that window; Phase 3 has no concurrent materialization surface.

# Phase 4 Validation Record

## Run

Date: 2026-09-04T08:10:51Z

Command:

```text
./scripts/validate-phase4
```

The validator keeps the Python test process on the original invoking user for the whole suite. Credential-sensitive scenarios delegate only their narrow privileged operations (ownership transfer, recursive chown/chmod maintenance, differing-UID execution) to `sudo` via the shared test helpers, enabled by `PRIVILEGED_HELPERS=1`. The validator fails if `sudo` or an existing `docker-dev` account is unavailable, and treats any remaining skip as incomplete validation rather than success.

## Results

- Invoking-user suite: 268 tests passed with no skips; the four credential-sensitive scenarios exercised the invoking user throughout and delegated only the narrow privileged steps to `sudo` (two-build regression: both builds and cache blobs stayed invoking-user-owned with only the intermediate project/workspace maintenance delegated; foreign-owned-project: namespace creation and import ran as the invoking user with only the ownership transfer delegated; foreign-owner hard-link rejection: only the blob ownership transfer was delegated; differing-UID traversal: only the `test -r` probe was delegated to `sudo runuser`).
- No scenario re-runs the whole Python process as root, and none of these tests describe invoking-user ownership while executing as root.
- External snapshot tests passed: deterministic canonical manifest bytes, stable logical filenames (`rustup-init`, `uv.tar.gz`, `rtk.deb`, `fd.deb`, `manifest.json`), selected-prebuilt-artifact-only exposure, hard-link creation with cache-name unlink survival, copy fallback with post-copy digest verification, `0444` selected-prebuilt-artifact finalization with every directory write bit removed, and permission-aware cleanup that never chmods, chowns, truncates, or otherwise mutates payload inodes shared through hard links.
- Foreign-owned-project import and remapped in-build UID passed: owner-private external-namespace population, differing-UID traversal denial, and readable non-writable in-build copies (`--chown=dev:dev` with `--chmod=0444`/`0555`) verified; the project/workspace `docker-dev` ownership-maintenance regression runs both builds as the invoking user with only the intermediate maintenance delegated to `sudo`.
- Typed-plan tests passed: real builds hold `Materialized(platform-native-path, NoDerivedEnvironment)`; dry-runs hold `{name: constructor-artifacts, state: prospective, path: null, attestation: {state: prospective}}`; executable rendering rejects every unresolved prospective context before producing argv.
- Capability-failure and command-display tests passed: missing named-context support fails before download, snapshot publication, or Docker execution; dry-run text shows `--build-context constructor-artifacts=<prospective:not-materialized>` beneath `Planned build (not executable)` with byte-identical POSIX/Windows output, retained digest inputs, absent artifact URL inputs, and zero filesystem/cache/network/Docker side effects.
- Build-vector, no-project-mutation, and Dockerfile contract tests passed: named-context Dockerfile consumption for rustup, uv, rtk, and fd retains independent stages and in-stage SHA-256 verification with no corresponding curl or URL input; the Rustup reviewed SHA-256 `4acc9acc76d5079515b46346a485974457b5a79893cfb01112423c89aeb5aa10` is paired with the immutable official `archive/1.29.0/` artifact and checksum URLs rather than mutable `dist/` aliases.

## INTROSPECT (4.11)

Reviewed the Phase 4 diff for checkout path leakage, exposure of the whole external cache, mutable snapshots, unstable manifest ordering, primary-context leakage, permission or ownership changes propagated through hard links (including cleanup-time chmod/chown of snapshot payloads), OS-specific prospective paths, command/display divergence, retained artifact URLs, and unnecessary artifact network access. Findings: no code changes required.

- Snapshot staging lives beneath the canonical external namespace's generated tree; the checkout is only read/traversed and never written.
- The named context exposes only the finalized snapshot directory (four stable logical payloads plus `manifest.json`); the external cache root and unrelated/uncommitted blobs are never exposed.
- Finalization removes every file write bit (`0444`) and every directory write bit (`0555`); cleanup restores write/traversal permission only on snapshot directories and unlinks snapshot pathnames, never chmodding/chowning/truncating hard-linked payload inodes.
- Manifest bytes are canonical: entries sorted by logical name, `sort_keys=True`, and no URLs or cache paths are recorded.
- `constructor-artifacts` is a dedicated named context, distinct from the primary build context; no artifact enters the primary context.
- `Prospective` carries `path: null` and a display-only token that never enters path handling; executable argv requires `Materialized(platform-native-path)` with a closed attestation, and POSIX/Windows dry-run output is byte-identical.
- The Dockerfile retains no artifact URL arguments and no corresponding downloads; only digest arguments and in-stage `sha256sum` verification remain. Rustup provenance uses the immutable `archive/1.29.0/` URLs.
- Named-context capability is probed before materialization; dry-run performs no probe, lock, cache, filesystem, network, or Docker operation.

# Phase 5 Validation Record

## Run

Date: 2026-09-04T09:34:15Z

Commands:

```text
ty check --output-format concise
python3 -m unittest -v \
  tests.test_constructor_buildkit_cache \
  tests.test_dockerfile_contracts \
  tests.test_constructor_build_materialization \
  tests.test_constructor_build_orchestration \
  tests.test_constructor_phase4_named_context \
  tests.test_constructor_build_snapshot \
  tests.test_constructor_build_vector \
  tests.test_constructor_build_cache_permissions
python3 -m unittest discover -s tests -p 'test_constructor_build*.py'
./scripts/validate-phase5
```

## Results

- Type check: all checks passed.
- Focused Phase 5 suite (valid-snapshot build vector, tampered/mismatched-snapshot integrity rejection, named-context capability/integrity, immutable snapshot finalization, permission boundaries, Dockerfile contracts, and the new BuildKit cache-boundary module): **222 tests OK, 4 env-dependent skips** (credential-sensitive scenarios requiring a `docker-dev` account and working `sudo`; the test process stays on the invoking user and delegates only narrow privileged operations).
- Full build discovery (`test_constructor_build*.py`): **366 tests OK, 3 skips** — the 7 new `test_constructor_buildkit_cache` tests are included.

### BuildKit cache-boundary evidence (task 5.1)

`tests.test_constructor_buildkit_cache.py` parses the Dockerfile into a stage dependency graph (FROM base stages plus `COPY --from=<stage>` edges) and proves, without a Docker daemon:

- The named-context `COPY` sources are exactly the snapshot logical names (`rustup-init`, `uv.tar.gz`, `rtk.deb`, `fd.deb`).
- Each artifact's named-context `COPY` and its digest/version build args (`RTK_*`, `FD_*`, `RUSTUP_SHA256`/`RUST_VERSION`, `UV_SHA256`/`UV_VERSION`) are confined to a single consumer stage (`rtk-prebuilt`, `fd-prebuilt`, `toolchain`).
- Changing the rtk input (bytes or digest) invalidates only `rtk-prebuilt` and the dependent final assembly `runtime`; `fd-prebuilt`, `toolchain` (rustup/uv), `pi-tools` (Pi), and `openspec-tools` (OpenSpec) remain eligible for BuildKit cache reuse. The fd boundary is symmetric.
- `rtk-prebuilt` and `fd-prebuilt` depend only on `base`; `runtime` consumes all five independent tool stages.
- Sensitivity check: injecting `rtk.deb` into `fd-prebuilt` is detected, so the assertions are not vacuous.

### Valid and tampered snapshot evidence (task 5.4, no-Docker portion)

- Valid snapshot: `test_constructor_build_snapshot` (deterministic manifest, stable logical names, `0444`/`0555` finalization, hard-link/copy-fallback publication) and `test_constructor_build_vector` (materialized plan renders a complete `docker build` vector) pass.
- Tampered snapshot: `test_constructor_build_materialization` (digest mismatch rejection), `test_constructor_build_orchestration` (integrity failure through the real streaming materializer prevents Docker invocation, commits no reference, and confines mutation to the selected namespace), and `test_constructor_phase4_named_context` (in-build `sha256sum -c` integrity) pass. `test_dockerfile_contracts` confirms each converted stage retains in-stage SHA-256 verification with no artifact URL/curl input.

### Host BuildKit acceptance evidence

`./scripts/validate-phase5` passed on a host with a reachable Docker daemon and BuildKit named-context support:

- A valid immutable snapshot completed the `linux/amd64` runtime build. Each installed command executed successfully with `--version`, and its parsed version matched the effective inventory: rtk `0.45.0`, fd `10.4.2`, rustc `1.98.0`, uv `0.12.5`, Pi `0.84.2`, and OpenSpec `1.10.0`.
- A snapshot whose rtk bytes were changed without changing `RTK_SHA256` was rejected by the in-stage SHA-256 check.
- With a unique rtk-only payload and matching updated digest, independent plain-progress target builds reported `CACHED` for fd, toolchain/rustup/uv, Pi, and OpenSpec; the changed rtk stage executed and rejected the deliberately invalid Debian package rather than reusing its prior result.
- The fd-only case passed symmetrically: rtk, toolchain/rustup/uv, Pi, and OpenSpec remained cached, while the changed fd stage executed and rejected the deliberately invalid Debian package.
- Every Docker command emitted live timestamped output and completed within the configured per-command timeout.

## INTROSPECT (5.3)

Reviewed the converted Dockerfile stages for duplicated verification, accidental payload persistence in the final image, cross-stage invalidation, and unnecessary coupling introduced by the minimal Phase 4 conversion. Findings: no code changes required.

- Each of rustup, uv, rtk, and fd is SHA-256 verified exactly once in the Dockerfile (four `sha256sum` verifications, one per artifact). The host-side materialization digest check plus this in-build check is the required defense-in-depth ("verify their SHA-256 digests again before installation"), not duplication within the Dockerfile.
- No payload persists into the final image: `rtk-prebuilt` removes `/tmp/rtk.deb` and `/tmp/rtk-extract`, `fd-prebuilt` removes `/tmp/fd.deb` and `/tmp/fd-extract`, `toolchain` removes `/tmp/rustup-init` and `/tmp/uv.tar.gz`/`/tmp/uv-*`; the `runtime` stage copies only the installed binaries (`/usr/local/bin/rtk`, `/usr/local/bin/fd`) and toolchain home directories.
- No cross-stage invalidation was introduced by the conversion: the four named-context `COPY` instructions and their digest/version args stay inside their own stages, so a changed artifact invalidates only its own stage and `runtime`.
- No unnecessary coupling was introduced: Phase 4 only replaced per-stage URL downloads with scoped named-context `COPY` operations and added no new `FROM`/`COPY --from=<stage>` edges. The pre-existing `base -> toolchain -> pi-tools` boundary is documented intent and predates the conversion; changing rustup/uv invalidates `pi-tools` by design and is outside the task 5.1 rtk/fd boundary.
- No artifact URL arguments or curl invocations remain for the four artifacts; build args are `ARG` (never `ENV`), so no artifact identity is persisted as image metadata.
