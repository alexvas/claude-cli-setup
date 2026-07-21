## Context

The base stage currently creates `/usr/local/bin/python3` as a wrapper that executes `uv run python` and advertises shell aliases for `python3` and `pip`. `uv run` is project-aware: it can discover project configuration, select or download an interpreter, create an environment, and synchronize dependencies before executing Python. Multiple consumers can therefore start concurrent uv operations, and the result depends on the working directory.

The image already installs uv and copies `/home/dev/.local` from the toolchain stage into the runtime. A uv-managed CPython 3.14.6 is currently present only as an incidental consequence of other uv operations, notably tool installation; Python is not an explicit build input.

## Goals / Non-Goals

**Goals:**
- Make `python` and `python3` direct, predictable interpreter commands independent of project discovery.
- Install exactly CPython 3.14.6 by default and support deliberate overrides to 3.14.6 or newer.
- Prevent ordinary Python invocation from initiating `uv run`, environment synchronization, or runtime downloads.
- Keep uv as the Python distribution and package-management mechanism.
- Preserve cache-friendly placement of the Python version argument near its first consumer.

**Non-Goals:**
- Provide a standalone `pip` command or emulate pip through aliases.
- Create a global mutable Python package environment.
- Replace uv with Debian Python, pyenv, or a source build.
- Fold the broader pinning of uv and all other tools into this urgent change.

## Decisions

### Install an exact uv-managed Python during the toolchain build

Introduce a `PYTHON_VERSION` build argument with an exact Compose default of `3.14.6`. After uv is available, explicitly install that version as the uv-managed default. Validate that an override is not lower than 3.14.6 and fail the build with a clear message otherwise.

An exact default is preferred over `3.14`, `>=3.14.6`, or implicit uv selection because those forms can resolve differently over time. Overrides remain possible for deliberate testing and upgrades.

### Expose uv-created direct executables

Rely on the installed runtime's `python` and `python3` executables under `/home/dev/.local/bin`, which already precedes `/usr/local/bin` on `PATH` and is copied into the runtime image. Remove the `/usr/local/bin/python3` `uv run` wrapper and the `python3` shell alias.

Direct executables are preferred over a wrapper with `uv run --no-project` because even a restricted `uv run` retains unnecessary resolver and launcher behavior. A fixed architecture-specific symlink into uv's internal installation directory is also avoided because uv owns that layout.

### Keep package operations explicit through uv

Remove the `pip='uv pip --system'` alias and do not promise a `pip` or `pip3` executable. Documentation will use complete uv commands such as `uv pip install ...`, including an explicit target environment or interpreter where needed.

This avoids pretending that the `uv pip` command family is a drop-in pip executable and avoids modifying the managed base interpreter merely to add pip compatibility.

### Pin Python selection for Python-backed uv tools

Any uv tool installation that needs Python, including `ty`, should receive the configured Python selection explicitly rather than choosing or downloading an unrelated default. Python installation must occur before such tool installation.

### Verify behavior in project and non-project directories

Build/runtime checks will verify the configured version, confirm that `sys.executable` identifies the managed interpreter, and invoke `python3` from a directory containing project metadata without creating or synchronizing a project environment. Checks will also confirm that no project-owned shell alias named `python3` or `pip` remains.

## Risks / Trade-offs

- [A future uv release changes its managed executable layout or `--default` behavior] → Assert command resolution and `sys.executable` during every image build.
- [A requested override is newer but unavailable from uv for the target architecture] → Fail during the explicit installation instead of deferring failure to runtime.
- [Existing users call `pip` directly] → Document the intentional removal and provide `uv pip install ...` migration examples.
- [The broader pinning change also edits uv/Python installation] → Treat this change's direct-Python runtime contract and minimum version as authoritative, then reconcile duplicate tasks before applying the broader change.
- [Changing Python invalidates Python-backed tool layers] → Scope `PYTHON_VERSION` immediately before Python installation; invalidation of genuinely Python-dependent tools is expected.

## Migration Plan

1. Add the exact Python default and explicit installation before Python-backed uv tools.
2. Remove the wrapper and aliases in the same image revision so no mixed behavior is shipped.
3. Update smoke checks and documentation, then perform a clean Docker-host build.
4. Roll back the image revision if the managed runtime is unavailable; do not restore `uv run python` as an implicit runtime fallback.

## Open Questions

- The exact uv version and artifact verification remain owned by `pin-docker-toolchain-versions`; its implementation must preserve this change's explicit Python installation order.
