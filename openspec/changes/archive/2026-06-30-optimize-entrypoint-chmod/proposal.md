## Why

Container startup still spends unnecessary time forcing group-write permissions across large trees when the target directories already have the desired mode. We need the same selective approach used for ownership repair so startup remains fast while ensuring the `dev` group can write where expected.

## What Changes

- Add startup permission repair for `chmod g+w` on the same top-level directories already processed by ownership repair.
- Apply permission changes only to files and directories that are missing group write access.
- Ensure the recursive permission scan does not follow symbolic links.
- Update runtime requirements to define selective group-write repair alongside selective ownership repair.

## Capabilities

### New Capabilities
- None.

### Modified Capabilities
- `docker-runtime`: refine startup repair so it selectively adds group-write permission to non-compliant entries in configured project mounts and runtime cache directories without following symlinks.

## Impact

- Affected code: `docker/entrypoint.sh`
- Affected behavior: container startup permission repair and startup performance
- Affected systems: mounted project directories, `/home/dev/.pi`, `/home/dev/.cargo`, `/home/dev/.npm`, and `/home/dev/.npm-global`
