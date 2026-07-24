## Why

Building the development image currently evaluates runtime-only Compose requirements such as `PROJECT_PATH_1`, forcing users to prepare project-mount configuration before an image can be built. Build inputs and runtime mount selection have different lifecycles and should not depend on one another.

## What Changes

- Make the canonical image build succeed without `.env`, `PROJECT_PATH_*`, `COMPOSE_FILE`, or selected project directories.
- Keep project path selection and 1:1 bind mounts mandatory when launching the runtime container.
- Separate build-safe Compose resolution from runtime configuration without introducing fallback tool versions.
- Add tests proving build commands do not consume runtime mount configuration while run commands still reject missing project selection.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `docker-build-reproducibility`: Require canonical image builds to be independent of runtime project-mount configuration.
- `docker-runtime`: Preserve mandatory project selection for runtime launch while removing it from image-build prerequisites.

## Impact

- Canonical resolver/Compose orchestration and potentially the Compose service layout or generated build configuration.
- `docker-compose.yml`, `docker/versioning/rendering.py`, `docker/versioning/cli.py`, build-wrapper integration, and related tests.
- Follow-up README restructuring can present build and launch as genuinely independent operations.
