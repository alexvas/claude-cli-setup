## Context

The Dockerfile currently uses `node:24-bookworm-slim` (Debian 12) as its base image. This was chosen when Bookworm was the latest Debian stable. The project's Dockerfile already moved to `trixie-slim` in the staged change; this design records the rationale and decisions behind that single-line `FROM` change.

The `node:24-trixie-slim` image provides the same Node.js 24 major version on Debian 13 (Trixie), which ships newer system libraries, updated compiler toolchains, and refreshed security patches. All existing stages (`base`, `toolchain`, `pi-tools`, `openspec-tools`, `runtime`) inherit from this single `FROM` without cascading modifications.

## Goals / Non-Goals

**Goals:**
- Modernize the OS base to Debian 13 while staying on Node.js 24.
- Preserve all existing tool installations, runtime contracts, and user-visible behaviour.
- Keep the change to a single `FROM` line.

**Non-Goals:**
- Change Node.js major version.
- Alter the multi-stage structure, cache boundaries, or stage dependencies.
- Add or remove any apt packages, tools, or configuration.

## Decisions

### Bump from `bookworm-slim` to `trixie-slim` rather than a different Debian tag

`node:24-trixie-slim` is the natural successor to `node:24-bookworm-slim` — same Node major, same slim variant, next Debian release. Other options considered:

- **`node:24-slim` (no codename)**: Floating tag that will eventually point to Trixie but introduces non-determinism in the interim. **Rejected** — the project prefers explicit Debian codenames for reproducibility.
- **`node:latest`**: Would also change the Node version. **Rejected** — the Node version is separately versioned and pinned.
- **`node:24-bookworm-slim` (no change)**: Would leave the project on an aging Debian release. **Rejected** — low risk, clear benefit to modernization.

### Single-line change, no cascading updates

The `FROM` change alone is sufficient. Because all subsequent stages derive from `base`, and the `base` stage installs OS packages explicitly (not relying on implicit Bookworm-specific packages), the migration needs no other Dockerfile edits.

Cache mounts (`/var/cache/apt`, `/var/lib/apt`) are naturally invalidated on first Trixie build, which is desirable: stale Bookworm caches should not persist.

## Risks / Trade-offs

- [Trixie packages have different versions than Bookworm] → The `base` stage installs packages by name, not version; any breakage surfaces immediately during `apt-get install` and fails the build.
- [Debian 13 is still testing (not stable at time of migration)] → Node.js 24-trixie images are maintained by the Node Docker team regardless of Debian release status. Rolling back is a single `FROM` line revert.
- [BuildKit cache invalidation on first Trixie build] → Expected; a clean `--no-cache` build or natural cache rotation handles it.
