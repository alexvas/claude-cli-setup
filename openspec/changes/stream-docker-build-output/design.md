## Context

The production `SubprocessBuildExecutor` currently calls `subprocess.run(..., capture_output=True)`. BuildKit output is therefore buffered until Docker exits, and successful output is discarded by the facade. The build request already carries the native BuildKit `--progress` choice, while the CLI facade owns the global text/JSON output mode and final rendering.

The design must preserve three boundaries: Docker receives an argument vector with `shell=False`; orchestration remains testable through an injected `BuildExecutor`; and JSON stdout remains a single valid document.

## Goals / Non-Goals

**Goals:**
- Show native Docker/BuildKit progress immediately during ordinary text-mode builds.
- Preserve Docker's TTY detection, colors, and `--progress` behavior.
- Keep JSON output isolated and machine-readable.
- Retain useful captured diagnostics when output is not streamed.
- Produce a concise final text status without repeating streamed output or the full build vector.

**Non-Goals:**
- Implement a custom progress UI or parse BuildKit output.
- Change Docker build arguments, image contents, caching, or progress modes.
- Stream output in JSON mode or define a JSON event protocol.
- Add an external subprocess or terminal-handling dependency.

## Decisions

### Select execution output policy at the CLI boundary

The facade will derive a build execution output policy from the global output format and pass it through the typed build request to the production executor. Text mode selects `streamed`; JSON mode selects `captured`. Dry runs execute no subprocess and are unaffected.

This is preferred over detecting `isatty()` because non-TTY text consumers can still benefit from incremental plain output, and output format—not terminal presence—is what determines whether stdout must remain structurally isolated.

### Use inherited process streams for text mode

In streamed mode, Docker will inherit the constructor process's stdout and stderr rather than being piped through Python. This preserves BuildKit's native terminal behavior and avoids deadlocks, buffering delays, thread management, and ANSI corruption associated with a custom `Popen` tee implementation.

The returned process result will identify streamed execution and retain the exit code, but it will not pretend to contain captured stdout/stderr. On failure, orchestration will report a concise exit-code message because Docker has already emitted its diagnostic.

### Retain capture for structured mode

In captured mode, the executor will continue to collect stdout and stderr. This prevents Docker output from contaminating JSON stdout and allows failure details to be represented in the final structured result. Captured output must not be replayed to the terminal before rendering.

### Separate final summaries from diagnostic build vectors

Normal successful text execution will render a concise image-built result. It will not print the complete build command after Docker has finished. The complete argument vector remains available in dry-run output, JSON data, and verbose diagnostics so automation and troubleshooting do not lose information.

The facade/result model will explicitly distinguish an executed streamed build, an executed captured build, and a dry-run plan rather than inferring behavior from empty stream strings.

### Preserve the executor injection boundary

Tests and callers that inject a `BuildExecutor` will continue to receive the exact immutable build argument tuple. Output policy will be configuration on the production executor or an explicit execution field with a backward-compatible default, rather than changing fake runners into terminal abstractions.

## Risks / Trade-offs

- **[Streamed output cannot be included retrospectively in an error payload]** → Docker diagnostics are already visible; retain exit code and clearly mark the result as streamed.
- **[Redirected text output can interleave stdout and stderr]** → This matches direct `docker build` semantics and avoids imposing artificial ordering.
- **[JSON builds remain silent while running]** → Preserve strict single-document JSON; a future event-stream format would require a separate capability.
- **[Concise summaries could hide a command users currently inspect]** → Keep the vector in dry-run, JSON, and verbose output.
- **[Tests that redirect Python streams may not model OS-level inheritance]** → Test executor configuration and subprocess arguments at the boundary, with a focused integration test where practical.
