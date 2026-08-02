## 1. RED: Execution-mode contracts

- [x] 1.1 Add daemon-independent process-runner tests for inherited interactive streams and captured noninteractive streams.
- [x] 1.2 Add launcher/facade tests proving default and mixed TTY/stdin flags select interactive mode while `--no-tty --no-interactive` selects captured mode.
- [x] 1.3 Add a timed fake-executor regression proving interactive output reaches the host stream before process completion and is absent from captured `ProcessResult` streams.
- [x] 1.4 Add interactive success, nonzero exit, process-launch error, and no-duplicate-rendering tests.
- [x] 1.5 Add captured text/JSON diagnostics tests for both streams, UTF-8 byte limits, in-budget truncation markers, and explicit truncation metadata.
- [x] 1.6 Add structured-output tests for mode identity, preserved run/container/projection fields, captured stream inclusion, and interactive stream omission.
- [x] 1.7 Run focused tests and confirm they fail only at the intended mode, streaming, and diagnostic boundaries.

## 2. GREEN: Mode-aware execution and diagnostics

- [x] 2.1 Add explicit `CAPTURED` and `INTERACTIVE` modes to the Docker process boundary.
- [x] 2.2 Select interactive mode when either effective TTY or stdin-open behavior is enabled; select captured mode only when both are disabled.
- [x] 2.3 Execute interactive Docker runs with inherited stdin/stdout/stderr and return empty captured streams with the real return code.
- [x] 2.4 Preserve `capture_output=True` behavior for noninteractive execution and keep non-run process users captured by default.
- [x] 2.5 Propagate mode through injectable run/process executor protocols and update daemon-independent fakes.
- [x] 2.6 Add shared UTF-8-safe per-stream diagnostic truncation with an in-budget marker and structured truncation flags.
- [x] 2.7 Add `interactive|captured` mode to structured run results, omit interactive stream fields, and render only captured streams in text mode.
- [x] 2.8 Preserve existing exit classification, run arguments, names, mounts, projection identity/lifecycle, and dry-run purity.
- [x] 2.9 Re-run focused tests until all launcher, facade, acceptance, and run-vector suites pass.

## 3. INTROSPECT: Behavior and scope review

- [x] 3.1 Verify interactive output is visible immediately, input reaches the container, terminal resize/container-local signals behave normally, and output is not duplicated.
- [x] 3.2 Verify captured stdout/stderr remain independently available, bounded by UTF-8 bytes, and explicit about truncation in text/JSON output.
- [x] 3.3 Verify default and both mixed TTY/stdin combinations stream, while the fully noninteractive combination captures.
- [x] 3.4 Verify build, verify, doctor, inspection, and evidence commands remain captured and evidence keeps its independent redaction/checksum pipeline.
- [x] 3.5 Confirm no Docker argv, mounts, project numbering, gateway, ownership, runtime projection, or container lifecycle behavior changed.
- [x] 3.6 Confirm host-sent facade termination and orphan cleanup remain outside scope and are owned exclusively by `cleanup-interrupted-container`.

## 4. VALIDATE: Automated and Docker-host acceptance

- [x] 4.1 Run focused daemon-independent launcher, facade, acceptance, run-vector, and runtime-lifecycle tests.
- [x] 4.2 Run the complete unit suite with `python3 -m unittest discover -s tests -q`.
- [x] 4.3 Run `python3 -m compileall -q docker tests`.
- [x] 4.4 Run `openspec validate stream-interactive-run-output --strict` and `git diff --check`.
- [x] 4.5 On a Docker host, run the default interactive facade and confirm entrypoint output, shell prompt, keyboard input, resize behavior, container-local `Ctrl-C`, and normal `exit` cleanup.
- [x] 4.6 Run `--no-tty --no-interactive` with distinct stdout/stderr and exit 7; confirm captured mode, exact exit code, both streams, and no duplicate output.
- [x] 4.7 Record that SIGTERM/orphan cleanup acceptance is not part of this change and must be completed under `cleanup-interrupted-container`.
