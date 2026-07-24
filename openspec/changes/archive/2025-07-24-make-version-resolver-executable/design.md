## Context

`docker/versions.py` is the stable user-facing wrapper but currently has mode `0664` and no shebang. Other user-facing project scripts, including `launch-pi.py` and `docker/build_wrapper.py`, are executable. Documentation therefore repeats an interpreter prefix that obscures the command itself.

## Goals / Non-Goals

**Goals:**
- Support `./docker/versions.py` on Unix-like development hosts.
- Preserve all existing interpreter and import entry points.
- Move maintained user documentation to the shorter direct form.

**Non-Goals:**
- Rename the command or add a top-level facade.
- Change subcommands, options, output, or exit codes.
- Add a packaging/install step or Windows executable wrapper.

## Decisions

### Use an env-based Python 3 shebang

The wrapper will start with `#!/usr/bin/env python3` and remain standard-library-only. This matches existing project scripts and selects the host's configured Python 3 without hard-coding an absolute interpreter path.

Rejected alternative: `#!/usr/bin/python3`, which is less portable across supported hosts.

### Preserve both invocation forms

Direct execution becomes canonical in user documentation, while `python3 docker/versions.py` remains supported for automation and environments that ignore Unix executable metadata. Both routes enter the same `main()` implementation.

### Verify Git mode and behavior parity

Tests will inspect both the shebang and executable mode and run representative commands through direct and interpreter invocation, comparing output and exit status. Existing import-boundary tests remain authoritative for package behavior.

## Risks / Trade-offs

- [Executable mode can be lost on non-POSIX filesystems] → Test Git index mode and retain interpreter invocation compatibility.
- [`env` resolves an unexpected Python] → Resolver runtime requirements and clear syntax errors remain visible; no virtual-environment activation is performed implicitly.
- [Documentation changes race with README restructuring] → Keep this change's documentation edits mechanical; the sibling README change owns information architecture.

## Migration Plan

1. Add direct-execution and file-mode tests.
2. Add the shebang and Git executable bit.
3. Update command references without changing semantics.
4. Run direct/interpreter parity and full resolver suites.

## Open Questions

None.
