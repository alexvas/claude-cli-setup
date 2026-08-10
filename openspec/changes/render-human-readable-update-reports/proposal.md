## Why

`docker-constructor.py check-updates` currently renders its structured result with Python's dictionary representation in text mode. This hides the update summary in implementation detail and means `--suggest` does not provide the reviewable TOML output its interface promises.

## What Changes

- Render `check-updates` text output as a readable, deterministic update report rather than a Python dictionary.
- Summarize current, outdated, skipped, unavailable, and incomplete dependencies while retaining per-dependency status and applicability.
- Render `--suggest` candidates as a clearly separated, copyable TOML fragment after the report.
- Compact long revision, digest, and checksum identifiers in the human-readable table; retain full machine-readable and copyable values.
- Report the authoritative release/version publication time when a provider supplies one, and show an explicit unknown marker when it does not.
- Preserve the structured JSON contract and existing non-mutating suggestion semantics, filtering, and exit-code behavior.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `docker-build-reproducibility`: Define human-readable update reports and reviewable text suggestions for `check-updates`.

## Impact

- Affected code: `docker/constructor_cli.py`, update result/provider models and adapters, and their focused tests.
- Affected CLI behavior: text-mode output of `docker/docker-constructor.py check-updates`, including `--suggest`.
- JSON retains full identifiers and gains publication time only as an additive optional field; inventory mutation behavior remains unchanged.
