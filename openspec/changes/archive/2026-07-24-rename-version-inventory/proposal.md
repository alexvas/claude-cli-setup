## Why

The name `versions.toml` describes only one aspect of a file that now defines the complete Docker construction inventory: sources, providers, artifacts, digests, override policy, cache settings, runtime extensions, and selected versions. Renaming it to `docker-constructor.toml` makes its architectural role explicit before direct-Docker orchestration expands that role further.

## What Changes

- **BREAKING** Rename the authoritative root inventory from `versions.toml` to `docker-constructor.toml`.
- Rename generated effective-inventory defaults and the read-only in-image inventory to the same `docker-constructor.toml` basename.
- Update resolver defaults, safety checks, Docker build/runtime consumers, verification, tests, fixtures where semantically appropriate, and all maintained documentation.
- Preserve explicit `--inventory <path>` support for arbitrary TOML filenames; do not add an implicit fallback to the old authoritative name.
- Update active OpenSpec artifacts that prescribe the old filename so subsequent changes do not restore stale paths.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `docker-build-reproducibility`: Rename the authoritative and effective Docker construction inventory while preserving its source-of-truth, validation, override, and runtime-verification contracts.

## Impact

- Renames the repository root file and generated/runtime inventory paths.
- Affects `docker/versioning`, Dockerfile/runtime scripts, verification tooling, semantic-source checks, acceptance fixtures, README translations, and active OpenSpec changes.
- Existing commands or automation that explicitly reference `versions.toml` must migrate to `docker-constructor.toml`.
- Inventory schema and selected values do not change.
