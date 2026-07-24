## Context

`docker-compose.yml` combines image build configuration with runtime working-directory, bind-mount, and environment requirements. Compose interpolation evaluates the whole service model before `build`, so `${PROJECT_PATH_1:?…}` makes image construction depend on a runtime project choice. The version resolver correctly owns selected tool inputs; it should not have to invent a project mount to satisfy Compose.

## Goals / Non-Goals

**Goals:**
- Make canonical image builds independent of `.env` and project selection.
- Preserve strict runtime failure when no main project is selected.
- Keep one version-resolution path and one final runtime image target.
- Preserve build-wrapper and launcher behavior.

**Non-Goals:**
- Remove Compose or replace the launcher.
- Make runtime project mounts optional.
- Add version fallbacks or alter `versions.toml`.
- Redesign host-gateway detection.

## Decisions

### Model build and runtime as different configuration phases

The build path will use a Compose model that contains build concerns but no required runtime interpolation. Runtime launch will add or select the service configuration that requires working directory and mounts.

Possible realizations include a build-only Compose service/profile, a generated build override that neutralizes runtime-only fields, or moving strict project validation from base Compose into launcher/run-specific configuration. Implementation should select the smallest form that `docker compose build pi` can evaluate without placeholder host paths while `run pi` still fails clearly.

Rejected alternative: set `PROJECT_PATH_1=$PWD` silently for every build. It hides the coupling rather than removing it and makes an unrelated host path part of build configuration.

### Keep version resolution before Compose

`docker/versions.py compose` remains responsible for build arguments and effective inventory generation. Runtime separation must not create a second mapping or bypass required interpolation for tool inputs.

### Test command intent, not only rendered YAML

Tests will execute resolver-mediated build command construction under an environment with project variables removed, and separately assert that runtime configuration without a selected project fails. If Compose is available, config/build evaluation should cover the real boundary.

## Risks / Trade-offs

- [Two Compose layers can drift] → Keep shared service/build definitions in one place and make runtime configuration additive.
- [Low-level users may invoke the wrong configuration] → Keep the resolver canonical and return actionable runtime errors.
- [Compose still evaluates an unexpected runtime field] → Add a sanitized-environment integration test for the exact build command.

## Migration Plan

1. Add failing sanitized build/runtime boundary tests.
2. Separate runtime-only Compose requirements from build evaluation.
3. Update wrapper/launcher tests and static contracts.
4. Verify default and custom UID/GID builds remain equivalent.
5. Roll back by restoring the previous single-service Compose model if runtime launch behavior regresses.

## Open Questions

- Is a build-only Compose service clearer than an additive runtime override while preserving the public image tag?
- Should direct low-level `docker compose run` remain supported, or should all runtime launch flow through `launch-pi.py`?
