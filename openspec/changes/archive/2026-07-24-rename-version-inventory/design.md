## Context

`versions.toml` began as a list of pinned versions but is now the authoritative typed input for Docker construction, update discovery, artifact integrity, override policy, cache behavior, runtime extension metadata, and effective image verification. Its basename is embedded in CLI defaults, generated output paths, the Docker image, scripts, tests, documentation, and semantic-source exclusions.

The concurrent direct-Docker change consumes the same inventory and must use the new name consistently.

## Goals / Non-Goals

**Goals:**
- Rename the authoritative, generated effective, and in-image inventory consistently.
- Preserve schema, selected values, validation behavior, and explicit custom inventory paths.
- Make stale authoritative-name references detectable by tests.

**Non-Goals:**
- Redesign the TOML schema or version resolver.
- Rename Python domain concepts such as `Inventory` solely for cosmetic consistency.
- Reject arbitrary filenames supplied through `--inventory`.
- Rewrite archived OpenSpec history.

## Decisions

### Use one basename across inventory lifecycle

The repository source will be `docker-constructor.toml`, generated effective output will default to `.docker-generated/docker-constructor.toml`, and the image copy will live at `/usr/local/share/pi-cli/docker-constructor.toml`. A single basename makes source/effective/runtime relationships recognizable while their directories distinguish authority.

### Make the rename explicit and fail closed

Default discovery will look only for `docker-constructor.toml`; it will not silently fall back to `versions.toml`. This avoids two competing sources of truth. Explicit `--inventory` remains filename-agnostic for fixtures and experiments.

### Distinguish semantic references from incidental fixture names

Production defaults, user-visible help, maintained docs, semantic tests, and active OpenSpec artifacts must use the new name. Temporary test files may retain arbitrary names when filename identity is irrelevant, but tests of authoritative discovery and output safety must use the new basename.

### Coordinate with active changes

Active changes that mention the authoritative inventory are updated in the same implementation so applying them later cannot reintroduce `versions.toml`. Archived changes remain immutable historical records and are excluded from stale-reference enforcement.

## Risks / Trade-offs

- [External automation breaks] → Mark the rename as breaking and provide a direct old-to-new command/path migration in documentation.
- [A stale path creates a second inventory] → Add repository-wide semantic checks for supported source while excluding archives and intentionally arbitrary fixtures.
- [Generated output overwrites the authoritative file] → Update output-path safety checks to reject `docker-constructor.toml` at repository root.
- [Concurrent change artifacts drift] → Include active OpenSpec paths in source-contract tests and validate every active change strictly.

## Migration Plan

1. Establish failing path/default/source-contract tests.
2. Rename the root inventory and migrate resolver discovery and generated output safety.
3. Migrate image/runtime consumers and verification.
4. Migrate maintained docs, active OpenSpec artifacts, and repository-owned scripts.
5. Validate that no supported reference depends on `versions.toml` and that explicit custom inventories still work.

Rollback requires restoring all three lifecycle paths together; mixed old/new inventory names are unsupported.
