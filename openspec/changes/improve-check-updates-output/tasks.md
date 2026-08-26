# Implementation Contract

Every checkbox below is required for completion. A phase is complete only when all four RED → GREEN → INTROSPECT → VALIDATE steps pass and its listed deliverables exist. GREEN work SHALL be limited to making that phase's RED tests pass; newly discovered scope SHALL be added to this contract before implementation.

Phase dependency DAG:

```text
Phase 1 ──┬──> Phase 2 ─────────┐
          └──> Phase 3 ──> Phase 4 ──> Phase 5
```

A phase MAY depend only on the earlier phases named in its `Depends on` line. Phase 2 and Phase 3 are independent after Phase 1.

## 1. Compact Report Foundation

**Depends on:** none

**Deliverables:** tested helpers for compact target/date/value formatting; default `TARGET | PROVIDER | CURR -> NEXT | STATUS | PUBLISHED` report; conditional `Details:` section.

- [x] 1.1 **RED:** Add failing renderer tests that specify exact `build.stages.` prefix removal, unchanged non-matching paths, `YYYY-MM-DD` publication dates, invalid/missing date fallback, long-hex abbreviation with `sha256:` preservation, absent/equal candidate fallback, and `<current> -> <candidate>` values under the `CURR -> NEXT` heading.
- [x] 1.2 **RED:** Add failing report tests that specify the exact compact headers, deterministic row ordering/alignment, original status values, reasons excluded from rows, complete reasons under a conditional `Details:` section, and output independence from terminal width.
- [x] 1.3 **GREEN:** Implement the compact formatting helpers required by task 1.1 without changing serialized result data.
- [x] 1.4 **GREEN:** Implement the default compact report and conditional `Details:` section required by task 1.2 while preserving the existing summary and suggestions placement.
- [x] 1.5 **INTROSPECT:** Review the compact renderer against the update-check-reporting spec and remove duplicated formatting logic, implicit dictionary-order coupling, or unnecessary terminal assumptions found in the phase diff.
- [x] 1.6 **VALIDATE:** Run the focused compact-renderer tests and existing text-rendering regression tests; record a passing result with no updated expectation outside the specified text-format change.

## 2. Detailed Report Mode

**Depends on:** Phase 1

**Deliverables:** parsed `check-updates --details` option; full diagnostic text table; unchanged JSON payload, discovery behavior, summaries, suggestions, and exit policies.

- [x] 2.1 **RED:** Add a failing parser test that specifies `--details` as a command-local `check-updates` boolean option with discoverable help text.
- [x] 2.2 **RED:** Add failing rendering tests that require the established `PATH`, `PROVIDER`, `CURRENT`, `CANDIDATE`, `STATUS`, `KIND`, `APPLICABLE`, `PUBLISHED`, and `DETAIL` columns, full paths, and `YYYY-MM-DD HH:MM:SS GMT` publication values under `--details`.
- [x] 2.3 **RED:** Add failing compatibility tests proving that `--details --suggest` preserves suggestions and that `--details` produces the same JSON structure, values, ordering, and policy exit codes as the equivalent command without `--details`.
- [x] 2.4 **GREEN:** Add and propagate the `--details` presentation flag without adding it to serialized result data or provider inputs.
- [x] 2.5 **GREEN:** Select the full diagnostic renderer for detailed text output while retaining the compact renderer as the text default.
- [x] 2.6 **INTROSPECT:** Review argument ownership and rendering selection so `--details` cannot alter discovery, classification, suggestions, JSON serialization, or exit-kind calculation; simplify any duplicated compact/detailed normalization.
- [x] 2.7 **VALIDATE:** Run parser, detailed-renderer, suggestion, JSON-contract, and policy-exit tests and record a passing result.

## 3. Presentation-Neutral Progress Events

**Depends on:** Phase 1

**Deliverables:** optional typed progress event/callback contract; one start event per selected target; unchanged sequential discovery and result semantics when callbacks are present or absent.

- [x] 3.1 **RED:** Add failing coordinator tests requiring one-based index, total after scope and `--only` filtering, full path, and provider in an event emitted immediately before each selected target is resolved.
- [x] 3.2 **RED:** Add failing coordinator tests proving scope and `--only` filters determine the event total/order, provider failures still yield one event and one result, and missing callbacks preserve existing behavior.
- [x] 3.3 **RED:** Add a failing ordering test proving the next provider call does not begin before the previous call returns and final results remain in selected-target order.
- [x] 3.4 **GREEN:** Define the minimal immutable progress event and optional synchronous callback interface required by tasks 3.1–3.3.
- [x] 3.5 **GREEN:** Emit start events from the sequential coordinator after filtering and before target resolution without catching callback failures as provider failures.
- [x] 3.6 **INTROSPECT:** Review the event boundary to ensure it contains no terminal control, rendering, transport state, timing loop, concurrency, or serialized-output fields; remove any such coupling.
- [x] 3.7 **VALIDATE:** Run coordinator progress, filtering, failure, ordering, and existing update-discovery tests and record a passing result.

## 4. Interactive Progress Presentation

**Depends on:** Phase 3

**Deliverables:** transient `Checking updates [N/T] TARGET (PROVIDER)…` stderr renderer; correct TTY/text gating; cleanup on success, handled error, and interruption; no JSON or redirected-output contamination.

- [x] 4.1 **RED:** Add failing facade tests requiring the exact progress content, compact target path, one replaceable stderr line, and event-by-event updates when text output and stderr TTY are active.
- [x] 4.2 **RED:** Add failing facade tests requiring zero progress bytes for non-TTY stderr and for JSON output even when stderr is a TTY.
- [x] 4.3 **RED:** Add failing cleanup tests requiring the transient line to be cleared before final success output, handled diagnostics, and interruption propagation.
- [x] 4.4 **GREEN:** Connect coordinator events to a facade-owned transient stderr renderer only under text-output and stderr-TTY conditions.
- [x] 4.5 **GREEN:** Add idempotent cleanup that clears the transient line on normal completion and in the handled exception/interruption path before other output.
- [x] 4.6 **INTROSPECT:** Review stream ownership, injected TTY probes, cleanup coverage, and test determinism; remove terminal writes from the service, coordinator, providers, and transports if any were introduced.
- [x] 4.7 **VALIDATE:** Run facade progress, cleanup, TTY, JSON, interruption, and output-channel regression tests and record a passing result.

## 5. Integrated Contract and Documentation

**Depends on:** Phase 2 and Phase 4

**Deliverables:** end-to-end CLI coverage for compact, detailed, suggestion, failure, TTY, non-TTY, and JSON modes; updated user documentation/help examples; all repository quality gates passing.

- [x] 5.1 **RED:** Add failing end-to-end acceptance cases for default compact output with a provider failure, `--details --suggest`, interactive sequential progress followed by a clean report, and progress-free redirected JSON.
- [x] 5.2 **GREEN:** Resolve only integration defects exposed by task 5.1 without changing the approved report fields, sequential execution model, JSON contract, or progress gating.
- [ ] 5.3 **GREEN:** Update command documentation and examples to define compact columns, `CURR -> NEXT`, exact path shortening, date-only publication, `Details:`, `--details`, transient progress, and JSON as the machine-readable interface.
- [ ] 5.4 **INTROSPECT:** Trace every requirement and scenario in `specs/update-check-reporting/spec.md` to at least one automated test and every implementation file to a task in this contract; add a missing task before addressing any uncovered scope.
- [ ] 5.5 **VALIDATE:** Run strict OpenSpec validation and record a passing result for `improve-check-updates-output`.
- [ ] 5.6 **VALIDATE:** Run the project typecheck and lint gates and record passing results without suppressions introduced for this change.
- [ ] 5.7 **VALIDATE:** Run the targeted update-check suites and the complete test suite and record passing results.
- [ ] 5.8 **VALIDATE:** Run the project build/package checks and confirm the working-tree diff contains only files required by this contract.
