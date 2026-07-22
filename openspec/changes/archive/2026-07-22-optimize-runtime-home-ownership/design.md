## Context

The runtime stage copies `/home/dev/.pi`, `.local`, `.rustup`, `.cargo/bin`, and `mcp` from stages derived from the same `base` stage and built with the same `DEV_UID` and `DEV_GID`. Their numeric ownership is therefore already compatible with the runtime `dev` account. Runtime assembly nevertheless executes `chown -R dev:dev /home/dev`, recursively traversing large Python and Rust installations and creating a snapshot operation observed to take about 120 seconds.

The project already provides `docker/verify-runtime.sh` as the host-side smoke check for the final image. Ownership is part of the runtime contract, so that script is the natural verification point and avoids coupling this invariant to host-network probing in `docker/build_wrapper.py`.

## Goals / Non-Goals

**Goals:**
- Eliminate recursive whole-home ownership work during image assembly.
- Ensure image-provided runtime artifacts are owned by `dev:dev` for default and custom UID/GID builds.
- Make the existing runtime smoke check fail with an actionable path when ownership preservation regresses.
- Keep the ownership check read-only and prevent it from masking failures through repair.
- Restrict startup ownership and read/write/traversal repair to configured `PROJECT_PATH_*` paths, which the supported Compose and launcher interfaces define as host-directory bind mounts.

**Non-Goals:**
- Add ownership verification to `docker/build_wrapper.py`.
- Remove entrypoint repair for actual project bind mounts configured through `PROJECT_PATH_*`.
- Recursively rewrite ownership after the image has been built.
- Validate arbitrary user-created or bind-mounted content.
- Change tool installation locations or cache boundaries.

## Decisions

### Preserve ownership across stages instead of repairing the whole home

Remove `chown -R dev:dev /home/dev`. Cross-stage `/home/dev` trees (`.pi`, `.local`, `.rustup`, `.cargo/bin`, and `mcp`) preserve `dev:dev` ownership for their contents, but Docker or the base stage can leave destination directory roots as `root:root` (including the parent `.cargo` directory). Copy them normally and repair only those destination roots with targeted non-recursive `chown dev:dev`. Create `/home/dev/work`, `/home/dev/.npm-global`, and `/home/dev/.npm-global/bin` with `install -d -o dev -g dev` or an equivalent targeted operation.

This is preferred over `find ... ! -user dev -exec chown` because a selective post-copy chown still performs an extra full traversal and snapshot. Ownership is instead assigned as part of each copy boundary and remains compatible with custom `DEV_UID`/`DEV_GID` through target-stage name resolution.

### Verify ownership inside docker/verify-runtime.sh

Extend the existing script's `docker run` smoke command. The image starts through its normal entrypoint and drops to `dev`, but no host volumes are mounted, so the inspected Pi, uv/Python, Rust/Cargo, MCP, work, and npm paths come from the image.

The check confirms required paths exist and uses a non-following `find` traversal to locate the first entry whose user or group differs from `dev`. Because the smoke process runs as `dev`, it cannot repair root-owned entries; any mismatch is printed and fails the script.

Checking account/group names inside the image is preferred over comparing host numeric IDs because custom `DEV_UID` and `DEV_GID` values still map to the runtime `dev:dev` identity.

### Limit verification to image-provided paths

Inspect `.pi`, `.local`, `.rustup`, `.cargo/bin`, `mcp`, `work`, and `.npm-global`. Do not scan bind-mounted projects, host-mounted configuration, transient caches absent from the image, or the entire home indiscriminately. Do not follow symbolic links.

Run the smoke container with `CHOWN_WORK_ON_START=0` so the ownership assertion remains independent of startup repair. The mount-only entrypoint policy should already leave unmounted image paths untouched, but disabling repair makes that test precondition explicit.

### Restrict startup repair to project bind mounts

Consider only paths supplied through `PROJECT_PATH_*`. The supported Compose files and `launch-pi.py` map these variables from host directories to the same absolute container paths. Install `util-linux` explicitly in the runtime as the provider of `mountpoint`. Before repair, require `mountpoint -q -- "$path"` to confirm that the destination is mounted rather than an ordinary image-layer directory. A configured path that exists but is not mounted is skipped, and Git safe-directory registration is limited to repaired project mounts.

When `CHOWN_WORK_ON_START` is enabled but `mountpoint` is unavailable, fail startup immediately with an actionable error. Continuing would silently disable the requested repair and defer the failure to a less clear project-access error.

After assigning `dev:dev` ownership, grant user and group read/write access and directory traversal. Use `chmod ug+rwX`: `X` grants execute to directories and preserves executable-file intent without making every regular file executable.

Do not process fixed `/home/dev/.cargo`, `.npm`, or `.npm-global` paths in the entrypoint, even if users mount content there. The explicitly supported host mount at `/home/dev/.pi` is repaired when it is an actual mount point. `docker/verify-runtime.sh` checks the image-provided versions of these paths without host volumes and with startup repair disabled.

### Keep build and verification separate

Direct Compose and wrapper builds remain build-only operations. Users and host verification workflows run `docker/verify-runtime.sh <image>` after building, as already documented. This keeps `build_wrapper.py` focused on host reachability and avoids duplicating image-selection logic.

## Risks / Trade-offs

- [A copied stage later uses a different UID/GID] → Runtime verification fails if copied contents escape the shared identity; retain targeted root ownership repair and investigate the source stage rather than restoring whole-home recursion.
- [The normal entrypoint masks bad ownership] → Limit repair to `PROJECT_PATH_*` host bind mounts and the explicitly supported `.pi` mount, and also set `CHOWN_WORK_ON_START=0` in the verification container.
- [`mountpoint` is absent or broken despite the explicit `util-linux` dependency] → Fail startup when repair is enabled and fail runtime verification; do not continue with disabled or unverified repair.
- [Scanning large trees adds smoke-test time] → A read-only `find` avoids layer creation and metadata rewrites; measure it and keep the path set limited to required image artifacts.
- [Direct builds do not automatically run smoke checks] → Retain and document the explicit `docker/verify-runtime.sh` command.
- [Symlinks point outside inspected trees] → Do not follow symlinks; verify ownership of directory entries only, matching entrypoint safety conventions.

## Migration Plan

1. Extend runtime verification and confirm the current recursively-chowned image passes.
2. Limit entrypoint candidates to `PROJECT_PATH_*`, gate each on host-bind-mount detection, and test mounted and unmounted project cases.
3. Replace recursive build-time chown with targeted directory creation.
4. Build with default and custom UID/GID values and run `docker/verify-runtime.sh` after each build.
5. Compare runtime assembly timing before and after removal.
6. Keep normal cross-stage copies plus targeted ownership repair for their destination roots; never restore whole-home recursion.

## Open Questions

None.
