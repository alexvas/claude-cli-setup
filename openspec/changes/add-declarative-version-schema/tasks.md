## 1. Schema primitives and generic interpreter — depends on stable Stage 1/1A inventory contract, no Docker

- [ ] 1.1 **RED:** Add focused tests for primitive, constant, enum, pattern, list, closed-table, dynamic-map, reference, and tagged-union schema nodes, including precise nested dot-path failures
- [ ] 1.2 **RED:** Add schema self-validation tests for duplicate definitions, unresolved references, invalid discriminators, unknown semantic-rule names, factory-field mismatches, and unstable definition ordering
- [ ] 1.3 **GREEN:** Implement immutable schema node types and the authoritative registry boundary in `docker/versioning/schema.py` without selected dependency values or arbitrary structural callbacks
- [ ] 1.4 **GREEN:** Implement the standard-library generic interpreter and schema self-validation in `docker/versioning/validation.py`, preserving established exception families and immutable model construction
- [ ] 1.5 **INTROSPECT:** Inspect the schema-node dependency graph, enumerate supported DSL features, compare declared factory fields with dataclass signatures, and confirm domain-specific paths are absent from the interpreter
- [ ] 1.6 **VALIDATE:** Run schema primitive, self-validation, model-consistency, compile, and import-boundary tests offline and record evidence

## 2. Inventory registry and semantic-rule migration — depends on Stage 1, no Docker

- [ ] 2.1 **RED:** Add differential tests running the imperative and declarative validators over the complete valid/invalid fixture corpus and comparing acceptance, exception family, and owning TOML path
- [ ] 2.2 **RED:** Add tests for named rules covering tag/version equality, artifact and Rust-manifest URL consistency, entry-specific source/update pairs, required platforms, placeholder checksums, constraint consistency, and default/override matching
- [ ] 2.3 **GREEN:** Describe every current inventory stage, provider variant, artifact map, override, and runtime extension in the declarative registry with typed factories and semantic-rule references
- [ ] 2.4 **GREEN:** Implement the closed semantic-rule registry in `docker/versioning/semantic.py`, reusing `constraints.py` for its domain grammar and keeping cross-field logic out of the structural interpreter
- [ ] 2.5 **GREEN:** Switch `inventory.py` to declarative validation and remove obsolete allowed-key registries, duplicated provider/entry dispatch, and path-specific structural traversal after differential parity passes
- [ ] 2.6 **INTROSPECT:** Trace each production `docker-constructor.toml` value through schema node, semantic rules, and output model; inspect diagnostics and verify one authoritative structural definition remains
- [ ] 2.7 **VALIDATE:** Run differential, semantic-rule, real-inventory, immutability, sanitized-environment, and zero-network tests; record intentional diagnostic differences explicitly

## 3. Deterministic JSON Schema generation — depends on Stage 2, no Docker

- [ ] 3.1 **RED:** Add golden and property-focused tests mapping every supported schema node to JSON Schema Draft 2020-12, preserving descriptions, closed objects, tagged unions, dynamic maps, references, and `x-semantic-rules`
- [ ] 3.2 **RED:** Add subprocess tests for `schema`, `schema --check`, and `schema --write`, including byte stability, final newline, stale/missing artifact failures, explicit mutation, and non-mutation in check mode
- [ ] 3.3 **GREEN:** Implement deterministic registry export in `docker/versioning/schema_export.py` and generate checked-in `versions.schema.json` with a generated-source notice
- [ ] 3.4 **GREEN:** Add resolver CLI integration for stdout, non-mutating drift check, and explicit write behavior without affecting validate, build, launch, or runtime paths
- [ ] 3.5 **INTROSPECT:** Compare registry definitions with generated `$defs`, inspect stable ordering and semantic annotations, and scan the generated artifact for selected versions, URLs, revisions, or digests
- [ ] 3.6 **VALIDATE:** Regenerate twice and compare bytes, run drift checks from a clean and deliberately stale fixture, and execute all generator/CLI tests offline under a sanitized environment

## 4. Documentation and release validation — depends on Stage 3, no Docker

- [ ] 4.1 **RED:** Add documentation/source-contract tests requiring the authoritative registry location, generated-artifact warning, resolver-authoritative semantic caveat, refresh/check commands, and optional editor association guidance
- [ ] 4.2 **GREEN:** Document the declarative schema, named semantic-rule boundary, JSON Schema generation workflow, and Taplo/VS Code association options without making external tooling mandatory
- [ ] 4.3 **INTROSPECT:** Review generated schema usability in one available TOML/JSON Schema tool, compare its structural diagnostics with resolver semantic diagnostics, and document known editor limitations
- [ ] 4.4 **VALIDATE:** Run all versioning and documentation suites, schema drift check, `compileall`, `git diff --check`, and strict OpenSpec validation; confirm Docker and network are unnecessary and record final evidence
