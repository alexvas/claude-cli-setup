## Context

`check_updates()` currently discovers targets sequentially and returns only after every provider call completes. The read-only service serializes structured results, while the CLI facade owns text/JSON rendering. The default text renderer prints nine dynamically sized columns, so repeated path prefixes, full timestamps, and unbounded reasons make ordinary reports excessively wide. Because no lifecycle events escape the coordinator, the facade cannot currently report discovery progress.

The design must preserve the separation between domain discovery and presentation, keep machine output stable, and remain deterministic under tests and redirected execution.

## Goals / Non-Goals

**Goals:**
- Make the default text report compact and predictable without consulting terminal width.
- Preserve full diagnostics through an explicit `check-updates --details` mode.
- Keep reasons readable by separating them from tabular data in compact mode.
- Expose lightweight sequential discovery events so the CLI can display interactive progress on stderr.
- Preserve structured result data, JSON output, ordering, exit behavior, and testability.

**Non-Goals:**
- Parallelizing provider discovery.
- Changing provider, cache, classification, suggestion, or failure-policy behavior.
- Adding a spinner thread, elapsed-time animation, color semantics, or a user-selectable progress mode.
- Reformatting output according to detected terminal width.
- Changing the JSON schema or adding dependencies.

## Decisions

### Use a fixed compact report by default

The default columns are `TARGET`, `PROVIDER`, `CURR -> NEXT`, `STATUS`, and `PUBLISHED`. The report uses the original serialized status rather than inventing a combined result vocabulary. Current and candidate values share the `CURR -> NEXT` column and are rendered as `<current> -> <candidate>`; when candidate is absent or equal to current, the cell is rendered as `<current> -> -`. The existing long-hex abbreviation is retained, including preservation of a `sha256:` prefix. Valid authoritative UTC publication values use `YYYY-MM-DD`; absent or invalid values use `-`.

Only a leading `build.stages.` prefix is removed from compact target names. Other paths remain intact to avoid ambiguous general-purpose shortening. Column widths continue to derive from report contents, but the set of columns and values does not vary with terminal width.

Alternatives considered were truncating arbitrary cells and dynamically dropping columns. Both can hide identity or produce environment-dependent output and were rejected.

The compact `CURR -> NEXT` heading intentionally favors concise user-facing terminology over the internal `current` and `candidate` field names; JSON and detailed output retain the canonical names.

### Move reasons into a details section in compact mode

Rows with a non-empty reason are referenced by compact target name in a `Details:` section after the table. Reasons remain untruncated there. This bounds the table while preserving actionable failures. Suggestion rendering remains after the report and details content.

An alternative was wrapping reasons inside table cells; that complicates alignment and makes scanning less predictable.

### Make `--details` an explicit check-updates presentation option

`--details` selects the established full diagnostic text table: `PATH`, `PROVIDER`, `CURRENT`, `CANDIDATE`, `STATUS`, `KIND`, `APPLICABLE`, `PUBLISHED`, and `DETAIL`. It retains full paths and renders valid authoritative UTC publication timestamps as `YYYY-MM-DD HH:MM:SS GMT`. It does not alter discovery, suggestions, structured data, exit status, or JSON serialization. When JSON output is selected, the flag has no representational effect because JSON already contains the complete structured fields.

A command-local `--details` flag is preferred over a global `--verbose` flag because the requested behavior is report-specific and should not imply broader debug logging semantics.

### Report progress through optional domain events and render it only at the facade

The sequential coordinator accepts an optional progress callback and emits a start event immediately before each selected target is resolved. Each event carries the one-based index, total target count after scope and `--only` filtering, full target path, and provider name. The callback is observational: absence of a callback preserves current behavior, event data is not serialized, and event handling must not change result ordering or classification.

The CLI facade installs a renderer only when output is text and stderr is a TTY. It writes a replaceable stderr line such as:

```text
Checking updates [4/11] toolchain.uv (github-release)…
```

The facade applies the same `build.stages.` shortening for this display. It clears the transient line before emitting final output and on exceptional or interrupted completion. Non-TTY execution and JSON output install no progress renderer and emit no progress bytes.

This keeps terminal control out of providers, transports, and the read-only result contract. Printing permanent lines was rejected because it would make redirected logs noisy; an animated spinner was rejected because it requires timing/concurrency machinery unrelated to discovery.

## Risks / Trade-offs

- **Compact combined values may still be long for unusual versions** → Preserve existing identifier abbreviation and provide `--details`; do not silently truncate semantic versions.
- **Removing `build.stages.` can make a future target collide with another compact path** → Shorten only this exact prefix and retain full paths in details, reasons' source data, and JSON; add collision-oriented rendering tests if inventory shapes expand.
- **Transient terminal output can survive abrupt process termination** → Clear it in normal and exception cleanup paths; hard termination such as `SIGKILL` remains inherently uncleanable.
- **Progress callbacks add an orchestration seam** → Keep the event contract minimal, optional, synchronous, and presentation-neutral.
- **The default text format changes for scripts that parse it** → Treat JSON as the stable machine interface and document text as human-oriented; JSON remains byte-contract compatible at the data level.
