## Why

The version inventory validator currently spreads schema knowledge across imperative key registries, provider dispatch, entry-specific checks, and model construction. As `docker-constructor.toml` and its providers grow, that duplication makes the accepted format difficult to document, review, and keep consistent with editor tooling.

## What Changes

- Add one authoritative, standard-library Python schema registry describing inventory tables, required and optional fields, primitive types, constants, enums, patterns, discriminated source/update variants, dynamic maps, model factories, and named semantic rules.
- Replace entry-specific structural traversal and unknown-key validation with a generic schema interpreter that preserves actionable TOML dot-path diagnostics and immutable typed inventory output.
- Keep domain relationships—constraint consistency, default/override matching, tag/version equality, URL/version consistency, and required-platform references—as explicit named semantic rules rather than inventing a general expression language.
- Generate a deterministic `versions.schema.json` from the authoritative registry for documentation, editor integration, and optional standards-based checks without making runtime validation depend on `jsonschema` or another package.
- Add drift checks proving the generated JSON Schema is current and structural validation remains offline, deterministic, and standard-library-only.
- Preserve `docker-constructor.toml`, the public resolver interface, selected values, effective inventory behavior, and provider/update semantics established by `manage-docker-toolchain-versions`.

## Capabilities

### New Capabilities

- `declarative-version-schema`: Defines the authoritative declarative inventory schema, generic structural validation, named semantic-rule boundary, deterministic JSON Schema generation, and schema drift guarantees.

### Modified Capabilities

<!-- None. This change builds on the in-progress docker-build-reproducibility capability without changing its externally observable version-selection contract. -->

## Impact

- Affects `docker/versioning/` schema, inventory loading, model construction, and related tests.
- Adds a generated root-level or documented schema artifact such as `versions.schema.json` and editor-facing schema association guidance.
- Requires implementation after the Stage 1/1A inventory contract from `manage-docker-toolchain-versions` is stable; it does not require Docker or network access.
- Adds no runtime Python dependency and does not change Docker build arguments, runtime ownership, or update-provider network behavior.
