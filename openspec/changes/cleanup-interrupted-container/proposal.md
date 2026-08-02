## Why

Sending `SIGTERM` to a running `docker-constructor.py run` facade terminates the facade but can leave its named Docker container running. Because `--rm` removes a container only after that container exits, facade termination must trigger explicit cleanup of the exact container owned by that launch.

## What Changes

- Define facade-termination semantics for direct interactive Docker launches.
- Handle host-sent `SIGTERM` long enough to force-remove the container allocated by the active launch and reap the attached Docker client.
- Preserve conventional SIGTERM exit status 143 even if best-effort cleanup fails.
- Keep the runtime projection available until container termination is attempted, then remove it on every termination path.
- Preserve normal terminal `Ctrl-C` behavior inside the interactive container; it continues to affect the foreground application in the container rather than terminating the facade.
- Add daemon-independent tests using injected signal, execution, and cleanup boundaries, plus Docker-host SIGTERM acceptance checks.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `project-launcher`: Require a SIGTERM-terminated facade to terminate only its owned container and clean its ephemeral runtime projection without orphaning a `pi-N` container.

## Impact

- Affects `docker/launcher.py`, launcher/facade signal wiring, process execution boundaries, and launcher lifecycle tests.
- Adds narrow injectable signal and Docker container-cleanup operations; no Docker daemon is required by unit tests.
- Does not change container-side `Ctrl-C`, Docker run arguments, project mounts, naming allocation, gateway behavior, or normal successful/nonzero execution semantics.
