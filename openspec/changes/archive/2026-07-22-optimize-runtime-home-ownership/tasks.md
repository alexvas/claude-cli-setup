## 1. Add runtime ownership verification

- [x] 1.1 Extend `docker/verify-runtime.sh` with the required image-provided `/home/dev` path inventory and explicit existence checks
- [x] 1.2 Run the smoke container with `CHOWN_WORK_ON_START=0` and add a non-following ownership scan that reports the first entry not owned by `dev:dev`
- [x] 1.3 Confirm ownership mismatch, missing-path, and Docker command failures propagate as non-zero script exits without repair

## 2. Restrict startup repair to project mounts

- [x] 2.1 Limit entrypoint repair candidates to configured `PROJECT_PATH_*` paths and require host-bind-mount detection before traversing them
- [x] 2.2 Limit Git safe-directory registration to repaired project bind mounts and skip configured paths that merely exist in the image
- [x] 2.3 Leave `.cargo`, `.npm`, `.npm-global`, named volumes, and all other non-project mounts untouched by startup repair; repair the explicitly supported `/home/dev/.pi` mount
- [x] 2.4 Verify host-directory `PROJECT_PATH_*` mounts receive `dev:dev` ownership plus `ug+rwX`, while identical unmounted project paths and non-project mounts remain untouched
- [x] 2.5 Verify `util-linux` provides `mountpoint` in the runtime and that enabled startup repair exits non-zero with an actionable error when the command is unavailable

## 3. Remove recursive runtime ownership work

- [x] 3.1 Replace runtime `chown -R dev:dev /home/dev` with targeted creation of `work`, `.npm-global`, and `.npm-global/bin` as `dev:dev`
- [x] 3.2 Preserve cross-stage Pi, uv/Python, Rust/Cargo, and MCP contents and repair only their destination roots with targeted non-recursive ownership changes, without adding a whole-home operation

## 4. Verify behavior and performance

- [x] 4.1 Build with default UID/GID and confirm `docker/verify-runtime.sh` passes all ownership and existing tool checks
- [x] 4.2 Build with non-default `DEV_UID` and `DEV_GID` and confirm every required image-provided path resolves to `dev:dev`
- [x] 4.3 Introduce or simulate one mismatched image-owned entry and confirm runtime verification fails with its path instead of repairing it
- [x] 4.4 Exercise startup with mounted and unmounted project targets plus the supported `/home/dev/.pi` mount and other non-project mounts, confirming only supported mounts are mutated
- [x] 4.5 Measure runtime assembly before and after the change and record the removal of the recursive-chown delay
- [x] 4.6 Update maintained documentation to state that startup repair applies only to project bind mounts and describe the ownership verification command
