## Why

Pinned build artifacts are currently downloaded from inside Dockerfile stages, so their verified bytes cannot be reused or lifecycle-managed by the constructor itself. Host-side materialization will establish a narrow, checkout-local, content-addressed input boundary for BuildKit while retaining only the artifacts useful to the latest successful build.

## What Changes

- Materialize the reviewed `linux-amd64` rustup, uv, rtk, and fd artifacts on the host before invoking Docker, verify their configured SHA-256 digests, and publish them atomically into a private checkout-local content-addressed cache.
- Create an owner-private per-build immutable snapshot containing only selected verified artifacts, remove all write bits from finalized files and directories, and pass it through the invoking host user's Docker client as a required BuildKit named context; give the build-stage `dev` user read access only to files already imported into the BuildKit filesystem, never to host cache paths, and do not alter checkout or ancestor permissions.
- Copy named-context artifacts into isolated build stages and verify their SHA-256 digests again before installation; represent side-effect-free dry-run contexts as typed prospective values with `path: null`, render a deterministic explicitly non-executable display token, and require platform-native materialized paths before executable argv generation on Linux or Windows.
- Permit only one active image build transaction per checkout and fail clearly when Docker lacks BuildKit named-context support.
- Maintain one atomic checkout-local committed build live set after a successful image build, immediately delete every superseded committed build blob, and retain verified uncommitted blobs from failed or interrupted builds for a fixed 30-day TTL; runtime artifacts and their shared XDG cache are outside this retention model.
- Keep generated transaction snapshots ephemeral and recover abandoned snapshots on a later build.
- Continue installing Pi from npm, but add the reviewed GitHub release repository and tag prefix to Pi source metadata, derive exact release asset URLs for `pi-coding-agent-install-package.json`, `pi-coding-agent-install-package-lock.json`, and `SHA256SUMS`, verify the two installation files against that manifest, and run `npm ci --ignore-scripts` with a BuildKit npm cache mount.
- Continue using npm networking inside BuildKit for Pi's locked dependency graph; a fully host-materialized npm registry/cache and offline npm installation are out of scope.
- Preserve host corporate proxy and CA behavior for host-side artifact downloads.

## Capabilities

### New Capabilities

- `build-artifact-materialization`: Defines checkout-local host materialization, verified build-input snapshots, committed live-set retention, transaction locking, and uncommitted-artifact garbage collection.

### Modified Capabilities

- `docker-build-reproducibility`: Build projections supply locally verified artifact inputs through BuildKit, and Pi installation uses the official release lockfile with `npm ci`.
- `docker-build-caching`: Pinned prebuilt artifacts enter builds through a named context while independent stages and the BuildKit npm dependency cache retain their existing invalidation guarantees.
- `user-cache-storage`: Build artifacts use a private checkout-local cache rather than the shared XDG runtime/metadata cache, with distinct persistent and generated-transaction paths.
- `corporate-network-configuration`: Host-side artifact materialization honors enabled proxy and trust configuration before Docker execution.

## Impact

Affected areas include inventory/effective artifact identity, host streaming downloads and digest verification, cache path security, build orchestration and locking, BuildKit capability checks and command rendering, Dockerfile artifact stages, Pi installation layout under `/opt/pi`, corporate network transport, generated-path cleanup, and build/cache acceptance tests. Docker with BuildKit named-context support becomes a build prerequisite; only `linux-amd64` materialization is supported in this change.
