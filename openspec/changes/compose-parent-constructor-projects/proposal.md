## Why

Independent constructor projects need to reuse a reviewed base environment without copying its dependency inventory, Dockerfile support files, and subsequent maintenance into every concrete project. A parent-project chain with collision-free composition provides that reuse while retaining one owner for every setting and build asset.

This change depends on `decouple-constructor-project-root`; implementation SHALL begin only after that predecessor is implemented, synchronized, and archived.

## What Changes

- Add optional schema-1 `parent-project` metadata to `docker-constructor.toml`, accepting an absolute path or a path relative to the declaring constructor project.
- Resolve up to 32 physical project layers, detect canonical-path and POSIX file-identity cycles, and merge globally disjoint TOML leaf settings from base to child.
- Validate the terminal base and every effective prefix, then materialize the validated merged raw inventory without `parent-project` metadata or CLI overrides.
- Compose inherited reviewed build inputs only from `docker-assets/`, reject cross-layer path, type, permission, and physical hard-link collisions, and allow only regular files and directories.
- Select the nearest child-side `Dockerfile` and its same-layer `.dockerignore`, and create a private leaf-owned Docker context containing those controls, the merged inventory, inherited assets, and leaf-only local assets.
- Rename reviewed Docker build inputs from the mixed `docker/` source tree into `docker-assets/`, and rename machine-local build inputs from `.docker-local/` to `.docker-assets-local/` during implementation.
- Serialize builds of one leaf project with a project lock and securely clean private or stale composed contexts.
- Keep `docker-constructor.local.toml`, `.docker-assets-local/`, `.env`, and `.docker-generated/` leaf-only; parent machine-local state is never inherited.
- Preserve the existing override boundary: CLI overrides affect effective projections and build arguments but not the merged reviewed `docker-constructor.toml` in the composed context.
- **BREAKING** Project Dockerfiles must source reviewed build inputs from `docker-assets/` and machine-local build inputs from `.docker-assets-local/`; the previous build-asset paths have no compatibility fallback after migration.

## Capabilities

### New Capabilities
- `constructor-project-inheritance`: Parent-chain resolution, collision-free inventory and asset composition, physical identity safety, Dockerfile selection, and private build-context lifecycle.

### Modified Capabilities
- `constructor-project-root`: Replace the leaf-only fixed build context and root Dockerfile contract with explicit parent-project layers, nearest-child Dockerfile selection, composed reviewed assets, and leaf-only `.docker-assets-local/` state.
- `docker-build-reproducibility`: Make the merged reviewed inventory authoritative for parented projects while preserving standalone inventory behavior and the existing effective override boundary.
- `corporate-network-configuration`: Move the leaf-only corporate trust bundle to `.docker-assets-local/corporate-ca-bundle.crt` and include it through the composed context.

## Impact

- Affects constructor project resolution, inventory parsing and validation, read-only commands, build orchestration and locking, context materialization, Docker rendering, corporate trust lookup, and generated-output cleanup.
- Migrates repository-owned Dockerfile inputs and all `COPY` paths, tests, verification scripts, examples, ignore rules, and maintained documentation.
- Adds no external service or network dependency; filesystem traversal, identity checks, TOML composition, and context preparation remain local and pre-Docker.
- Requires completion of `decouple-constructor-project-root` before implementation because this change replaces its self-contained single-project context with an explicit composed-project contract.
