## Why

`ty check` currently reports 879 diagnostics because it scans production code and dynamic unittest doubles without a declared project boundary. Real production type defects are mixed with test-double noise, so the command cannot serve as a reliable quality gate.

## What Changes

- Define and document a reproducible `ty` invocation for the direct constructor production surface, with its checked-in configuration in `pyproject.toml`, Python 3.14 semantics, and automatic discovery of the container's sole Python installation.
- Correct real type-contract defects in production modules, including dependency injection, raw external data narrowing, missing names, optional values, and incompatible protocols.
- Exclude only retired verification artifacts and dynamic test doubles from the initial production gate; do not globally disable diagnostics or mask production errors.
- Add automation that makes the agreed type-check command pass with no diagnostics.

## Capabilities

### New Capabilities
- None.

### Modified Capabilities
- None.

This is internal typing and tooling work; it does not change product requirements.

## Impact

- Affects Python annotations and type-safe interfaces in `docker/`.
- Adds repository-local `ty` configuration in `pyproject.toml` and CI/test integration.
- Leaves runtime CLI, inventory, build, and update behavior unchanged.
