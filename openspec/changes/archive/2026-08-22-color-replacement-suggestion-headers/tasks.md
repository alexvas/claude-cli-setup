# Implementation Contract

Every phase follows RED → GREEN → INTROSPECT → VALIDATE. GREEN work is limited to satisfying that phase's RED evidence; it SHALL preserve plain replacement-fragment construction, the established `--color` contract, and the JSON payload.

Phase dependency DAG:

```text
Phase 1 → Phase 2
```

Later phases depend only on completed earlier phases.

## 1. Isolated Replacement-Header Decoration

**Deliverables:** a CLI-presentation decoration path that can wrap exactly a replacement-fragment visual comment header in SGR 90 followed immediately by reset, with no decoration of its neighbouring text.

- [x] 1.1 **RED:** Add a focused rendering test requiring `# --- <display path> ---` to be wrapped exactly in SGR 90 and an immediate reset when header decoration is enabled; verify the test fails before the implementation.
- [x] 1.2 **RED:** Add a focused rendering test requiring the manual-replacement section label, TOML table headers, and TOML body adjacent to a decorated header to remain free of ANSI sequences; verify the test fails before the implementation.
- [x] 1.3 **GREEN:** Implement presentation-layer decoration of only replacement-fragment visual comment header lines, retaining the plain domain-level fragment text; verify tasks 1.1–1.2 pass.
- [x] 1.4 **INTROSPECT:** Review the decoration boundary for multiple fragments, exact header matching, reset containment, and accidental styling of section labels or TOML content; record any necessary regression assertions in the focused tests.
- [x] 1.5 **VALIDATE:** Run the focused replacement-suggestion rendering tests and verify the Phase 1 deliverable is satisfied without changing fragment construction or JSON serialization.

## 2. Colour-Policy Integration and Output Boundaries

**Depends on:** Phase 1.

**Deliverables:** replacement-header decoration governed by the existing stdout `--color` policy; regression evidence for `auto`, `always`, `never`, non-TTY output, and ANSI-free JSON.

- [x] 2.1 **RED:** Add facade tests requiring SGR 90 header decoration for `check-updates --suggest` under `--color auto` with stdout TTY and under `--color always`; verify both fail before policy integration.
- [x] 2.2 **RED:** Add facade tests requiring plain, ANSI-free replacement headers for `--color never` and for `--color auto` when stdout is not a TTY; verify both fail before policy integration.
- [x] 2.3 **RED:** Add a JSON regression test requiring `check-updates --suggest --output json` to remain ANSI-free and retain the established structured suggestion payload; verify it fails before any required JSON-boundary fix.
- [x] 2.4 **GREEN:** Connect Phase 1 header decoration to the existing stdout colour decision and make all Phase 2 RED evidence pass without changing colour flags, JSON rendering, or plain replacement-fragment construction.
- [x] 2.5 **INTROSPECT:** Audit the complete policy matrix (`auto` TTY/non-TTY, `always`, `never`, and JSON), stdout target selection, and ANSI containment; add focused assertions for any discovered boundary not covered by tasks 2.1–2.3.
- [x] 2.6 **VALIDATE:** Run the focused CLI facade and update-suggestion suites, then the project test command; verify all tests pass and the final output satisfies every scenario in the change delta spec.
