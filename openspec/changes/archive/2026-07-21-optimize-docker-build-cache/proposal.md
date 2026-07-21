## Why

Changing one tool version currently invalidates early Docker builder layers, including Debian package installation and expensive Rust/Cargo setup, because all build arguments are declared before the first `RUN`. The image also installs overlapping Debian packages in independent builder and runtime chains and configures APT cache mounts in a way that deletes their contents, making routine upgrades slower than necessary.

## What Changes

- Introduce an explicit Docker build-cache contract for stable dependency layers and version-specific tool layers.
- Move build arguments next to their first use and order expensive stable operations before frequently changing tool installations.
- Build builder and runtime stages from a shared base layer where their operating-system setup overlaps, avoiding duplicate package installation where practical.
- Preserve APT metadata and package archives in BuildKit cache mounts without copying them into the resulting image.
- Add appropriate npm and Cargo compilation caches for recovery when layer reuse is impossible.
- Isolate independently versioned tools, especially Pi and OpenSpec, so changing one version rebuilds only its installation stage and the minimum required final assembly layers.
- Keep final-image cleanup limited to data actually stored in image layers rather than BuildKit cache mounts.

## Capabilities

### New Capabilities
- `docker-build-caching`: Defines cache reuse and invalidation boundaries for the Docker build, including shared base setup, dependency caches, and independently versioned tools.

### Modified Capabilities
- `docker-runtime`: The multi-stage image gains a shared base and isolated tool assembly while preserving the existing runtime toolset and commands.

## Impact

- Affects `Dockerfile`, Docker BuildKit cache mounts, stage layout, tool installation prefixes, and final-stage `COPY`/symlink assembly.
- May affect image layer ordering and intermediate-stage names, but does not intentionally change the runtime CLI interface.
- Requires build verification on a Docker host because Docker is unavailable inside the coding-agent container.
