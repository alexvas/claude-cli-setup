## 1. Inventory model and constraint engine — no Docker

This stage has no dependencies and produces the validated in-memory configuration model used by every later stage.

- [x] 1.1 **RED:** Add fixture-driven tests for required cache-scope sections, exact selected versions, source metadata, platform artifacts, SHA-256 digests, and override policy
- [x] 1.2 **RED:** Add tests for `==`, `>`, `>=`, `<`, `<=`, compound AND bounds, boundaries, exact-default selection, and rejection of wildcards, OR, incomplete versions, empty clauses, forbidden prereleases, and contradictory constraints
- [x] 1.3 **GREEN:** Add `versions.toml` with current values grouped under base, toolchain, prebuilt-tool, Node-tool, runtime, and Pi-extension scopes
- [x] 1.4 **GREEN:** Implement dependency-free inventory loading plus numeric `X.Y.Z` constraint parsing/evaluation with no tool-specific minimum constants
- [x] 1.5 **GREEN:** Implement local schema, digest, platform, URL/version consistency, override-policy, and constraint-consistency validation
- [x] 1.6 **INTROSPECT:** Trace every parsed value back to its TOML path and inspect normalized defaults, constraints, artifacts, and validation errors
- [x] 1.7 **VALIDATE:** Run the complete inventory/constraint unit suite and record all Stage 1 fixtures passing without Docker or network access

## 1A. Complete entry provenance and modularize the resolver — depends on Stage 1, blocks Stages 2 and 3, no Docker

This corrective stage applies the complete-entry contract adopted after the initial Stage 1 implementation and establishes module boundaries before CLI and provider work expand the resolver.

- [x] 1A.1 **RED:** Add tests requiring `uv-python` source/update metadata for CPython, PyPI metadata for `ty`, npm metadata without duplicated package fields for every Pi extension, retention of all declared entries, rejection of unknown paths, and direct-script/package import parity
- [x] 1A.2 **GREEN:** Split the resolver into the documented `docker/versioning/` modules, keep `docker/versions.py` as a thin stable entry point, and model Python, `ty`, and Pi extensions as complete typed entries with provider-specific validation
- [x] 1A.3 **INTROSPECT:** Trace every independently selected inventory value through its typed entry and owning module; inspect the import graph for cycles, confirm no catch-all attribute access, and compare direct-script with imported behavior
- [x] 1A.4 **VALIDATE:** Run decomposed constraint, inventory, import-boundary, and real-inventory tests offline; record byte-identical behavior where retained and strict OpenSpec validation

## 2. Effective configuration CLI — depends on Stage 1A, no Docker

This stage exposes deterministic defaults and controlled overrides without integrating any build system.

- [x] 2.1 **RED:** Add subprocess-level CLI tests for `validate`, `get`, and `env`, including text/JSON output, unknown paths, malformed overrides, and actionable exit codes
- [x] 2.2 **RED:** Add tests proving a supported override changes both emitted build arguments and effective inventory while an ordinary invocation keeps the exact selected default
- [x] 2.3 **GREEN:** Implement `docker/versions.py validate`, `get`, and `env` over one validated effective configuration
- [x] 2.4 **GREEN:** Implement supported override application and deterministic serialization of the effective inventory
- [x] 2.5 **INTROSPECT:** Compare default and Python-override effective inventories field-by-field with emitted environment values and inspect stable ordering/diagnostics
- [x] 2.6 **VALIDATE:** Run CLI tests under a sanitized environment and confirm identical input produces byte-identical local output without Docker or network access

## 3. Update discovery and non-mutating suggestions — depends on Stage 1A, no Docker

This stage consumes inventory provider metadata but is independent of build integration and can proceed in parallel with Stage 2 after Stage 1A.

- [ ] 3.1 **RED:** Add deterministic adapter-level tests for npm, GitHub Releases, PyPI, uv-managed Python, Rust stable channel, Docker Registry, and immutable git refs, plus coordinator tests that do not depend on provider transport details
- [ ] 3.2 **RED:** Add tests for stable-only filtering, current/outdated/skipped/unavailable/incomplete states, Docker digest refresh classification, git revision updates, strict mode, and fail-on-outdated exit codes
- [ ] 3.3 **RED:** Add `--suggest` tests requiring candidate version, URL, and digest output while hashing the working tree before/after to prove non-mutation
- [ ] 3.4 **GREEN:** Implement provider adapters and best-effort `check-updates` with table/JSON output, filters, optional tokens/cache TTL, strict mode, and fail-on-outdated behavior
- [ ] 3.5 **GREEN:** Implement architecture/checksum applicability checks and non-mutating `check-updates --suggest`
- [ ] 3.6 **INTROSPECT:** Inspect representative provider reports and suggestions, including incomplete releases that must not be presented as directly applicable
- [ ] 3.7 **VALIDATE:** Run decomposed provider-adapter and update-coordinator tests offline with injected fake transports and confirm ordinary inventory commands make zero provider requests

## 4. Build argument rendering and orchestration — depends on Stage 2, no Docker daemon

This stage defines the boundary between effective configuration and Compose/build-wrapper execution. Tests mock process execution; a Docker daemon is not required.

- [ ] 4.1 **RED:** Add tests for required Compose argument rendering, `NODE_BASE_IMAGE=<tag>@<digest>`, effective-inventory build input, argument quoting, and missing-value failures
- [ ] 4.2 **RED:** Add mocked-subprocess tests proving the canonical `compose` command and `docker/build_wrapper.py` receive the same validated values and propagate failures
- [ ] 4.3 **GREEN:** Implement canonical `versions.py compose` process orchestration and low-level environment export
- [ ] 4.4 **GREEN:** Integrate `docker/build_wrapper.py` with the resolver without maintaining a second mapping of selected values
- [ ] 4.5 **GREEN:** Generate the effective inventory input that the Docker build will copy into the runtime image
- [ ] 4.6 **INTROSPECT:** Inspect rendered commands/environments for default and override builds and map each argument to one inventory path
- [ ] 4.7 **VALIDATE:** Run orchestration tests with mocked Docker/Compose executables and confirm no Docker daemon or network is contacted

## 5. Migrate semantic source files — depends on Stage 4, no Docker daemon

This stage removes duplicated constants and rewires source files. Static and shell-level tests provide the primary feedback.

- [ ] 5.1 **RED:** Add semantic-source tests that reject selected version/revision/URL/digest defaults outside `versions.toml`, allowing only explicit test fixtures and generated effective inventory
- [ ] 5.2 **RED:** Add source-contract tests requiring value-free Dockerfile `ARG` declarations, required Compose interpolation, inventory-backed runtime/extension scripts, and canonical documentation commands
- [ ] 5.3 **GREEN:** Remove concrete defaults from Dockerfile, Compose, runtime verification, extension setup, environment templates, and direct-build documentation
- [ ] 5.4 **GREEN:** Resolve the Node base before `FROM`; pin/verify remaining Rust/rustup and uv inputs; preserve exact Pi, OpenSpec, ty, oh-my-zsh, and direct Python behavior
- [ ] 5.5 **GREEN:** Copy the effective inventory as root-owned read-only runtime content and make `verify-runtime.sh` plus `install-pi-extensions.sh` query it
- [ ] 5.6 **INTROSPECT:** Search all semantic source paths for duplicate constants, inspect Docker stage/cache ownership of every argument, and review shell quoting and failure paths
- [ ] 5.7 **VALIDATE:** Run static source-contract tests, Python unit tests, shell syntax checks, Compose configuration rendering if the CLI is available, `git diff --check`, and strict OpenSpec validation without requiring a daemon

## 6. Docker image integration — depends on Stage 5, requires a Docker host

This is the only implementation stage that requires Docker. It validates the already-tested local configuration and source integration against real images.

- [ ] 6.1 **RED:** Add a host-side acceptance script that checks effective inventory ownership/mode, installed-version equality, direct Python behavior, checksum rejection, and runtime extension pins; demonstrate it rejects the pre-migration image or a deliberately mismatched fixture image
- [ ] 6.2 **GREEN:** Build the default image through `versions.py compose` and fix only Docker-specific integration failures until the acceptance script and `verify-runtime.sh` pass
- [ ] 6.3 **GREEN:** Build one supported stable Python override and confirm the effective inventory and direct `python`/`python3` report the requested exact version
- [ ] 6.4 **INTROSPECT:** Compare image inventory with installed Node, Rust/Cargo, rustfmt/clippy, uv, Python, ty, Pi, OpenSpec, rtk, fd, and Pi extension metadata
- [ ] 6.5 **INTROSPECT:** Change one inventory node at a time and inspect plain BuildKit output to confirm only dependent stages invalidate
- [ ] 6.6 **VALIDATE:** Run clean default/custom UID-GID builds, checksum/digest negative tests, Python prerelease/old-version rejection, runtime smoke checks, and record Docker-host evidence

## 7. User workflow and release validation — depends on Stages 3 and 6; documentation checks need no Docker

This final stage joins update discovery with the proven build workflow and makes the supported interface reviewable.

- [ ] 7.1 **RED:** Add documentation/source consistency tests requiring canonical build commands, inventory paths, override grammar, update-check semantics, `--suggest` non-mutation, and reproducibility boundaries
- [ ] 7.2 **GREEN:** Update maintained documentation for canonical builds, low-level env export, inventory editing, controlled overrides, provider checks, suggestions, refresh review, and completed focused-change ownership
- [ ] 7.3 **INTROSPECT:** Run a live best-effort update check, manually review at least one suggestion against its upstream artifact/checksum source, and confirm normal build/launch/setup paths make no update-provider requests
- [ ] 7.4 **VALIDATE:** Run all local suites first, then available project checks and recorded Docker acceptance evidence; finish with `openspec validate --all --strict --no-interactive` and `git diff --check`
