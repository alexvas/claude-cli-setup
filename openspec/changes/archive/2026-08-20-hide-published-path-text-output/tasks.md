# Implementation Contract

Every checkbox is required for completion. Each phase is complete only when its RED → GREEN → INTROSPECT → VALIDATE sequence passes and its deliverables exist. GREEN work SHALL be limited to satisfying that phase's RED tests without changing projection publication or unrelated command output.

Phase dependency DAG:

```text
Phase 1 ──> Phase 2
```

A phase MAY depend only on the earlier phases named in its `Depends on` line.

## 1. Output-Mode Metadata Selection

**Depends on:** none

**Deliverables:** focused facade tests for normal text, verbose text, and JSON; conditional `published_path` result assembly; unchanged projection publication.

- [x] 1.1 **RED:** Add a failing facade test proving a successful normal text build omits both the `published_path` key and projection filesystem path while the publish result remains present internally.
- [x] 1.2 **RED:** Add a failing facade test proving a successful verbose text build includes the `published_path` key and projection filesystem path.
- [x] 1.3 **RED:** Add a failing facade test proving a successful JSON build retains `data.published_path` with the exact projection filesystem path.
- [x] 1.4 **GREEN:** Gate facade assembly of `published_path` data so it is included only for JSON or verbose output, satisfying tasks 1.1–1.3 without changing orchestration.
- [x] 1.5 **INTROSPECT:** Review the phase diff to ensure the policy remains at the facade boundary, generic rendering is unchanged, and no output mode alters whether or where the projection is published.
- [x] 1.6 **VALIDATE:** Run the focused facade and build-output rendering tests and record a passing result for all three output modes.

## 2. Integration and Regression Closure

**Depends on:** Phase 1

**Deliverables:** end-to-end output coverage; preserved JSON compatibility; validated OpenSpec artifacts; complete project regression suite passing.

- [x] 2.1 **RED:** Add an end-to-end regression test proving a real successful text-mode constructor invocation publishes the effective projection but does not print its path.
- [x] 2.2 **RED:** Add an end-to-end regression test proving equivalent verbose text and JSON invocations expose the exact published path.
- [x] 2.3 **GREEN:** Complete only the integration wiring needed for tasks 2.1–2.2, without changing projection contents, location, lifecycle, or Docker execution.
- [x] 2.4 **INTROSPECT:** Trace normal text, verbose text, and JSON success results from orchestration through rendering and remove any duplicate metadata, mode-specific side effect, or accidental suppression of other result fields.
- [x] 2.5 **VALIDATE:** Run focused end-to-end build-output tests and confirm JSON field names and values remain backward-compatible.
- [x] 2.6 **VALIDATE:** Run the complete project test suite with no skipped or weakened regressions.
- [x] 2.7 **VALIDATE:** Run `openspec validate hide-published-path-text-output` and confirm every specification scenario has passing automated coverage.
