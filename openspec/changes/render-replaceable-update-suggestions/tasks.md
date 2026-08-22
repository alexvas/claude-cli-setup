# Implementation Contract

Every phase follows RED → GREEN → INTROSPECT → VALIDATE. GREEN work SHALL be limited to satisfying that phase's RED evidence while preserving read-only discovery, provider classification, structured JSON suggestions, and update exit-policy behavior.

Phase dependency DAG:

```text
Phase 1 → Phase 2 → Phase 3 → Phase 4
```

## 1. Replacement Ownership and Raw Block Evidence

- [x] 1.1 **RED:** Add fixtures and focused tests mapping every current update target to exactly one replaceable raw inventory block; require Rust and nested rustup targets to share the `build.stages.toolchain.rust` owner.
- [x] 1.2 **RED:** Add tests requiring target-owner grouping to be deterministic, to emit no overlapping owner blocks, and to preserve distinct owners in inventory order.
- [x] 1.3 **RED:** Add tests proving a complete raw block retains unchanged source, update, validation, override, and all configured artifact-platform values while candidate leaves overlay only applicable updates.
- [x] 1.4 **GREEN:** Implement explicit target-to-replaceable-block ownership and raw-subtree selection without changing provider discovery, classification, or structured JSON suggestion serialization.
- [x] 1.5 **GREEN:** Implement deterministic grouping and combined candidate overlay for each replacement owner.
- [x] 1.6 **INTROSPECT:** Audit every build and runtime update target family for missing ownership, nested overlap, artifact-platform loss, typed-model defaults, and raw source leakage.
- [x] 1.7 **VALIDATE:** Run focused update-target, provider, candidate-classification, ownership, grouping, and JSON-suggestion suites.

## 2. Canonical Replacement Fragment Rendering

- [ ] 2.1 **RED:** Add exact text-rendering tests for full canonical TOML fragments containing complete target tables, unabridged candidate version/tag/URL/checksum values, retained unchanged fields, and deterministic table/key/platform ordering.
- [ ] 2.2 **RED:** Add tests that combine all applicable updates for a shared Rust block into one complete fragment and reject duplicate emitted TOML declarations.
- [ ] 2.3 **RED:** Add round-trip tests that replace each fixture's complete old canonical block with its suggestion fragment and require the ordinary inventory loader to accept the resulting inventory.
- [ ] 2.4 **RED:** Add multi-platform tests proving an update to one artifact does not remove untouched configured platforms after replacement.
- [ ] 2.5 **GREEN:** Implement deterministic complete-block TOML serialization from overlaid raw reviewed data; do not reconstruct fragments from defaults-populated typed models.
- [ ] 2.6 **GREEN:** Replace candidate-only text suggestion rendering with complete grouped replacement fragments while leaving structured JSON suggestions unchanged.
- [ ] 2.7 **INTROSPECT:** Review TOML quoting, dotted/nested tables, array values, ordering, complete-block boundaries, and the difference between parseable fragments and full validated inventories.
- [ ] 2.8 **VALIDATE:** Run focused TOML renderer, replacement round-trip, multi-platform, Rust/rustup grouping, text CLI, and JSON-contract suites.

## 3. Visual Replacement Boundaries and Canonical Migration

- [ ] 3.1 **RED:** Add tests requiring every text replacement fragment to begin with `# --- <display path> ---`, stripping only leading `build.stages.` or `runtime.` once while retaining full canonical TOML table paths.
- [ ] 3.2 **RED:** Add tests proving missing, altered, or duplicated visual comments in a custom inventory neither alter parsing/validation nor prevent complete-fragment suggestion construction.
- [ ] 3.3 **RED:** Add semantic scans requiring matching visual headers immediately before every replaceable block in the repository canonical `docker-constructor.toml`.
- [ ] 3.4 **GREEN:** Add concise visual headers to the canonical inventory and emit the matching headers for every replacement fragment.
- [ ] 3.5 **GREEN:** Update user-facing suggestion labels to describe manual complete-block replacement rather than candidate-only review values, without implying automatic application.
- [ ] 3.6 **INTROSPECT:** Verify comments remain visual-only, headers delimit exactly one replacement owner, shortening is display-only, and no absolute source path or machine-local data enters fragments.
- [ ] 3.7 **VALIDATE:** Run focused canonical-inventory, custom-inventory, renderer, CLI display, and semantic-scan suites.

## 4. Read-Only and Documentation Closure

- [ ] 4.1 **RED:** Add no-effect regression tests proving `check-updates --suggest` does not write the inventory, working tree, cache policy, or any generated file while producing complete fragments.
- [ ] 4.2 **RED:** Add no-candidate and incomplete-candidate tests requiring an explicit no-replacement-block message and no empty/unlabelled fragment.
- [ ] 4.3 **GREEN:** Preserve normal report ordering, no-suggestion/incomplete diagnostics, provider behavior, result ordering, JSON fields/values, and exit policies around the new text renderer.
- [ ] 4.4 Update maintained documentation and examples to show locating a visual header, replacing the complete block through the next header, preserved fields/platforms, optional headers in custom inventories, and the no-automatic-application boundary.
- [ ] 4.5 **INTROSPECT:** Reconcile implementation, raw inventory ownership, main semantic source, delta spec, design, tasks, docs, and CLI diagnostics; remove stale candidate-only or falsely appendable-TOML claims.
- [ ] 4.6 **VALIDATE:** Run the complete project test suite and `openspec validate render-replaceable-update-suggestions`; confirm every modified scenario has automated evidence.
