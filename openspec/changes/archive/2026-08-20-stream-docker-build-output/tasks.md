# Implementation Contract

Every checkbox below is required for completion. A phase is complete only when every RED → GREEN → INTROSPECT → VALIDATE task in that phase passes and all listed deliverables exist. GREEN work SHALL be limited to satisfying the phase's RED tests and preserving the invariants named in this contract. Newly discovered scope, changed behavior, or additional dependencies SHALL be added to this contract before implementation continues.

Phase dependency DAG:

```text
Phase 1 ──> Phase 2 ──> Phase 3 ──> Phase 4
```

A phase MAY depend only on the earlier phases named in its `Depends on` line. No task may rely on work assigned to the same or a later phase unless that work is an earlier task within the same phase. Each task SHALL produce one independently reviewable outcome and SHALL NOT absorb another task's deliverable.

## 1. Typed Build Output Contract

**Depends on:** none

**Deliverables:** an explicit typed streamed/captured build-output policy; explicit process-result mode metadata; unchanged immutable Docker build argument vectors; backward-compatible injected executor tests.

- [x] 1.1 **RED:** Add a failing model test requiring the build request to represent exactly the supported streamed and captured output policies with a documented default.
- [x] 1.2 **RED:** Add a failing process-result test requiring callers to distinguish streamed output from captured output without inferring the mode from empty stdout or stderr strings.
- [x] 1.3 **RED:** Add a failing executor-boundary test proving an injected executor still receives the exact immutable Docker argument tuple and no presentation data is inserted into that tuple.
- [x] 1.4 **GREEN:** Implement the minimal typed build-output policy required by task 1.1.
- [x] 1.5 **GREEN:** Implement explicit streamed/captured process-result metadata required by task 1.2 while preserving return code and captured stream fields.
- [x] 1.6 **GREEN:** Propagate the output policy through build orchestration without changing the executor injection contract or rendered Docker vector required by task 1.3.
- [x] 1.7 **INTROSPECT:** Review the phase diff for boolean-mode ambiguity, presentation concerns leaking into command rendering, mutable defaults, or mode inference from stream contents; remove any such coupling.
- [x] 1.8 **VALIDATE:** Run the focused build model, vector, and orchestration boundary tests and record a passing result with byte-for-byte unchanged build vectors for equivalent requests.

## 2. Native Docker Stream Execution

**Depends on:** Phase 1

**Deliverables:** production executor inheritance of host stdout/stderr in streamed mode; retained subprocess capture in captured mode; native `--progress auto|plain|tty` behavior; non-duplicated streamed failure diagnostics; captured failure diagnostics with original Docker return code.

- [x] 2.1 **RED:** Add a failing production-executor test requiring streamed mode to invoke Docker with `shell=False` and inherited stdout/stderr rather than pipes or `capture_output=True`.
- [x] 2.2 **RED:** Add a failing production-executor test requiring captured mode to invoke Docker with `shell=False`, capture both text streams, and preserve their contents and the Docker return code.
- [x] 2.3 **RED:** Add a failing orchestration test requiring a streamed nonzero exit to produce a concise operational failure containing the Docker exit code without replaying stdout or stderr.
- [x] 2.4 **RED:** Add a failing orchestration test requiring a captured nonzero exit to retain the captured Docker diagnostic and original return code.
- [x] 2.5 **RED:** Add a failing parameterized test proving `--progress auto`, `plain`, and `tty` each remain unchanged in the Docker vector in both output policies.
- [x] 2.6 **GREEN:** Implement inherited-stream subprocess execution for streamed mode required by task 2.1.
- [x] 2.7 **GREEN:** Implement captured subprocess execution and explicit captured result construction required by task 2.2.
- [x] 2.8 **GREEN:** Implement mode-aware failure construction required by tasks 2.3 and 2.4 without replaying streamed diagnostics.
- [x] 2.9 **INTROSPECT:** Review subprocess ownership, terminal inheritance, exception mapping, return-code preservation, and stdout/stderr duplication; remove custom buffering, polling, or ANSI handling not required by the RED tests.
- [x] 2.10 **VALIDATE:** Run the focused executor and orchestration suites and record passing streamed-success, captured-success, streamed-failure, captured-failure, and all-progress-mode cases.

## 3. Facade Policy and Final Rendering

**Depends on:** Phase 2

**Deliverables:** text mode selecting streamed execution; JSON mode selecting captured execution; one valid JSON document with captured failure data; concise successful text summary; full build vector retained for dry-run, JSON, and verbose output.

- [x] 3.1 **RED:** Add a failing facade test requiring normal text builds to select streamed execution independently of stdout/stderr TTY detection.
- [x] 3.2 **RED:** Add a failing facade test requiring `--output json` builds to select captured execution and emit exactly one parseable JSON document without interleaved Docker output.
- [x] 3.3 **RED:** Add a failing JSON failure test requiring captured Docker diagnostics and the original Docker return code in the structured operational result.
- [x] 3.4 **RED:** Add a failing text success test requiring a concise image-built summary that does not render the complete Docker build vector as the primary result.
- [x] 3.5 **RED:** Add a failing dry-run test requiring the complete planned Docker build vector and proving Docker is not executed.
- [x] 3.6 **RED:** Add a failing verbose-output test requiring the complete Docker build vector to remain available as diagnostic detail without duplicating streamed Docker output.
- [x] 3.7 **GREEN:** Derive and pass streamed versus captured execution policy from the facade output format as required by tasks 3.1 and 3.2.
- [x] 3.8 **GREEN:** Serialize captured JSON failure diagnostics and Docker return code as required by task 3.3 without changing JSON channel rules.
- [x] 3.9 **GREEN:** Implement the concise executed-build text summary required by task 3.4.
- [x] 3.10 **GREEN:** Preserve complete build-vector rendering for dry-run, JSON, and verbose paths required by tasks 3.5 and 3.6.
- [x] 3.11 **INTROSPECT:** Review result-shape and renderer branching so output format controls presentation only, dry-run remains side-effect free, JSON remains presentation-stable, and streamed output is never re-rendered.
- [x] 3.12 **VALIDATE:** Run focused parser, facade, rendering, JSON-contract, dry-run, verbose, and exit-code tests and record a passing result.

## 4. User-Facing Acceptance and Regression Closure

**Depends on:** Phase 3

**Deliverables:** end-to-end acceptance coverage for visible pre-exit BuildKit progress and output isolation; consistent maintained documentation where behavior is described; a valid OpenSpec change; complete project checks passing.

- [x] 4.1 **RED:** Add a failing acceptance test using a controllable child process that proves text-mode progress becomes observable before process exit.
- [x] 4.2 **RED:** Add a failing acceptance test proving a streamed Docker failure diagnostic appears once and the constructor exits with the established operational exit code.
- [x] 4.3 **RED:** Add a failing acceptance test proving successful and failed JSON builds produce isolated parseable JSON with no streamed child-process bytes.
- [x] 4.4 **GREEN:** Complete only the acceptance wiring required to make tasks 4.1–4.3 pass without introducing a custom progress parser or JSON event protocol.
- [x] 4.5 **GREEN:** Update each maintained README translation that describes build execution so it consistently states that normal builds show native Docker/BuildKit progress; if no existing passage requires a change, record that conclusion instead of adding unrelated documentation.
- [x] 4.6 **INTROSPECT:** Trace one text success, text failure, JSON success, JSON failure, dry run, and verbose build from CLI parsing through executor and final rendering; record and remove any duplicate output, hidden buffering, channel contamination, or undocumented mode inference.
- [x] 4.7 **VALIDATE:** Run the focused acceptance and documentation suites and record a passing result.
- [x] 4.8 **VALIDATE:** Run the complete project test suite and record a passing result with no skipped or weakened regression tests.
- [x] 4.9 **VALIDATE:** Run `openspec validate stream-docker-build-output` and confirm every specification scenario is covered by a passing automated test or an explicitly recorded manual acceptance check.
