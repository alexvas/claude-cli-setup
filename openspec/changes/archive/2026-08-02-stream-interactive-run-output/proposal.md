## Why

The default interactive `docker-constructor.py run` attaches stdin but currently captures Docker stdout and stderr, leaving users with an apparently hung terminal and an invisible container prompt. Interactive launches must inherit terminal streams, while explicitly noninteractive launches must continue capturing bounded diagnostics.

## What Changes

- Introduce explicit captured and interactive execution modes at the Docker process boundary.
- Stream stdin, stdout, and stderr directly for launches using TTY or interactive stdin.
- Preserve captured stdout/stderr for `--no-tty --no-interactive`, including bounded UTF-8 diagnostics and explicit truncation metadata.
- Distinguish interactive and captured execution in structured facade output and avoid replaying output already streamed to the terminal.
- Preserve existing Docker arguments, mounts, projection lifecycle, project numbering, and verification/evidence behavior.
- Exclude facade-termination container cleanup from this change. SIGTERM cleanup and orphan prevention are owned by the separate `cleanup-interrupted-container` change.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `project-launcher`: Define terminal stream behavior and diagnostics for interactive versus captured direct Docker launches.

## Impact

- Affects `docker/launcher.py`, `docker/constructor_cli.py`, process execution protocols, facade rendering, and daemon-independent launcher/acceptance tests.
- Does not add external dependencies or require Docker in unit tests.
- Does not handle containers left behind when the facade receives host `SIGTERM`; that work is explicitly delegated to `cleanup-interrupted-container`.
