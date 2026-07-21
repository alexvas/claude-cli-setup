## Why

The image currently implements `python3` as `uv run python`, so an ordinary interpreter invocation can discover project metadata, synchronize environments, download runtimes, and trigger multiple concurrent `uv run` operations. This is currently causing Docker builds to stall and makes Python availability depend on unrelated uv tool installation side effects.

## What Changes

- Install an explicit uv-managed CPython runtime, defaulting to exactly `3.14.6`, during the image build.
- Expose `python` and `python3` as direct executables for that installed runtime rather than wrappers or shell aliases around `uv run`.
- Allow deliberate overrides to Python `3.14.6` or newer through a Compose/Docker build argument while retaining an exact default.
- Remove the synthetic `pip` alias; users invoke package operations explicitly through `uv pip install ...`.
- Add build-time and runtime checks proving that `python3` is direct, reports the requested supported version, and does not depend on project discovery.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `docker-runtime`: Replace project-aware `uv run python` indirection with an explicitly installed direct Python runtime and remove the advertised `pip` alias.

## Impact

- Affects `Dockerfile`, `docker-compose.yml`, runtime verification, and maintained README translations.
- Changes the runtime contract for `python`, `python3`, and `pip`; there will be no standalone `pip` command promised by the image.
- Overlaps with the Python/uv version inventory work in `pin-docker-toolchain-versions`; this urgent change establishes the Python contract and its exact default, which that broader change should preserve rather than duplicate.
