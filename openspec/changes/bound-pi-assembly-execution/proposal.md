## Why

Host-side Pi assembly can spend an unbounded period inside a silent `npm ci`, making a healthy cold install, a retrying registry request, and a genuinely stuck build indistinguishable. The constructor needs bounded execution, safe interruption, and timely text-mode progress without weakening output redaction or structured-output isolation.

## What Changes

- Expose host-side Pi materialization and npm assembler progress during text-mode builds before the main Docker build starts.
- Bound assembler registry retries, request waits, and total container execution so a stalled install fails predictably.
- Preserve bounded, redacted diagnostics while preventing unbounded subprocess-output buffering.
- Force-remove assembler containers and clean mutable staging after timeout, cancellation, interruption, or failure while preserving the opaque reusable npm download cache and prior published environments.
- Diagnose abandoned same-input staging safely without silently deleting authoritative or shared cache state.

## Capabilities

### New Capabilities

- None.

### Modified Capabilities

- `locked-npm-environment-assembly`: Require bounded Docker-backed assembly execution, deterministic npm network limits, bounded redacted diagnostics, and reliable timeout/interruption cleanup.
- `docker-build-output`: Extend text-mode build visibility to host-side Pi materialization while preserving clean JSON output and existing Docker progress behavior.

## Impact

- Affects npm assembler execution, fixed npm policy identity, Pi build orchestration, CLI progress presentation, subprocess cleanup, and assembler storage lifecycle tests.
- Existing command-line build interfaces remain compatible; failed stalled assemblies become time-bounded and actionable.
- Changing the fixed npm network policy changes assembler identity and may require a fresh assembly while retaining safe reuse of the opaque npm download cache.
