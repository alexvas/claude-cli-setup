## Why

Container startup is slowed down by unconditional recursive ownership repair in `docker/entrypoint.sh`, especially for large cache directories such as `/home/dev/.npm`. We need to keep startup safe while avoiding repeated full-tree traversal and ownership changes for paths that are already correct.

## What Changes

- Optimize startup ownership repair to update only files and directories that are not already owned by `dev:dev`.
- Preserve recursive handling for configured project mounts and runtime cache directories.
- Ensure the ownership scan does not follow symbolic links while traversing directories.
- Update runtime requirements to define selective ownership repair behavior and symlink handling.

## Capabilities

### New Capabilities
- None.

### Modified Capabilities
- `docker-runtime`: refine startup ownership repair so it selectively fixes non-`dev:dev` entries and avoids following symlinks.

## Impact

- Affected code: `docker/entrypoint.sh`
- Affected behavior: container startup performance and ownership repair semantics
- Affected systems: mounted project directories, `/home/dev/.pi`, `/home/dev/.cargo`, `/home/dev/.npm`, `/home/dev/.npm-global`
