## Why

The supported version-management interface is repeatedly invoked as `python3 docker/versions.py`, even though it is a user-facing command alongside already-executable project scripts. A direct executable interface makes build and update workflows shorter and visually consistent.

## What Changes

- Make `docker/versions.py` directly executable with a portable Python shebang and executable file mode.
- Preserve `python3 docker/versions.py` compatibility, package imports, exit codes, and deterministic behavior.
- Use `./docker/versions.py` as the canonical documented command form.
- Add source/permission and direct-execution parity tests.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `docker-build-reproducibility`: Define direct executable invocation as the canonical resolver interface while preserving Python-interpreter invocation compatibility.

## Impact

- `docker/versions.py` file header and mode.
- Resolver subprocess tests, semantic-source/documentation consistency tests, `.env.example`, maintained README translations, and internal usage examples.
- No dependency or inventory format changes.
