## Why

`docker-constructor.py build` currently captures all `docker build` output, leaving users without feedback during long image builds and making the command appear stalled. The constructor should expose BuildKit progress as it happens while preserving its machine-readable output contract.

## What Changes

- Stream Docker/BuildKit build output to the host terminal in real time for normal text-mode builds.
- Preserve the selected `--progress auto|plain|tty` behavior and Docker's native terminal handling.
- Keep `--output json` machine-readable by capturing Docker output instead of mixing it into the JSON stdout stream.
- Avoid duplicating Docker diagnostics after streamed failures.
- Replace the oversized successful build-vector summary with a concise success result in normal text mode, while retaining the complete vector for dry runs, verbose diagnostics, and structured output.
- Add regression coverage for streamed text builds, captured JSON builds, success and failure behavior, and dry runs.

## Capabilities

### New Capabilities
- `docker-build-output`: Defines real-time build progress, structured-output isolation, failure reporting, and final build summaries.

### Modified Capabilities

None.

## Impact

- Affects the constructor CLI facade, build request/executor boundary, Docker subprocess execution, and result rendering.
- Requires tests around terminal stream inheritance or streaming execution and JSON output integrity.
- Does not change the rendered Docker build vector, Dockerfile contents, image composition, or existing `--progress` values.
