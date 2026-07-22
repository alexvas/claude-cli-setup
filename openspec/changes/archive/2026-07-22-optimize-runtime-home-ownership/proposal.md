## Why

Runtime assembly currently runs `chown -R dev:dev /home/dev` after copying large uv, Rust, Pi, and MCP trees, adding roughly two minutes of recursive metadata work to an otherwise cached Docker build. Those trees are already produced by the same configurable `dev` user, so ownership should be preserved by stage assembly and verified explicitly instead of repaired unconditionally.

## What Changes

- Remove the whole-home recursive ownership rewrite from the runtime image build.
- Create only newly introduced runtime directories with the intended `dev:dev` ownership.
- Preserve ownership of copied tree contents and repair only cross-stage destination roots with targeted non-recursive `chown dev:dev`, preserving custom `DEV_UID` and `DEV_GID` without whole-home traversal.
- Extend `docker/verify-runtime.sh` to fail when required image-provided runtime home paths contain entries not owned by `dev:dev`.
- Restrict `CHOWN_WORK_ON_START` repair to `PROJECT_PATH_*` paths, which Compose and `launch-pi.py` define as host-directory bind mounts; require an actual mount point, assign `dev:dev`, and grant user/group read-write access plus directory traversal without making all regular files executable. Ordinary image directories and non-project mounts must not be scanned or modified.
- Install `util-linux` explicitly as the runtime provider of `mountpoint`; when repair is enabled, startup must fail immediately if mount detection is unavailable.
- Verify image-provided `.cargo`, `.npm`, and `.npm-global` content through `docker/verify-runtime.sh`; permit startup ownership and permission repair for the explicitly supported host `.pi` mount as well as project mounts.
- Cover default and non-default UID/GID configurations while preserving startup repair only for mounted project worktrees.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `docker-runtime`: Runtime assembly must preserve correct ownership for image-provided home artifacts without recursively chowning the complete home tree; runtime smoke checks must verify that invariant; and startup repair must be limited to actual `PROJECT_PATH_*` host bind mounts.

## Impact

- Affects `Dockerfile`, `docker/verify-runtime.sh`, runtime verification commands, and potentially maintained build documentation.
- Does not modify `docker/build_wrapper.py` or make ownership checking part of the network-aware build-wrapper flow.
- Reduces runtime assembly time and avoids an expensive ownership-only snapshot operation.
- Preserves entrypoint repair only for actual `PROJECT_PATH_*` host bind mounts. Other home/configuration/cache mounts are outside startup repair and remain the caller's responsibility.
