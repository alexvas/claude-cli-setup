## Why

Pinned build artifacts are currently downloaded from inside Dockerfile stages, so their verified bytes cannot be reused or lifecycle-managed by the constructor itself. Host-side materialization will establish a narrow, checkout-local, content-addressed input boundary for BuildKit while retaining only the artifacts useful to the latest successful build.

## What Changes

- Materialize the reviewed `linux-amd64` rustup, uv, rtk, and fd artifacts on the host before invoking Docker, verify their configured SHA-256 digests, and publish them atomically into a private checkout-local content-addressed cache.
- Create an owner-private per-build immutable snapshot containing selected verified artifacts plus derived assembled environments and evidence, remove all write bits from finalized files and directories while preserving assembler-validated executable bits on derived-environment files, and pass it through the invoking host user's Docker client as a required BuildKit named context; give the build-stage `dev` user read access only to files already imported into the BuildKit filesystem, never to host cache paths, and do not alter checkout or ancestor permissions.
- Copy named-context artifacts into isolated build stages and verify their SHA-256 digests again before installation; represent side-effect-free dry-run contexts as typed prospective values with `path: null`, render a deterministic explicitly non-executable display token, and require platform-native materialized paths before executable argv generation on Linux or Windows.
- Permit only one active image build transaction per checkout and fail clearly when Docker lacks BuildKit named-context support.
- Maintain one atomic checkout-local committed build live set after a successful image build, immediately delete every superseded committed build blob, and retain verified uncommitted blobs from failed or interrupted builds for a fixed 30-day TTL; runtime artifacts and their shared XDG cache are outside this retention model.
- Keep generated transaction snapshots ephemeral and recover abandoned snapshots on a later build.
- Extend the closed reviewed `[build.stages.base.node]` inventory with required exact `node_version` and `npm_version` fields as the sole caller-owned toolchain expectations shared by Pi and later npm consumers; never infer either value from an image tag.
- Depend on `add-locked-npm-environment-assembler` and use its standalone pinned container to assemble Pi from the reviewed GitHub release `pi-coding-agent-install-package.json`, `pi-coding-agent-install-package-lock.json`, and `SHA256SUMS` before Docker build.
- Call the assembler’s explicit side-effect-free input preflight with exact lock bytes, plural roots, platform, and reviewed Node/npm versions; require it to return a digest-bound validated input only after every reviewed-root engine check, then select `bin.pi` from metadata keyed to the exact `@earendil-works/pi-coding-agent` root identity/path. Pass that same validated input and exact bytes to Docker-backed assembly, which rechecks bindings, validates and publishes the host-visible Pi tree and assembler evidence, and creates no executable link. Never consume another root’s metadata or reparse raw package input; construct `/opt/pi/bin/pi` explicitly in the consumer while rejecting dangling or escaping resolved targets; record consumer evidence for its exact contents, mode, target, and containment; bind the assembled output identity, canonical tree digest, canonical assembler-evidence digest, and consumer launcher-evidence digest to a post-materialization transaction/build-plan attestation, not resolved build projection; include the environment and both evidence sets in the immutable build snapshot; and require BuildKit to match all four attested values and verify assembler and launcher evidence before copy and again in the final image, with no npm networking or installation.
- Preserve host corporate proxy and CA behavior for host-side artifact downloads.

## Capabilities

### New Capabilities

- `build-artifact-materialization`: Defines checkout-local host materialization, verified build-input snapshots, committed live-set retention, transaction locking, and uncommitted-artifact garbage collection.

### Modified Capabilities

- `docker-build-reproducibility`: Build projections supply locally verified artifacts and a host-assembled Pi environment through BuildKit named context; Pi uses its official release lock without in-build npm.
- `docker-build-caching`: Pinned prebuilt artifacts and Pi's assembled tree enter builds through a named context; npm downloads use the shared standalone assembler cache rather than BuildKit npm cache.
- `user-cache-storage`: Build artifacts use a private checkout-local cache rather than the shared XDG runtime/metadata cache, with distinct persistent and generated-transaction paths.
- `corporate-network-configuration`: Host-side artifact materialization honors enabled proxy and trust configuration before Docker execution.

## Impact

Affected areas include inventory/effective artifact identity, host streaming downloads and digest verification, cache path security, build orchestration and locking, BuildKit capability checks and command rendering, Dockerfile artifact stages, Pi installation layout under `/opt/pi`, corporate network transport, generated-path cleanup, and build/cache acceptance tests. Docker with BuildKit named-context support becomes a build prerequisite; only `linux-amd64` materialization is supported in this change.
