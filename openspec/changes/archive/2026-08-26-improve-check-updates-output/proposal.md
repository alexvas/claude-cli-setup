## Why

The human-readable `check-updates` report is too wide to scan comfortably because it always renders nine dynamically sized columns, including long paths, timestamps, and error details. Network discovery also provides no feedback while sequential provider requests are running, making the command appear stalled.

## What Changes

- Replace the default text report with a compact, deterministic table containing target, provider, combined current-to-candidate value, original status, and publication date.
- Shorten only the `build.stages.` target prefix in the default report and render publication timestamps as dates.
- Move provider errors and explanatory reasons out of the table into a separate details section.
- Add a `check-updates --details` mode that preserves the established nine-column diagnostic report, including full paths and `YYYY-MM-DD HH:MM:SS GMT` publication timestamps.
- Show per-target progress while sequential network discovery runs in an interactive text session, using stderr without contaminating the final stdout report.
- Keep JSON output and its structured contract unchanged, suppress progress for JSON and non-interactive execution, and avoid terminal-width-dependent formatting.

## Capabilities

### New Capabilities
- `update-check-reporting`: Human-readable compact and detailed update reports plus interactive discovery progress behavior.

### Modified Capabilities
- `docker-build-reproducibility`: Updates the existing `check-updates` text-report contract to delegate compact, detailed, and progress presentation behavior to `update-check-reporting`, while preserving discovery, applicability, suggestion, JSON, and exit-policy semantics.

## Impact

- Affects `check-updates` argument parsing, read-only update orchestration, and text rendering in `docker/constructor_cli.py` and `docker/versioning/`.
- Requires deterministic rendering, progress-channel, TTY, JSON-compatibility, failure-cleanup, and CLI acceptance tests.
- Does not change provider discovery semantics, sequential execution, update classification, JSON fields, exit policy, or external dependencies.
