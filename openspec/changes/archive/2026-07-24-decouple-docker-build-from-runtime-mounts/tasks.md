## 1. Define the build/runtime boundary

- [x] 1.1 Add RED subprocess and Compose tests proving canonical build evaluation succeeds with `.env`, `PROJECT_PATH_*`, and custom `COMPOSE_FILE` absent
- [x] 1.2 Add RED tests proving runtime run/config evaluation still rejects a missing main project and accepts launcher-provided 1:1 mounts
- [x] 1.3 Inspect Compose interpolation and resolver environment flow to select the smallest build-only/runtime-additive configuration boundary

## 2. Decouple image construction

- [x] 2.1 Refactor Compose configuration so service `pi` can be built without evaluating runtime working-directory or volume requirements
- [x] 2.2 Preserve required resolver-provided version arguments, effective inventory generation, target name, image tag, and custom UID/GID inputs
- [x] 2.3 Keep runtime project selection strict in the launcher and supported low-level run path without placeholder host directories
- [x] 2.4 Update build-wrapper and source-contract expectations to use the separated configuration model

## 3. Validate behavior

- [x] 3.1 Run sanitized-environment resolver, Compose rendering, launcher, and source-contract suites without a Docker daemon
- [x] 3.2 On a Docker host, build with no project configuration and verify the resulting image with `docker/verify-runtime.sh`
- [x] 3.3 Launch with selected main/additional projects and confirm working directory, 1:1 mounts, and missing-selection failure
- [x] 3.4 Run strict OpenSpec validation and `git diff --check`
