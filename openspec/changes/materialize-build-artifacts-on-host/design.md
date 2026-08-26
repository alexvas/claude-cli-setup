## Context

Reviewed SHA-256 artifacts are currently passed as URL/digest build arguments and downloaded inside Dockerfile stages. Runtime npm extensions already demonstrate host-side streaming verification and atomic content-addressed publication, but use a shared XDG cache and SRI identities. Build orchestration currently invokes `docker build` without host artifact transactions. Pi is globally installed by exact root version without consuming the official release lockfile.

## Goals / Non-Goals

**Goals:**
- Establish a private checkout-local host trust boundary for selected `linux-amd64` build artifacts.
- Pass a minimal immutable input snapshot through a required BuildKit named context.
- Commit one current build live set only after successful image construction.
- Reuse verified failed-build downloads for 30 days and serialize builds per checkout.
- Install Pi reproducibly from its official release lockfile while preserving `/opt/pi` interfaces.

**Non-Goals:**
- `linux-arm64`, multi-platform or remote builders without local named-context support.
- Fully offline Docker builds or host materialization of APT, Rust channel, PyPI, Yarn, OpenSpec npm, or Pi dependency tarballs.
- Historical generations, image labels, offline rollback, or a constructor-owned npm cache format.

## Decisions

### Generalize verified blob identity and keep build storage checkout-local

Represent cache identity as algorithm plus digest bytes, with hex and SRI adapters. Reuse the runtime materializer's streaming, locking, no-follow inspection, atomic publication, and revalidation concepts without forcing build SHA-256 values through npm-specific DTOs. Resolve persistent build state under a fixed ignored checkout path and transaction snapshots under `.docker-generated`; do not honor shared `[cache].dir` for build blobs.

Alternative considered: shared XDG cache. Rejected because aggressive single-live-set cleanup would conflict across checkouts.

### Keep host paths private and cross the UID boundary through BuildKit import

Keep locks, manifests, markers, temporary downloads, verified blobs, and transaction snapshots under host-owner-controlled checkout paths. Populate blobs and snapshots in private mutable staging state, then publish verified blob files and finalized snapshot files as `0444` and remove every write bit from finalized snapshot directories. Immutability therefore applies to the host owner as well as group/other ordinary write attempts; later constructor mutation uses replacement/unlink under locked control state rather than in-place payload writes. The invoking host user's Docker client reads the snapshot and streams/imports it as a named BuildKit context; the in-container `dev` UID never traverses the host checkout. Dockerfile `COPY --from=constructor-artifacts` creates an in-build copy with explicit read permissions before a stage runs as `dev`. Thus a private `0700` checkout or ancestor owned by the invoking host user remains compatible, while unrelated users and container UID mappings receive no host-cache access.

Validate that the invoking host user can traverse the resolved checkout and snapshot path, but never chmod or chown the checkout, its ancestors, the home directory, shared cache roots, or unrelated paths. If host-owner traversal is unavailable, fail with the path and remediation left to the operator.

Alternative considered: making payload directories `0555` or ancestors traversable by other UIDs. Rejected because it cannot overcome an earlier `0700` ancestor safely and would unnecessarily broaden host access. Directly bind-mounting the cache was rejected because named-context import already provides the required isolation boundary.

### Materialize before Docker and expose a narrow snapshot

Under the checkout-wide build lock, resolve the effective projection, materialize cache misses, then create a unique owner-private staging snapshot with stable logical names (`rustup-init`, `uv.tar.gz`, `rtk.deb`, `fd.deb`) and a canonical manifest. Prefer hard links to immutable blobs with copy fallback and revalidate the completed payload. Finalize files to `0444` and remove all directory write bits before passing it as `--build-context constructor-artifacts=<snapshot>` so the host Docker client imports it before any build-stage user consumes files.

Dockerfile stages use `COPY --from=constructor-artifacts` and retain `sha256sum` verification. URL build args disappear for these artifacts, while digest args remain the common authority. Named-context capability is checked before downloads.

Dry-run has no transaction and therefore no snapshot. Model each named context as a closed typed state: `Materialized(path)` or `Prospective(name)`. Real builds must resolve `constructor-artifacts` to `Materialized` before executable argv rendering. Dry-run retains `Prospective("constructor-artifacts")`, serializes it as `{ "name": "constructor-artifacts", "state": "prospective", "path": null }`, and displays `--build-context constructor-artifacts=<prospective:not-materialized>` only beneath `Planned build (not executable)`. The display token is never passed to path handling or argv rendering.

Executable rendering accepts only fully materialized plans and fails before returning argv when any prospective context remains. Dry-run performs no lock, path creation, cache read/write, materialization, snapshot operation, Docker probe, or other side effect. This representation is independent of POSIX and Windows path syntax. Random transaction paths were rejected because they make output nondeterministic; OS-specific impossible paths were rejected because their impossibility is not portable; omitting context shape was rejected because the plan would hide a required build input.

Alternative considered: exposing the entire cache. Rejected because it broadens build access to unrelated and uncommitted blobs. Adding files to the primary context was rejected because it weakens context isolation and invalidation clarity.

### Use a single transaction lock and atomic commit

A nonblocking checkout-wide lock rejects a competing build with an actionable message. A successful Docker exit atomically replaces `committed-build.json`; only afterward does GC remove every digest unique to the old checkout-local build set. Failure preserves the old set and marks newly published verified build blobs uncommitted. Shared XDG runtime artifacts have no committed manifest in this design and are never inspected or mutated by build GC. Abandoned snapshot directories without the active lock are removed on the next build.

Alternative considered: multiple concurrent generations. Rejected by the explicit single-build and single-live-set product model.

### Apply fixed uncommitted retention

Create an atomic marker with `verified_at` for each newly published blob. Remove its marker when it becomes committed. Uncommitted blobs older than 2,592,000 seconds are removed during later build maintenance. Superseded committed blobs are removed immediately after commit; partial or corrupt files are removed immediately. The duration is built-in and has no configuration surface.

### Keep Pi as npm software but consume an explicit authoritative release contract

Extend the closed reviewed Pi source with `release_repository = "earendil-works/pi"` and `release_tag_prefix = "v"` alongside npm package `@earendil-works/pi-coding-agent`. For selected inventory version `<version>`, derive one immutable base URL as `https://github.com/<release_repository>/releases/download/<release_tag_prefix><version>/`. Fetch exactly `SHA256SUMS`, `pi-coding-agent-install-package.json`, and `pi-coding-agent-install-package-lock.json` beneath that base; do not discover aliases or infer names from npm metadata. Strictly parse SHA256SUMS and verify both installation assets before publishing them into the same selected build snapshot under their exact names.

The Pi stage copies those files to an installation workspace and runs `npm ci --ignore-scripts` with its existing independent BuildKit npm cache mount. It then creates the `/opt/pi` bin/module layout explicitly from package metadata so existing command and SDK paths remain stable. The GitHub HTTPS release and its SHA256SUMS are authoritative for the two install files; lockfile SRI is authoritative for npm dependency tarballs.

Do not materialize Pi's binary archive or implement npm cacache. npm networking remains in BuildKit.

### Unify host network policy

The streaming downloader receives the resolved credential-free proxy and validated corporate trust bundle through an injected host HTTP transport. Disabled settings add no overrides. Secrets and URLs follow existing redaction rules. Downloads complete before Docker starts, making materialization errors early operational failures.

## Risks / Trade-offs

- [Hard-link snapshots can encounter filesystem limitations] → Fall back to verified copies and recheck the snapshot digest.
- [A container UID cannot traverse a private checkout ancestor] → Do not require it to; import the named context through the invoking host owner, expose explicit in-build copies, test a checkout beneath a `0700` parent, and never repair ancestor permissions.
- [BuildKit named context is unavailable] → Probe capability before downloads and fail with minimum-prerequisite guidance.
- [Dry-run has no real named-context path] → Preserve a typed `Prospective` state with `path: null`, render only a clearly non-executable display token, require `Materialized(path)` at the argv boundary, and test identical POSIX/Windows output with zero side effects.
- [Pi `npm ci` layout differs from global npm layout] → Add focused contract tests for `/opt/pi/bin/pi`, package resolution, SDK imports, extension behavior, and runtime verification before replacing the old stage.
- [Host corporate TLS behavior differs from in-build clients] → Share resolved policy through an injectable downloader and add corporate-network acceptance coverage.
- [Crash occurs between commit and GC] → Commit first; later maintenance safely recomputes deletions from the sole checkout-local committed build manifest.
- [Pi npm and GitHub releases diverge] → Require reviewed repository/tag metadata and all three exact-version assets before Docker execution; never infer a GitHub release from npm alone.
- [Thirty-day abandoned downloads consume space] → Run bounded GC at build startup/commit and keep only digest-deduplicated verified blobs.

## Migration Plan

1. Add ignored checkout-local cache/generated paths, generalized digest identity, locking, materialization, markers, and manifests without changing Dockerfile consumption.
2. Add snapshot and named-context build rendering plus capability validation.
3. Convert rustup, uv, rtk, and fd stages individually to named-context inputs with double verification.
4. Convert Pi to verified official installation metadata and `npm ci`, validating the established `/opt/pi` interface.
5. Enable commit/GC only after all stages consume host materialization.
6. Rollback restores URL-based stages and build arguments; checkout-local blobs are inert and can be removed without affecting built images.
