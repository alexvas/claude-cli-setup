## Context

The repository has one image and one runtime container, while orchestration is split among `docker/versions.py compose`, two static Compose files, optional/project-generated fragments, `launch-pi.py`, and `docker/build_wrapper.py`. Python already owns inventory validation, effective build inputs, project selection, gateway probing, and rootless setup; Compose mainly translates those computed values into Docker arguments and forces additional command/file-selection logic.

## Goals / Non-Goals

**Goals:**
- Establish `docker/docker-constructor.py` as the sole public CLI facade for build, run, update discovery, inspection, diagnosis, and verification.
- Launch sessions through an explicit, inspectable `docker run` argument vector.
- Keep all domain behavior behind reusable internal APIs and keep argument parsing, prompts, presentation, and exit-code mapping in the facade.
- Derive separate effective build and runtime projections from one reviewed inventory so runtime receives only minimal installation and validation metadata.
- Preserve image identity, build arguments, mounts, working directory, runtime environment, TTY, entrypoint behavior, and host connectivity.
- Remove Compose and `build_wrapper.py` without duplicating orchestration logic.

**Non-Goals:**
- Change Dockerfile stages, selected tool versions, image contents, or cache boundaries.
- Change project selection UX or ownership-repair policy.
- Generalize the project into a multi-container orchestrator.
- Remove the rootless systemd override or the standalone helper script that installs it.
- Resolve dynamic versus immutable host settings or remove dotenv operational configuration; that decision is deferred.

## Decisions

### Make `docker-constructor.py` the sole public CLI facade

`docker/docker-constructor.py` exposes primary commands `build`, `run`, and `check-updates`, plus auxiliary commands `validate`, `show`, `doctor`, and `verify`. A public `schema` command is explicitly deferred. The facade parses command-specific and global flags, performs user-input validation, coordinates confirmations, renders user-facing output, and maps domain errors to process exit codes. It SHALL NOT implement inventory traversal, Docker argument rendering, gateway probing, project selection, provider calls, image checks, or evidence collection.

`build` delegates the complete transaction—validated reviewed inventory, effective build projection, gateway diagnosis/persistence, command rendering, and direct Docker execution—to internal APIs. `run` delegates runtime projection generation, project selection, and direct runtime orchestration. `check-updates`, `validate`, `show`, `doctor`, and `verify` similarly call focused APIs; verification rules remain internal and the facade only selects checks and presents results. Existing `docker/versions.py`, `launch-pi.py`, verification executables, and wrapper scripts cease to be supported user entry points.

The facade supports a global reviewed-inventory path, output format, verbosity, and color control plus command-owned flags. `build` owns build overrides, platform, image tag, cache/pull/progress, rootless consent, confirmation, and dry-run flags. `run` owns runtime overrides, explicit/main/additional project selection, image/name, TTY, ownership policy, dry-run, and command passthrough. `check-updates`, `validate`, and `show` accept `--scope build|runtime|all`; update checks retain provider/path filters, suggestions, policy exits, prerelease, JSON, and cache controls. `doctor` accepts diagnostic scopes and explicit rootless repair consent; `verify` accepts image, reviewed-inventory path, check scopes, JSON, and evidence-collection output. Flags modify only their owning command unless explicitly global.

Gateway diagnosis SHALL live in a dedicated, independently testable networking module. That module owns Docker mode detection, candidate selection, probe execution, rootless override operations, persistence, and structured diagnosis results without parsing process arguments. The facade imports and reuses this API; helper modules and tests use the same API instead of duplicating networking logic.

### Use argument vectors, not shell command strings

Both build and launch paths will pass lists to `subprocess.run`. Explicit `--build-arg`, `--mount`, `--env`, `--workdir`, `--add-host`, and `--name` arguments avoid shell quoting and YAML interpolation problems. A shared command renderer will make argument construction independently testable.

### Preserve the current runtime contract with direct `docker run`

The internal launcher API used by `docker-constructor.py run` will mount host `~/.pi`, mount the main and optional projects 1:1, set the main project as working directory, export `PROJECT_PATH_1..N`, add `host.docker.internal`, allocate `pi-N`, use `--rm` and interactive TTY behavior, and run the same tagged image. There is no replacement Compose abstraction or generated configuration file.

### Project one reviewed inventory by installation phase

`docker-constructor.toml` remains the single reviewed dependency source and contains explicit closed `build` and `runtime` sections. The build section owns dependencies installed into the image—base image, toolchains, CLIs, prebuilt artifacts, source/update metadata, checksums, and build override policy. The runtime section owns dependencies installed or validated after container start, initially Pi extensions, and may retain host-side source/update and override metadata needed by facade commands.

The resolver validates the complete source and creates typed phase-specific effective projections after applying command-owned overrides. The effective build projection is written atomically to `.docker-generated/docker-constructor.build.effective.toml`, drives individual Docker build arguments, and remains host-only; neither the reviewed source nor this projection is copied into the image or mounted at runtime. Host-side `verify` APIs retain its expected values and compare them with commands executed in the container.

For `run`, the resolver creates a narrow effective runtime projection containing only package identity, effective version, downloadable artifact identity, checksum/integrity, and validation metadata required by the internal installer. Host-only update providers, update policy, override policy, and unrelated source fields are omitted even when present in the reviewed runtime section. The generated projection is validated against its own closed DTO schema, written atomically to a private per-launch file under `.docker-generated/runtime/`, and mounted read-only at `/run/pi-cli/docker-constructor.runtime.toml`. A per-launch file prevents concurrent sessions with different overrides from mutating each other's mounted input; the launcher owns cleanup after Docker exits or launch fails. The entrypoint/runtime installer verifies integrity, installs idempotently into mounted Pi home, and validates installed metadata.

Build-installed dependency selections SHALL NOT be duplicated in the runtime source section or effective runtime projection. `check-updates`, `validate`, and `show` can operate on either or both source scopes while preserving typed models. `show --effective --scope build|runtime` renders the corresponding projection. Runtime overrides affect only the generated runtime projection and never rewrite the reviewed source.

Dynamic host settings such as gateway persistence, UID/GID, ownership policy, and launcher root are intentionally not assigned to either dependency section in this change. Existing operational storage remains until a separate design resolves dynamic versus immutable host configuration. Project selections remain ephemeral launcher inputs.

Rootful Docker may use `host-gateway`; rootless Docker retains candidate probing and optional user-systemd override installation. `docker/apply-rootless-port-forward.sh` will call the unified command surface instead of the removed wrapper.

### Remove Compose compatibility rather than maintain two public paths

Compose files, fragments, `COMPOSE_FILE`, `versions.py`, `launch-pi.py`, and their standalone command adapters will be removed or internalized. Compatibility aliases were rejected because they would preserve multiple public command surfaces and make the canonical interface ambiguous. Documentation will use only `docker/docker-constructor.py` commands.

### Remove the unused inf-splitter model generator

`docker/gen-models-json.py` is not called by the image build, launcher, runtime setup, or maintained user workflow. Its only configuration surface is stale `.env.example` guidance plus a legacy semantic requirement. The script, `PROXY_PORT`, inf-splitter path examples, tests dedicated only to this generator, and the corresponding `build-networking` requirement will be removed rather than migrated into either dependency section. Users needing a custom Pi provider can maintain `models.json` through the owning external integration instead of this repository.

### Bridge Docker-host acceptance with portable evidence

A host-side acceptance collector will perform the minimal real-Docker build and representative runtime launch, then save command arguments, exit status, bounded stdout/stderr, host-only effective build expectations, the generated and mounted effective runtime projection identity, image inspection, structured runtime observations, checksums, and a human-readable index in a portable evidence bundle. The bundle can be copied into the development container for direct inspection by the agent; a dedicated validation program would duplicate the agent's reasoning and is intentionally out of scope. Collector boundaries remain testable with fixtures and fake processes, while only producing fresh acceptance evidence requires a Docker-capable host. The bundle will redact secrets and include enough host/tool metadata to distinguish implementation failures from environment differences.

## Risks / Trade-offs

- [Docker flags drift between launcher and tests] → Centralize pure command rendering and assert complete argument vectors.
- [Interactive behavior differs from Compose] → Test TTY/stdin flags and provide a non-interactive path where required by automation.
- [Gateway diagnosis blocks a build when host reachability is unavailable] → Make this failure explicit and actionable because the unified build workflow is also responsible for preparing the later runtime mapping; test rootful, rootless, failure, and override paths.
- [Secrets or malformed paths appear in diagnostics] → Print shell-escaped display forms while executing argument vectors directly.
- [Projection accidentally exposes reviewed or build-only metadata] → Generate the mounted runtime DTO by explicit field selection, validate it against a closed schema, and assert the reviewed source and effective build projection are absent from the container.
- [Runtime package metadata drifts from installed extensions] → Require exact package identity, version, checksum/integrity verification, idempotent installation, and post-install validation.
- [Removing embedded build metadata weakens verification] → Compare runtime command observations against host-side effective build expectations through internal verification APIs.
- [Existing user automation invokes Compose] → Mark the command removal as breaking and update every repository-owned caller and maintained README in one change.

## Migration Plan

1. Introduce and test direct Docker build/run command rendering and unified gateway services.
2. Add the constructor CLI facade and migrate build, run, update, validation, inspection, doctor, verification, helper, and acceptance workflows to internal APIs.
3. Update documentation and semantic specs to the direct-Docker interface.
4. Remove `build_wrapper.py`, Compose files/fragments, obsolete Compose code/tests, and the unused inf-splitter generator and configuration surface.
5. Verify inventory overrides, rootful/rootless diagnosis, build caching, runtime mounts, extension installation, and smoke checks.

Rollback restores the removed Compose files and command adapter; the reviewed inventory remains the canonical dependency source.

## Resolved Questions

- The canonical build performs gateway diagnosis and fails actionably if no runtime-capable mapping can be selected.
- Installing or changing the rootless systemd override requires an explicit user option; diagnosis alone never modifies user services.
