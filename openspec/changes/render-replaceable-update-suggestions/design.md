## Context

`check-updates` classifies provider candidates into structured `UpdateResult` records, and current text-mode `--suggest` rendering serializes only candidate leaf changes under a target table. A reviewed inventory already declares that table and its nested source, artifact, and update tables, so appending that output produces duplicate TOML declarations. It also omits unchanged fields that are required when a user replaces the complete block manually.

The target model is flatter than inventory replacement ownership: `build.stages.toolchain.rust` and `build.stages.toolchain.rust.rustup` are separate update targets but belong to one replaceable Rust inventory block. The canonical repository inventory can receive visual boundary comments, but TOML comments are neither parsed nor authoritative for custom inventories.

## Goals / Non-Goals

**Goals:**

- Render one complete, manually replaceable TOML fragment for each affected reviewed inventory block.
- Preserve all unchanged reviewed values in the block, including every configured artifact platform.
- Apply all applicable candidates that affect a shared replacement block before rendering it.
- Give users concise visual headings for locating blocks in the canonical inventory and suggestions.
- Preserve non-mutating discovery, provider/classification behavior, JSON suggestion data, and exit policy.

**Non-Goals:**

- Automatically applying suggestions, editing inventories, or generating patches.
- Preserving comments, whitespace, source table ordering, or formatting inside a manually replaced block.
- Requiring visual comments in custom inventories or using them as parser metadata.
- Changing update candidates, applicability rules, provider network traffic, structured JSON fields, or machine-local configuration.

## Decisions

### Render replacement blocks from raw reviewed inventory data

The suggestion builder receives the parsed raw reviewed inventory alongside typed update results. It identifies the full raw subtree for each replaceable inventory block, overlays candidate version, tag, digest, revision, URL, and checksum values, and serializes the entire updated subtree deterministically. It does not reconstruct blocks solely from typed models, which could add defaults or lose explicitly reviewed source data.

The resulting fragment contains all tables and leaves in that block: unchanged source and update fields, validation/override fields where applicable, and untouched platform artifacts remain present. This makes a manual replacement safe even when only one platform was updated.

### Group update targets by replacement owner

The grouping key is a schema-defined replaceable inventory block, not `UpdateResult.path`. A block receives all applicable changes from its contained targets and is emitted once. In particular, Rust and its nested rustup bootstrap candidate become one `build.stages.toolchain.rust` fragment. Unrelated entries remain separate fragments in deterministic inventory order.

This avoids overlapping emitted TOML tables and gives each replacement exactly one visual boundary.

### Use concise optional visual headers

Every emitted block begins with:

```toml
# --- <display path> ---
```

For display only, `build.stages.` and `runtime.` are stripped exactly once; all TOML table headers retain their full canonical paths. Thus `build.stages.toolchain.uv` displays as `toolchain.uv`, while `runtime.pi-extensions.example` displays as `pi-extensions.example`.

During migration the repository's canonical `docker-constructor.toml` receives the same header directly before every replaceable block. Custom inventories need not contain headers; their absence, alteration, or duplication never affects loading, validation, target grouping, or rendering. Users can use headers to select from one header through the next header in the canonical layout.

### Preserve explicit text and JSON boundaries

Text `--suggest` replaces the existing candidate-only mapping-style output with complete fragments and labels them as manual replacement suggestions, not automatic mutation. The normal report remains before suggestions. The existing structured JSON `suggestions` list remains unchanged because it is an API-oriented leaf-change representation rather than a pasteable TOML representation.

When no applicable candidate exists, text retains an explicit no-suggestion message and emits no replacement header or empty fragment.

### Validate replacement evidence without mutating inventory

Tests construct a complete fixture inventory, obtain suggestion text from deterministic applicable results, replace each named canonical block in a copy, and load the result through the ordinary inventory validator. They also verify retained fields, all platform entries, shared Rust grouping, canonical header migration, no-candidate behavior, custom inventory operation without headings, and no filesystem mutation by `--suggest`.

## Risks / Trade-offs

- **[Manual replacement discards local comments inside a block]** → State this explicitly; regenerate only canonical reviewed TOML values and leave comments non-semantic.
- **[Two update targets overlap one inventory entry]** → Group by schema-defined replacement owner and test Rust/rustup as one fragment.
- **[A new target is not mapped to a replacement owner]** → Make target-to-owner mapping explicit and require tests for every update target family.
- **[A custom inventory lacks headers]** → Generate headers independently of source comments and retain normal suggestion behavior.
- **[Renderer changes JSON accidentally]** → Keep structured `serialize_suggestions()` unchanged and cover its exact contract separately.

## Migration Plan

1. Define raw-block ownership for every current update target and add failing replacement tests.
2. Implement grouping, raw overlays, deterministic full-block TOML serialization, and text rendering.
3. Insert visual headers into the repository canonical inventory and update semantic/documentation checks.
4. Validate replacement round trips, existing update/provider regressions, JSON compatibility, and read-only behavior.
5. Rollback restores candidate-only text suggestions and removes canonical visual comments; no inventory schema or stored data migration is required.

## Open Questions

None. Replacement ownership, grouping, raw-data source, header syntax and shortening, comment semantics, platform preservation, JSON boundary, and no-mutation behavior are fixed.
