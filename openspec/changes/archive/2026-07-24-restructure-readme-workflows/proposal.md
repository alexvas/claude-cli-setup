## Why

The maintained README files bury the three primary user jobs—build, launch, and update—under setup details, internal invariants, cache diagnostics, and scattered option descriptions. A user who sees a new Pi release cannot currently determine the complete inspect-review-edit-rebuild workflow from the documentation.

## What Changes

- Reorganize all maintained README translations around three primary actions: build the image, launch the environment with interactive project selection, and inspect/apply environment component updates.
- Lead the update section with a concrete Pi update walkthrough, then generalize to other inventory entries and provider types.
- Group update-check flags by user intent rather than listing them across unrelated paragraphs.
- Document version-managed component categories, installation locations, update providers, and the distinction between image content and mounted Pi-home extensions.
- Remove top-level setup, Python implementation detail, Python override, BuildKit cache verification, shell prompt, and standalone extension-installation sections from the main user flow.
- Consolidate verification, extension refresh, host permission repair, Docker storage cleanup, and user-facing cache cleanup under Maintenance while removing detailed Dockerfile/cache-development notes.
- Reduce troubleshooting to actionable current failures, with a rootless Docker ownership/permission repair procedure using `<docker-dev>:<docker-dev>`, `ug+rwX`, host UID/GID `100999` guidance, and host group membership setup.
- Adopt the executable resolver command form and build/runtime separation delivered by the two sibling changes.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `docker-runtime`: Require maintained documentation to be organized around build, interactive launch, updates, and maintenance, with accurate project-selection and host-permission guidance.
- `docker-build-reproducibility`: Require a concrete review-and-apply update workflow, including a focused Pi example, component taxonomy, grouped update options, validation, rebuild, and mounted-extension refresh.

## Impact

- `README.md`, `README.en.md`, and `README.zh.md`.
- Documentation consistency and semantic-source tests.
- References to executable `docker/versions.py` and build-without-runtime-configuration behavior depend on `make-version-resolver-executable` and `decouple-docker-build-from-runtime-mounts` being implemented first or in parallel.
