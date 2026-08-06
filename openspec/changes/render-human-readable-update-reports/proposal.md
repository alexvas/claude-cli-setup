## Why

`docker-constructor.py check-updates` currently renders its structured result with Python's dictionary representation in text mode. This hides the update summary in implementation detail and means `--suggest` does not provide the reviewable TOML output its interface promises.

## What Changes

- Render `check-updates` text output as a readable, deterministic update report rather than a Python dictionary.
- Summarize current, outdated, skipped, unavailable, and incomplete dependencies while retaining per-dependency status and applicability.
- Render `--suggest` candidates as a clearly separated, copyable TOML fragment after the report.
- Preserve the existing structured JSON output, non-mutating suggestion semantics, filtering, and exit-code behavior.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `docker-build-reproducibility`: Define human-readable update reports and reviewable text suggestions for `check-updates`.

## Impact

- Affected code: `docker/constructor_cli.py`, `docker/versioning/updates.py`, and their focused tests.
- Affected CLI behavior: text-mode output of `docker/docker-constructor.py check-updates`, including `--suggest`.
- JSON output and inventory mutation behavior remain compatible.
