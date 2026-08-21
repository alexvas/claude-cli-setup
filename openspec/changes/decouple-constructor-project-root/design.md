## Context

The executable bootstrap and facade currently derive `_REPO_ROOT` from the installed Python file and use it for several unrelated concepts: locating the reviewed inventory, selecting Docker build context, publishing effective projections and evidence, reading `.env`, and locating `.docker-local` trust inputs. The domain build planner already defaults its context to the inventory parent and already accepts context/Dockerfile fields, but the facade supplies the source checkout as `repo_root`, leaving path ownership inconsistent across commands.

Runtime launch has a second use of “project”: `--main-project` and `--project` identify source directories mounted into the container. Introducing a Compose-like `--project-directory` would make that terminology ambiguous. This change therefore separates the constructor project (the environment definition) from primary and extra workspaces (the source trees used by an agent session).

The change is intentionally breaking. There is no compatibility period for custom inventory paths, old launcher flags, old domain names, `.env` `BASE_PROJECT_DIR`, or `PROJECT_PATH_*` container variables.

## Goals / Non-Goals

**Goals:**

- Make environment definitions portable directories independent of the constructor installation checkout.
- Establish one authoritative, normalized constructor project root for every command invocation.
- Resolve fixed inventory, companion, Dockerfile, local input, dotenv, and generated output paths from that root.
- Keep runtime source workspaces distinct in CLI, domain, TUI, rendering, entrypoint, verification, tests, and documentation.
- Fail before side effects when project resolution or required project inputs are invalid.

**Non-Goals:**

- Generalizing the Pi-oriented inventory schema, image tag, prompts, container names, home paths, or runtime projection paths.
- Supporting alternate inventory or Dockerfile names, parent-directory discovery, multiple inventories, or generated/merged build contexts.
- Shipping reusable Dockerfile assets from the installed constructor; each selected project owns a self-contained build context.
- Preserving aliases for removed CLI options, `.env` keys, domain fields, or container environment variables.

## Decisions

### Resolve one typed constructor project before command dispatch

Introduce a small immutable project-path value resolved from global CLI input. Its root is `Path.cwd()` when `--project-directory` is absent and the supplied path resolved relative to CWD otherwise. Resolution requires an existing directory and uses an absolute physical `resolve()` path. The value derives fixed paths for:

```text
<root>/docker-constructor.toml
<root>/docker-constructor.local.toml
<root>/Dockerfile
<root>/.env
<root>/.docker-local/
<root>/.docker-generated/
```

The facade passes this resolved value, or explicit derived paths from it, to command services. Installation/source location remains usable only for Python bootstrap/import concerns and must not select project-owned state.

This central resolver is preferred over letting each service inspect CWD because it gives all commands identical semantics, makes path behavior injectable in tests, and prevents a process-level directory change from splitting one transaction across roots.

### Use a fixed local layout and remove `--inventory`

The constructor always reads `<root>/docker-constructor.toml`; its only companion is `<root>/docker-constructor.local.toml`. `--inventory` is removed from parsing, request DTOs, diagnostics, scripts, documentation, and tests. Unknown use fails as a CLI error.

A fixed layout is preferred over precedence between `--project-directory` and `--inventory`: the latter permits inventory, Dockerfile, local inputs, and generated outputs to acquire unrelated roots without a clear user benefit.

### Make the selected project the Docker build context

`build` uses `<root>` as the context and `<root>/Dockerfile` as the sole Dockerfile. The facade checks that Dockerfile before projection publication or Docker execution. Other commands do not require Dockerfile existence. Dockerfile `COPY` inputs remain entirely project-owned; the constructor does not synthesize a context or inject installation assets.

Although the rendering DTO can express alternate context and Dockerfile values, the canonical CLI does not expose them. Keeping lower-level rendering general is acceptable, but orchestration inputs that exist only for the removed ambiguity should be narrowed where practical.

### Put all project-owned reads and writes under the selected root

Build and runtime projection creation paths, the default evidence path, the default verification projection lookup, `.env`, and `.docker-local/corporate-ca-bundle.crt` resolve under the selected root. An explicit verify `--runtime-projection PATH` remains caller-directed and may point outside the selected project without changing projection creation or any other project-owned path. The local companion remains the only machine-local TOML input. Persistent artifact/HTTP caches continue to use their existing local-companion or XDG policy; they are not moved beneath the project merely because project-local configuration selects them.

All commands (`validate`, `show`, `check-updates`, `build`, `run`, `doctor`, and `verify`) consume the same project root even when a command only needs a subset of its derived paths.

### Rename runtime source selection to workspace selection end to end

The public interface becomes:

```text
--workspace PATH, -w PATH       primary workspace; required unless TUI selects it
--extra-workspace PATH          repeatable extra workspace
--workspace-root PATH           filesystem tree root for TUI
.env WORKSPACE_ROOT             project-local TUI default
```

Domain and TUI types use `WorkspaceSelection`, `workspace`, `extra_workspaces`, and `workspace_root`; renderer and verification DTOs use the same vocabulary. The first selected workspace remains the container workdir and all workspaces retain 1:1 bind mounts.

The container contract becomes consecutive `WORKSPACE_PATH_1..N`. Entrypoint repair and runtime verification inspect only those variables. `CHOWN_WORK_ON_START` remains unchanged because it is already workspace-neutral. Old names are rejected rather than translated.

### Treat compatibility breakage as one atomic migration

CLI parsing, run-vector rendering, image entrypoint behavior, verification, acceptance helpers, documentation, and tests change in one release. This avoids containers that expect `WORKSPACE_PATH_*` being launched by a host that emits `PROJECT_PATH_*`, or vice versa.

## Risks / Trade-offs

- **[Existing automation breaks immediately]** → Document an explicit old-to-new mapping and update all repository-owned scripts and examples in the same change.
- **[A command accidentally retains `_REPO_ROOT`]** → Add cross-command tests from a foreign CWD with an explicit project directory, plus semantic scans for project-owned `_REPO_ROOT` and removed names.
- **[Generated files and lookup inputs are split across roots]** → Derive build/runtime projection creation paths, the default runtime-projection lookup, and the default evidence path from the single immutable constructor-project value, while preserving explicit evidence `--output-dir` and verify `--runtime-projection PATH` as caller-directed paths; assert default placement and both explicit redirection boundaries in orchestration tests.
- **[Symlink handling crosses path-domain boundaries]** → Apply physical resolution only to the constructor-project root and its derived project-owned paths. Preserve workspace paths using the existing lexical absolute-path normalization without resolving workspace symlinks, so workspace bind and display paths retain their established spelling; test both path domains independently.
- **[A standalone Dockerfile lacks current repository scripts]** → Require the selected project to supply every `COPY` input in its context and let Docker report missing project-owned assets; do not silently source files from the installation.
- **[Large rename obscures functional regressions]** → Stage implementation by project-root plumbing, then host workspace DTO/rendering, then container contract, followed by docs and semantic cleanup.

## Migration Plan

1. Update repository-owned definitions and scripts so the repository root remains a valid constructor project under the fixed layout.
2. Replace invocations using `--inventory` with `--project-directory <directory-containing-docker-constructor.toml>` or execute from that directory.
3. Replace `--main-project`/`-m`, `--project`, and `--base-project-dir` with `--workspace`/`-w`, `--extra-workspace`, and `--workspace-root`.
4. Rename project-local `.env` `BASE_PROJECT_DIR` to `WORKSPACE_ROOT`.
5. Rebuild the image and update any external entrypoint/verification integration from `PROJECT_PATH_*` to `WORKSPACE_PATH_*`; old and new host/image contracts are intentionally not interoperable.
6. Rollback requires reverting the host CLI and image together because no compatibility aliases exist.

## Open Questions

None. The root precedence, fixed filenames, path normalization, command coverage, Dockerfile ownership, and breaking workspace terminology have been selected explicitly.
