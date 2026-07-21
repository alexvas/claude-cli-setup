## 1. Define explicit Python inputs

- [x] 1.1 Add an exact `PYTHON_VERSION=3.14.6` default to Compose and pass it into the Docker build
- [x] 1.2 Scope the Python build argument immediately before its first consumer and reject versions older than 3.14.6 with a clear error

## 2. Install and expose direct Python executables

- [x] 2.1 Explicitly install the configured uv-managed Python as the default before installing Python-backed uv tools
- [x] 2.2 Make Python-backed uv tool installation select the configured Python version rather than resolving an implicit default
- [x] 2.3 Remove the `/usr/local/bin/python3` `uv run` wrapper and the `python3` and `pip` shell aliases
- [x] 2.4 Verify during the build that `python` and `python3` directly execute the configured managed interpreter and report the requested version

## 3. Update runtime verification and documentation

- [x] 3.1 Extend runtime smoke checks to invoke direct Python from project and non-project directories without creating or synchronizing a project environment
- [x] 3.2 Verify that no project-owned `python3` or `pip` alias remains and that package-management examples use explicit `uv pip` subcommands
- [x] 3.3 Update the Russian, English, and Chinese README files with the Python version input, direct-executable behavior, and absence of a standalone pip interface
- [x] 3.4 Reconcile overlapping Python inventory and installation tasks in `pin-docker-toolchain-versions` so the broader change preserves this runtime contract

## 4. Verify on a Docker host

- [x] 4.1 Perform a clean build with the default and confirm direct CPython 3.14.6 execution as user `dev`
- [x] 4.2 Build with one available version newer than 3.14.6 and confirm the override is installed and used by Python-backed uv tools
- [x] 4.3 Attempt an override older than 3.14.6 and confirm the build fails before tool installation
- [x] 4.4 Run concurrent `python3` invocations in a project directory and confirm they neither execute `uv run` nor contend on uv project synchronization
