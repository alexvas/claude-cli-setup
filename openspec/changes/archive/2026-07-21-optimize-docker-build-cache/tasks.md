## 1. Establish cache-safe stage boundaries

- [x] 1.1 Inventory shared, builder-only, runtime-only, and independently versioned dependencies in the current Dockerfile
- [x] 1.2 Introduce a shared operating-system/dev-user base and derive builder and runtime assembly stages from it
- [x] 1.3 Move each retained build argument immediately before its first consumer and order stable expensive setup before versioned tools

## 2. Improve dependency caches

- [x] 2.1 Configure APT cache mounts to retain lists and archives without storing them in image layers
- [x] 2.2 Add npm download cache mounts with correct ownership for each Node tool installation stage
- [x] 2.3 Add reusable Cargo registry, git, and compilation-target caches with correct dev-user ownership
- [x] 2.4 Remove cleanup operations that target cache mounts and retain cleanup only for data committed to image layers

## 3. Isolate tool installations

- [x] 3.1 Install Pi and OpenSpec in independent stages and prefixes
- [x] 3.2 Assemble Pi, OpenSpec, Rust/Cargo, uv, ty, rtk, fd, and MCP artifacts into the runtime with stable PATH entries and executable links
- [x] 3.3 Place Pi-dependent `pi-read` setup on a cache path unaffected by OpenSpec-only version changes

## 4. Verify behavior

- [x] 4.1 Add static checks or documented commands that verify required runtime executables and versions resolve as user `dev`
- [x] 4.2 On a Docker host, perform two identical plain-progress builds and confirm the second build reuses deterministic layers
- [x] 4.3 On a Docker host, change only `OPENSPEC_VERSION` and confirm APT, Rust, uv, Cargo, and Pi-specific steps remain cached
- [x] 4.4 On a Docker host, change only `PI_VERSION` and confirm the independent OpenSpec installation remains cached
- [x] 4.5 Record measured build timing and image-size changes and document normal BuildKit cache pruning guidance
