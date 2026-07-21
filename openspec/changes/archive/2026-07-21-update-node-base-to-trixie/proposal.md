## Why

The Docker base image `node:24-bookworm-slim` is based on Debian 12 (Bookworm). Migrating to `node:24-trixie-slim` (Debian 13) provides newer system libraries, security updates, and package versions that match the project's Trixie-based toolchain. This change is already staged and in review — the proposal records the rationale for the migration.

## What Changes

- Update the single `FROM` line in the Dockerfile base stage from `node:24-bookworm-slim` to `node:24-trixie-slim`.
- All subsequent stages inherit the new base without further modification.

## Capabilities

### New Capabilities

- `node-base-image`: The Docker image SHALL use an explicit Debian-codenamed Node.js slim base image pinned to a specific Debian release.

### Modified Capabilities

None. The Debian version bump does not alter the runtime contract for `python3`, `pi`, tools, or shell behaviour — it is an infrastructure modernization within the same Node major version.

## Impact

- `Dockerfile`: single `FROM` line changed.
- Build environment: system packages (`apt`), C library, and toolchain components resolve from Debian 13 (Trixie) repositories instead of Debian 12 (Bookworm).
- No user-facing runtime contract, README, or smoke-check changes required.
