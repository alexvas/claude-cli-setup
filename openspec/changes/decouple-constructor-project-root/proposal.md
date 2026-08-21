## Why

The constructor currently treats its own source checkout as the environment definition root, so its inventory, Dockerfile, local inputs, and generated artifacts cannot accompany an independent environment directory in the same way a Compose file accompanies its project. Separating the installed tool from the selected environment definition is the first prerequisite for using the constructor with independently maintained Pi, Claude CLI, Codex CLI, OpenCode, and other agent environments.

## What Changes

- Add a global `--project-directory DIR` selector; without it, every command uses the current working directory as the constructor project directory.
- Resolve the fixed project-owned files and directories from that root: `docker-constructor.toml`, `docker-constructor.local.toml`, `Dockerfile`, `.docker-local/`, and `.docker-generated/`.
- Require the selected project directory to exist, normalize it to an absolute physical path, and report actionable configuration errors for missing required files.
- Keep each project-supplied `Dockerfile` and its build assets self-contained; this change does not add alternate Dockerfile names or generated/merged build contexts.
- Apply project-directory resolution consistently to validation, display, update discovery, build, run, doctor, and verification commands, while keeping mounted source workspaces independent from the constructor project.
- Store generated runtime projections under the selected constructor project's `.docker-generated/` directory and use that tree for verify lookup by default, while preserving explicit verify `--runtime-projection PATH` as a caller-directed input.
- Store evidence under `.docker-generated/evidence/` by default while preserving an explicit `--output-dir` override that does not affect any other project-owned path.
- **BREAKING** Remove `--inventory`; the reviewed inventory and its local companion now have fixed names under the selected project directory.
- **BREAKING** Replace runtime project-selection terminology end to end: `--workspace`/`-w`, repeatable `--extra-workspace`, and `--workspace-root` replace `--main-project`/`-m`, `--project`, and `--base-project-dir`; domain/TUI names and diagnostics follow the same terminology.
- **BREAKING** Replace the project-local `.env` launcher default `BASE_PROJECT_DIR` with `WORKSPACE_ROOT`.
- **BREAKING** Replace the container contract `PROJECT_PATH_1..N` with `WORKSPACE_PATH_1..N`, where index 1 is the container working directory and later indices are extra 1:1 bind-mounted workspaces. No deprecated aliases are retained.
- Keep Pi-specific image tags, prompts, home paths, projection paths, and inventory schema out of scope.

## Capabilities

### New Capabilities
- `constructor-project-root`: Selection, normalization, and consistent use of a CWD- or flag-selected environment definition root.

### Modified Capabilities
- `docker-build-reproducibility`: Replace source-checkout/custom-inventory discovery with the fixed project-local inventory and Dockerfile contract.
- `runtime-host-access`: Resolve machine-local companion state from the selected constructor project after removing custom inventory paths.
- `corporate-network-configuration`: Resolve project-owned trust inputs from the selected constructor project rather than the tool installation checkout.
- `project-launcher`: Replace main/additional project selection with primary/extra workspace selection throughout CLI and TUI behavior.
- `docker-runtime`: Replace mounted-project terminology and `PROJECT_PATH_*` with the workspace-oriented runtime contract.
- `user-cache-storage`: Keep runtime projections and default evidence output outside constructor-managed persistent caches, while allowing evidence to be redirected to any explicit `--output-dir` regardless of location.

## Impact

- Affects CLI parsing and dispatch, build/doctor/run orchestration, inventory and local companion resolution, corporate-network path resolution, generated projection/evidence publication, runtime rendering and entrypoint behavior, TUI selection, verification, acceptance scripts, tests, and all maintained README translations.
- Removes public CLI options and container environment variables without compatibility aliases; callers and automation must migrate in the same release.
- Requires existing source-checkout usage to run from the repository root or pass `--project-directory` explicitly.
- Adds no external dependency and does not generalize the Pi-specific inventory schema or runtime implementation.
