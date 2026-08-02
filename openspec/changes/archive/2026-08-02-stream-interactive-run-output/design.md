## Context

The launcher renders a correct attached `docker run` vector, but its process runner unconditionally uses `capture_output=True`. With default `--tty --interactive`, Docker waits for an interactive session while the facade hides entrypoint output and the shell prompt in pipes. Noninteractive execution needs the opposite behavior because captured stdout/stderr provide actionable JSON and text diagnostics.

This change separates terminal I/O mode from Docker argument construction. Container cleanup after host-sent facade termination belongs to the independent `cleanup-interrupted-container` change and is not designed or implemented here.

## Goals / Non-Goals

**Goals:**

- Stream default interactive Docker sessions through inherited host terminal descriptors.
- Preserve captured execution for `--no-tty --no-interactive`.
- Keep noninteractive diagnostics bounded, UTF-8-safe, explicit about truncation, and available in text and JSON.
- Prevent duplicate rendering of output already streamed interactively.
- Preserve dependency injection and daemon-independent tests.

**Non-Goals:**

- Handling host `SIGTERM`, force-removing orphaned containers, or reaping Docker clients after facade termination; `cleanup-interrupted-container` owns that lifecycle.
- Capturing interactive terminal transcripts as evidence.
- Changing Docker flags, mounts, names, project environment, gateway mapping, or runtime projections.

## Decisions

### Use an explicit execution mode

Represent process behavior as `CAPTURED` or `INTERACTIVE` at the narrow process boundary. The effective run request selects interactive mode when either TTY or stdin-open behavior is enabled; only the fully noninteractive combination selects captured mode.

An explicit mode avoids parsing Docker argv inside the generic process runner and keeps build, verify, doctor, inspection, and evidence execution captured by default.

### Inherit all standard streams interactively

Interactive mode invokes the subprocess with inherited stdin, stdout, and stderr and without output pipes. Its structured `ProcessResult` contains the argv and return code with empty captured streams because output has already reached the terminal.

This preserves prompt visibility, keyboard input, container-local `Ctrl-C`, terminal resizing, and normal Docker attachment behavior.

### Bound captured diagnostics per stream

Captured mode retains `capture_output=True`. Before facade serialization/rendering, bound stdout and stderr independently by a shared UTF-8 byte limit. A truncated value ends with an in-budget marker and carries corresponding structured truncation metadata.

Truncation belongs to presentation diagnostics; verification evidence retains its existing independent redaction, truncation, checksum, and metadata pipeline.

### Make mode observable without duplicating output

Structured run results include `mode: interactive|captured`. Captured results include stdout/stderr. Interactive results omit those fields and human-readable rendering prints only the exit summary, avoiding replay of terminal output.

### Preserve injectable boundaries

Mode-aware process and run executor protocols remain injectable. Tests assert subprocess arguments and stream behavior with fakes; no test allocates a real TTY or invokes Docker.

## Risks / Trade-offs

- **Interactive diagnostics are unavailable after the session** → Output is intentionally streamed, not recorded; portable evidence remains a separate captured verification workflow.
- **Mixed flags are ambiguous** → Either TTY or open stdin selects streaming; tests cover both mixed combinations explicitly.
- **Large captured output consumes memory before presentation truncation** → This change bounds rendered/serialized diagnostics, not subprocess pipe memory; streaming or spool-based capture is outside scope.
- **Facade termination can orphan the container** → Explicitly handled by `cleanup-interrupted-container`, not this change.
