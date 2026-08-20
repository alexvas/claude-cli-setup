## Why

A successful text-mode build currently appends the internal effective-projection path as `data: {'published_path': ...}`, adding implementation detail to the user-facing success message. Normal output should stay concise while structured and diagnostic modes retain the path when it is useful.

## What Changes

- Omit `published_path` from normal text-mode build results.
- Preserve `published_path` in JSON output for automation.
- Preserve `published_path` in verbose text output for diagnostics.
- Keep effective-projection publication behavior unchanged; only its presentation changes.

## Capabilities

### New Capabilities
- `build-result-presentation`: Defines visibility of internal build metadata across normal text, verbose text, and JSON output.

### Modified Capabilities

None.

## Impact

- Affects build-result assembly in `docker/constructor_cli.py` and facade/output regression tests.
- Does not change projection generation, publication paths, Docker execution, exit codes, or JSON field names.
