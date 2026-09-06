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

## Phase 6 — Official Locked Pi Installation (6.1–6.11)

Date: 2026-09-04T10:00:00Z

Commands:

```text
ty check --output-format concise
python3 -m unittest -v \
  tests.test_constructor_pi_inventory \
  tests.test_constructor_pi_release \
  tests.test_constructor_pi_consumer \
  tests.test_constructor_pi_snapshot \
  tests.test_constructor_pi_assembly \
  tests.test_constructor_inventory_root \
  tests.test_constructor_inventory_build \
  tests.test_constructor_inventory_runtime \
  tests.test_constructor_build_projection \
  tests.test_constructor_build_vector \
  tests.test_constructor_verification \
  tests.test_dockerfile_contracts \
  tests.test_constructor_corporate_network_build_red
python3 -m unittest discover -s tests
```

### Reviewed values bootstrapped once (task 6.1)

- `[build.stages.base.node].node_version = "24.18.0"` and `.npm_version = "11.16.0"` — the exact versions the standalone assembler already asserts against the digest-pinned image (`docker.npm_environment.smoke.SMOKE_NODE_VERSION` / `SMOKE_NPM_VERSION`), never inferred from the `24.18.0-trixie-slim` tag. The reviewed digest `sha256:ae91dcc111a68c9d2d81ff2a17bda61be126426176fde6fe7d08ab13b7f50573` is unchanged and matches inventory.
- `[build.stages.pi-tools.pi]` reviewed version updated `0.84.2` → `0.84.4`, matching the checked-in `tests/data/pi_install_lock_0.84.4.json` fixture whose lock SHA-256 (`a9f805a677f0860328059390b0f62adcc655299952f293127a8db8939818dff4`) is exactly the `pi-coding-agent-install-package-lock.json` entry of the `v0.84.4` GitHub release `SHA256SUMS`. The source is now `type = "pi-release"` with `package = "@earendil-works/pi-coding-agent"`, `release_repository = "earendil-works/pi"`, `release_tag_prefix = "v"`.

### Results

- Type check: all checks passed.
- New Phase 6 suites: inventory (13), release URL/SHA256SUMS (16), consumer launcher/containment (26), snapshot admission (22), assembly orchestration (15) — all OK.
- Full discovery (`python3 -m unittest discover -s tests`): **3213 tests OK, 5 skips** (env-dependent credential-sensitive scenarios). The same run under a blackhole proxy (`http_proxy`/`https_proxy` pointing at an unreachable address) is also **3213 OK, 5 skips**, proving the acceptance suites never reach the live Pi release endpoint.

### Hermetic Pi fixtures and no-network transport (acceptance hardening)

The acceptance suites (`test_constructor_acceptance`, `test_constructor_build_output`, `test_constructor_build_output_acceptance`) previously injected a duck-typed `fake_pi_materialization` but still constructed the production `UrllibStreamingTransport`. A shared `tests/pi_fixtures.py` now centralises the deterministic assets and pins every acceptance build to a no-network transport:

- `pi_install_package_bytes()`, `pi_install_lock_bytes()` (the reviewed `tests/data/pi_install_lock_0.84.4.json`), and `pi_sha256sums_bytes()` produce the exact `SHA256SUMS`/install-asset bytes locally; `FakePiReleaseTransport` serves exactly those three URLs and raises `AssertionError` on any other URL, recording download order.
- `NoNetworkTransport.stream()` raises `AssertionError("unexpected outbound network request: <url>")`; `no_network_transport_factory()` is wired via `_transport_factory` on every in-process acceptance build request, and `test_constructor_build_output_acceptance` pins the subprocess default `UrllibStreamingTransport` to the same tripwire. This makes any future change that drops the injected materializer fail immediately instead of reaching GitHub.
- `fake_pi_materialization` is now defined in `tests/pi_fixtures.py` and re-exported by `tests/build_test_support.py`; `test_constructor_pi_assembly` reuses the shared fixtures instead of duplicating transport/SHA256SUMS construction.
- Two explicit regression tests assert the no-network transport rejects any outbound request (`test_constructor_acceptance.TestBuildFailureDiagnostics.test_no_network_transport_rejects_any_outbound_request`, `test_constructor_pi_assembly.TestMaterializePiOrchestration.test_no_network_transport_rejects_any_request`).

### Image-side verification hardening (`docker/verify-pi.mjs`)

The in-image verifier was upgraded from a field-presence/string-equality check to a full recompute-and-compare pipeline.  It now, in order: (1) strictly validates the assembler-evidence envelope and body (exact top-level and body key sets, hex64 digest fields, envelope/body `input_identity` agreement), canonically re-serializes the body, requires its SHA-256 to equal both `evidence_digest` and `PI_ASSEMBLER_EVIDENCE_DIGEST`, and recomputes the assembled output identity from `input_identity.digest` + `tree_digest` + the recomputed evidence digest, requiring it to equal both `output_identity` and `PI_ASSEMBLED_OUTPUT_IDENTITY`; (2) rebuilds the canonical tree manifest for the copied tree (files, directories, symlinks, content hashes, and executable modes) with no-follow containment checks that reject dangling, escaping, and unexpected symlinks, and requires the canonical content digest to equal both the evidence `tree_digest` and `PI_TREE_DIGEST` — the consumer launcher (`bin/pi`) and its parent directory are excluded so the digest covers exactly the assembler's published tree; (3) matches every copied-tree entry by relative path against the retained `body.tree_entries` list — rejecting missing or extra entries, and any mismatched kind, file digest, or symlink target — and enforces the read-only permission contract on every regular file and directory (no write bits via `mode & 0o222`, and executable bits equal to the evidence via `mode & 0o111`, while deliberately not comparing UID/GID because Docker `COPY` re-owns the tree); (4) only then re-verifies the launcher evidence digest, exact contents, non-writable executable mode, and resolved-target containment; and (5) runs `pi --version`.  Filesystem locations are overridable via `PI_ROOT`, `PI_ASSEMBLER_EVIDENCE_PATH`, and `PI_LAUNCHER_EVIDENCE_PATH` (production defaults unchanged), so `tests/test_constructor_pi_verify.py` drives the real script with `node` against temp trees.  That suite (11 tests) proves the Dockerfile verification fails for a changed file under `/opt/pi`, a substituted tree with the original evidence, a modified evidence body with unchanged top-level digest fields, a modified `output_identity`, escaping/dangling symlinks in the imported tree, a Pi CLI target with its execute permission removed (contents unchanged), a file gaining execute permission where the evidence says it is absent, and a write bit added to a regular file or to a directory — and that a faithful tree passes.  No Pi acquisition, rendering, inventory, or runtime interfaces were changed.

### Pi materialization error boundary (`build_orchestration.py`)

The host Pi pipeline (release acquisition → preflight → Docker-backed assembly → consumer launcher) raises several implementation-specific exception types: `PiAssemblyError` (acquisition/checksum), `PiConsumerError` (launcher selection/containment/evidence), and the assembler's `LockedNpmError` (preflight/executor/npm-exit/publication), plus any raw `OSError`/`ValueError` that can still leave `materialize_pi()`.  `_materialize_pi_for_build()` now normalizes all of them to the existing materialization-boundary `SnapshotError` (message `Pi materialization failed: …`) for both the injected and the production `materialize_pi` paths, so `execute_build()` keeps a single `except (MaterializationError, BuildCacheError, SnapshotError, OSError, ValueError)` boundary.  On any such failure the build returns `ExitKind.OPERATIONAL`, calls `cleanup_artifact_snapshot(snapshot)` (the snapshot is never created, so this is a `None` no-op), preserves the already-rendered prospective display, and never publishes the effective projection or invokes Docker.  `tests/test_constructor_build_orchestration.TestPiMaterializationBoundary` (4 tests) covers release-asset acquisition/checksum failure (real `materialize_pi` with a bad-bytes transport, no Docker daemon needed), malformed-lockfile preflight failure, assembler execution failure, and consumer launcher-target failure — each asserting OPERATIONAL (no uncaught exception), no Docker run, no projection publication, no snapshot, and no committed build reference.  `TestPiSnapshotAdmissionFailure` (1 test) additionally proves a `SnapshotError` raised by snapshot admission itself returns OPERATIONAL with cleanup invoked (snapshot never assigned), no Docker run, no projection publication, and no committed build reference.

### Validation before snapshot admission (`build_snapshot.py`)

The derived-environment admission no longer trusts the raw tree/evidence bundle.  `DerivedEnvironmentSource` now carries the complete four-value attestation (`assembler_evidence_digest`, `launcher_evidence_digest`, `assembled_output_identity`, `canonical_tree_digest`) alongside the raw tree, launcher, and evidence bytes, and `build_orchestration.py` derives the attestation before snapshot creation so the same values drive both admission and rendering.  `admit_derived_environment` now, in order: (1) re-verifies the assembler-evidence byte digest, strictly re-parses the evidence envelope, and requires the evidence's `output_identity` and `tree_digest` to equal the attestation; (2) re-maps the source tree with `build_tree_manifest` and requires it to equal the evidence `tree_entries` field-for-field; (3) re-verifies the launcher-evidence byte digest and fully re-validates the launcher via the shared `validate_launcher_evidence` (see the next section); (4) only then copies the tree (executable bits preserved, write bits stripped) and writes the launcher and evidence; and (5) recomputes the copied staging tree with the launcher (`bin/pi`) and its emptied parent excluded and re-validates its content digest and per-entry content signature against the evidence, closing the validation-to-copy race.  Any mismatch raises `SnapshotError`, removes staging, and fails before Docker execution or snapshot publication.  `tests/test_constructor_pi_snapshot.py` (22 tests) covers: source tree changed after materialization; a copied tree diverging from the validated source (via a diverging-copy patch); each of the four attestation values being wrong; substituted assembler evidence; substituted launcher contents; substituted launcher evidence; an escaping launcher target; and the full launcher-evidence rejection matrix — a missing field, a wrong `launcher_path`, a non-string/malformed `contents_sha256`, an incorrect `mode`, an absolute target, an escaping target, an unknown extra field, and arbitrary launcher bytes rejected via the canonical-script recompute (all with recomputed evidence digests so the failure comes from the schema/value check, not the byte-digest check) — plus a non-canonical-but-valid launcher evidence admitted case (exact canonical bytes are not part of the contract) and a proof that launcher-evidence failures raise before the derived tree is copied or any snapshot is published; the retained happy-path/symlink/installation-file-absence tests remain.

### Isolated derived-environment layout (`build_snapshot.py`, `Dockerfile`)

The complete Pi derived environment is now confined to one stable, immutable directory instead of a split `opt/pi` + two root-level evidence files.  All Pi-derived paths live under `derived-environments/pi/` — the assembled tree at `derived-environments/pi/opt/pi`, the consumer launcher at `derived-environments/pi/opt/pi/bin/pi`, and the two evidence sets at `derived-environments/pi/pi-assembler-evidence.json` and `derived-environments/pi/pi-launcher-evidence.json`.  `admit_derived_environment` finalizes the launcher directory, the tree root, its parent, and the isolation directory itself (directories `0o555`, files write-bit-free), so the whole isolation directory and every descendant are immutable; `_readonly_tree` skips exactly that directory and finalizes its `derived-environments` parent.  The manifest now carries `isolation_dir` plus relative `path` values (tree, launcher, and both evidence entries) that explicitly identify the isolation directory.  The installation package and lock assets remain absent from the snapshot.  The `Dockerfile` copies the three isolated paths (`derived-environments/pi/opt/pi`, `derived-environments/pi/pi-assembler-evidence.json`, `derived-environments/pi/pi-launcher-evidence.json`) to the same image destinations as before, preserving the existing verify-then-remove ordering.  Tests: `test_constructor_pi_snapshot.TestPiSnapshotAdmission.test_isolated_layout_and_prebuilt_artifacts_outside` proves no Pi evidence or `opt` at the snapshot root, the tree and both evidence files exist only under the isolation directory, the entire isolation directory is immutable, and the four prebuilt artifacts remain outside it under their stable logical names; `test_dockerfile_contracts.TestDockerfileBuildContract.test_pi_named_context_copies_use_isolated_paths` pins the three new `COPY` sources; and `test_constructor_buildkit_cache` now expects the three isolated named-context sources.

### Strict launcher-evidence schema (`pi_consumer.py`)

The launcher evidence is now validated through one authoritative shared schema instead of an inline snapshot-side field check.  `parse_launcher_evidence(data)` requires exactly the five fields (`launcher_path`, `contents_sha256`, `mode`, `target`, `containment`), rejecting both missing and unknown keys, and validates each value: `launcher_path == "/opt/pi/bin/pi"`; `contents_sha256` is a lowercase 64-character SHA-256 value; `mode` is an integer equal to the non-writable executable `0o555`; `target` is a non-empty relative POSIX path with no absolute or escaping (`..`) form; and `containment is True`.  `validate_launcher_evidence(data, launcher_contents=…, environment_root=…)` then re-binds the evidence to the actual launcher: the recorded contents digest must equal the SHA-256 of the supplied launcher contents, the canonical launcher script is recomputed from the evidenced target (`_launcher_script`, now shared with `plan_launcher`) and must match the supplied contents byte-for-byte (so arbitrary bytes are never accepted merely because their digest is recorded), and the target is resolved against the assembled environment as a contained regular file.  `build_snapshot.py` now delegates its launcher re-validation to `validate_launcher_evidence` and only additionally requires the evidenced mode to equal the derived `launcher_mode` used for writing.  `resolve_contained_target` normalizes `environment_root` once (`environment_path = Path(environment_root)`; `root = Path(os.path.realpath(os.fspath(environment_path)))`) and joins the candidate through `environment_path` rather than applying `/` directly to the possibly-`str` argument, so both `str` and `Path` environment roots resolve identically while the real-path containment and regular-file checks are unchanged.  `tests/test_constructor_pi_consumer.py` (26 tests) adds: round-trip parse, missing/unknown field, wrong `launcher_path`, uppercase SHA-256, wrong mode, absolute/escaping target, non-`True` containment, the contents-digest-mismatch plus arbitrary-bytes-with-matching-digest cases, and `str(environment_root)` round-trips through both `resolve_contained_target` and `validate_launcher_evidence`.

### Install-package binding (no download-and-discard)

The install-package manifest is now a real assembler input instead of being downloaded and discarded.  `preflight` accepts the exact `pi-coding-agent-install-package.json` bytes (optional, so the standalone lockfile-only assembler is unchanged), strictly parses them, requires the package `name`/`version` to match the lockfile manifest root, and requires the package `dependencies` to agree with the lockfile root entry.  An absent `dependencies` field is normalized to `{}`, but a present field is validated strictly as a string-to-string object, so a falsey value (`null`, `[]`, `""`, `false`, `0`) is rejected as `invalid_package_dependencies` rather than silently treated as absent.  The exact bytes and their SHA-256 are carried on `ValidatedAssemblyInput` (`package_bytes`/`package_digest`), and the digest is folded into `AssemblerInputIdentity` via `input_identity_digest` (a `null` digest for the standalone path), so a package substitution changes the input identity and the assembled output identity.  `compute_assembler_input_identity` rechecks `package_digest` against `package_bytes` and re-runs preflight with the package bytes, so `assemble_environment`/`assemble`/`render_run_vector` re-verify the binding before any effect.  `materialize_pi` now passes both exact assets to preflight; neither file is ever added to the BuildKit snapshot.  `tests/test_constructor_pi_assembly.TestInstallPackageBinding` (7 tests) covers malformed package JSON, wrong package name, wrong package version, package/lock root dependency disagreement, package bytes changed after preflight, a verified package substitution changing the identity, and a substitution that invalidates the binding; `TestInstallPackageDependencies` (5 tests) covers an absent `dependencies` field being treated as `{}`, an explicit empty object being accepted against a dependency-free lockfile root, each present-falsey value (`null`, `[]`, `""`, `false`, `0`) being rejected as `invalid_package_dependencies`, a non-empty map disagreeing with an empty lockfile root, and a non-empty map being accepted only when it exactly matches the lockfile root; `test_installation_files_are_absent_from_snapshot` retains the absence assertion for both exact assets.

### INTROSPECT (6.10)

Reviewed for implicit asset inference, binary archives, mutable resolution, lifecycle scripts, lock bypass, BuildKit npm/network, consumer duplication of assembler logic, cache authority, and changed Pi paths. Findings: no issues remained after the implementation, which removes each by construction.

- **No implicit asset inference**: `derive_pi_release_urls` composes exactly `https://github.com/<release_repository>/releases/download/<release_tag_prefix><version>/` with the three exact names `SHA256SUMS`, `pi-coding-agent-install-package.json`, `pi-coding-agent-install-package-lock.json`; no npm metadata or alias discovery is consulted.
- **No binary archives**: `acquire_install_assets` fetches only the two installation files and `SHA256SUMS`; `pi-linux-x64.tar.gz` and sibling archives are never requested or admitted (asserted in `test_constructor_pi_snapshot`).
- **No mutable resolution**: the assembler image reference is the digest-pinned `docker.io/library/node:24.18.0-trixie-slim@sha256:…` (validated by `validate_image_reference`), and release URLs are version-pinned.
- **No lifecycle scripts**: the assembler fixed policy is `--ignore-scripts --no-bin-links --no-audit --no-fund`.
- **No lock bypass**: preflight validates the complete lock closure; assembly re-runs preflight via `compute_assembler_input_identity` and rechecks bindings before effects.
- **No BuildKit npm/network**: the `pi-tools` stage now copies `/opt/pi` from `constructor-artifacts` and runs `docker/verify-pi.mjs`; the `npm install --global` stage is gone (confirmed by `test_constructor_corporate_network_build_red` networked-stage enumeration and `test_dockerfile_contracts`).
- **No consumer duplication of assembler logic**: `select_pi_metadata` reads only the keyed `ReviewedRootMetadata` for `@earendil-works/pi-coding-agent`; the consumer never reparses raw package input or re-runs npm.
- **Cache authority intact**: the assembler's shared opaque cache is keyed by assembler identity + input identity; the consumer never inspects npm cache internals.
- **Changed Pi paths preserved**: `/opt/pi/bin/pi` remains a working launcher (a real file, non-writable executable `0o555`, symlink-robust), and `/opt/pi` remains on PATH.

### VALIDATE (6.11)

- Inventory: closed-schema rejection of missing/malformed/unknown `node_version`/`npm_version` and Pi release metadata; exact reviewed values and digest; node version never inferred from the tag (`test_constructor_pi_inventory`, `test_constructor_verification`).
- Exact URLs and release content: `test_constructor_pi_release` covers the exact base/asset URL derivation, strict SHA256SUMS parsing (blank/malformed/duplicate/escaping/empty lines), both required entries, redirects (transport-transparent), missing assets, digest mismatches, and transport failures.
- Assembler preflight + selection + snapshot admission: `test_constructor_pi_consumer` and `test_constructor_pi_snapshot` cover keyed `bin.pi` selection, launcher contents/mode/target/containment, contained-symlink import, escaping/dangling rejection, exec-bit preservation, and installation-file absence from the snapshot.
- Orchestration: `test_constructor_pi_assembly` proves side-effect-free preflight (asset downloads) precedes Docker-backed assembly, that assembly receives the exact validated input (lock digest, roots, platform, tool versions) and assembler identity, and that `--no-bin-links`/`--ignore-scripts` are fixed policy.
- Materialized-attestation binding: `execute_build` now materializes Pi, builds a `DerivedEnvironment(assembledOutputIdentity, canonicalTreeDigest, assemblerEvidenceDigest, consumerLauncherEvidenceDigest)` attestation, and passes it through `Materialized(path, DerivedEnvironment(…))`; the four values are emitted as `PI_*` build args only for materialized derived-environment contexts. Dry-run remains `Prospective` (`path: null`) and Phase 4 `NoDerivedEnvironment` remains a closed variant.
- No-build-network / Dockerfile: `pi-tools` consumes only the named context; the in-image `docker/verify-pi.mjs` re-verifies launcher contents/mode/target/containment and cross-checks the evidence sets against the four attestation values before `pi --version` (CI-only; no Docker daemon on this host).
- Identical external Pi interfaces: `pi --version` version check and `/opt/pi/bin/pi` layout are preserved; the runtime stage still copies `/opt/pi` and links `/usr/local/bin/pi`.

# Phase 7 Validation Record

## Host run

Date: 2026-09-06T23:18:33Z–2026-09-06T23:19:45Z

Command:

```text
scripts/validate-materialize-build-artifacts-on-host-phase7-host
```

## Results

- The complete focused inventory, digest, project-identity, cache-security, transaction, materialization, corporate-network, snapshot, build-vector, Dockerfile, Pi, runtime, host-access, and acceptance inventory passed.
- The privileged Phase 4 inventory passed as the invoking user with narrowly delegated ownership operations and no skipped credential-sensitive scenarios.
- A real `linux-amd64` image build succeeded from a readable constructor-project copy recursively owned by `docker-dev`.
- A real launch succeeded with one primary and one extra workspace. Captured `docker run` argv proves the runtime projection was mounted from the constructor project's external runtime namespace and both workspaces were mounted.
- Constructor-project, primary-workspace, and extra-workspace before/after manifests are byte-identical. No workspace namespace appeared, and no `.docker-cache` or `.docker-generated` entry was created.
- External metadata/path diagnostics passed: malformed and identity-mismatched `project.json` state was rejected without adoption or mutation, and diagnostics retained the selected constructor-project and external namespace/path boundary rather than reporting a legacy checkout-local state location.
- Unsupported-platform rejection passed: build projection and orchestration coverage explicitly rejected targets other than the reviewed `linux-amd64` platform before artifact materialization or Docker execution.
- The report records `passed: true`; evidence is under `validation-evidence/materialize-build-artifacts-on-host-phase7-20260906T231833Z/`.
